#define _GNU_SOURCE
#include "guardian.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <linux/openat2.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <poll.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/statfs.h>
#include <sys/wait.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

#define GUARDIAN_DEPTH_LIMIT 64
#define GUARDIAN_SETTLE_NS 10000000000ULL

static guardian_result refuse(guardian_state *state, uint32_t operation, int error, guardian_result result) {
    state->operation = operation;
    state->system_errno = error;
    return result;
}

static uint64_t now_ns(void) {
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    return (uint64_t)value.tv_sec * 1000000000ULL + (uint64_t)value.tv_nsec;
}

static void close_slot(int *slot) {
    if (*slot >= 0) close(*slot);
    *slot = -1;
}

/* The subtree is resolved beneath the mount without symlinks or other mounts, and must
 * belong to the hierarchy owner with no group or other write. */
static bool trusted_entry(const struct stat *status, uid_t owner) {
    return (status->st_uid == 0 || status->st_uid == owner) && !(status->st_mode & (S_IWGRP | S_IWOTH));
}

/* A cgroup is trusted when root or the hierarchy owner holds it and the files that move
 * processes or enable controllers. A delegated cgroup anywhere on the way would let its
 * owner move a payload out of its container and past the epoch's kill. */
static bool trusted_cgroup(int directory, uid_t owner) {
    static const char *const files[] = {"cgroup.procs", "cgroup.threads", "cgroup.subtree_control"};
    struct stat status;
    if (fstat(directory, &status) != 0 || !trusted_entry(&status, owner)) return false;
    for (size_t i = 0; i < sizeof(files) / sizeof(files[0]); ++i)
        if (fstatat(directory, files[i], &status, AT_SYMLINK_NOFOLLOW) != 0 || !trusted_entry(&status, owner))
            return false;
    return true;
}

/* Walks the subtree one component at a time beneath the mount, never through a link,
 * and judges every cgroup on the way, the mount and the subtree included. */
static guardian_result open_subtree(guardian_state *state) {
    const guardian_manifest *manifest = state->manifest;
    char path[256];
    if (strlen(manifest->subtree) >= sizeof(path)) return refuse(state, 12, ENAMETOOLONG, GUARDIAN_REFUSED);
    strcpy(path, manifest->subtree);
    if (!trusted_cgroup(state->mount, manifest->hierarchy_owner)) return refuse(state, 14, EPERM, GUARDIAN_REFUSED);
    struct open_how how = {.flags = O_RDONLY | O_DIRECTORY | O_CLOEXEC,
        .resolve = RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS | RESOLVE_NO_XDEV | RESOLVE_NO_MAGICLINKS};
    int current = dup(state->mount);
    if (current < 0) return refuse(state, 12, errno, GUARDIAN_REFUSED);
    for (char *cursor = path, *end; cursor; cursor = end ? end + 1 : NULL) {
        end = strchr(cursor, '/');
        if (end) *end = 0;
        if (!*cursor) continue;
        long next = syscall(SYS_openat2, current, cursor, &how, sizeof(how));
        int saved = errno;
        close(current);
        if (next < 0) return refuse(state, 12, saved, GUARDIAN_REFUSED);
        current = (int)next;
        if (!trusted_cgroup(current, manifest->hierarchy_owner)) {
            close(current);
            return refuse(state, 14, EPERM, GUARDIAN_REFUSED);
        }
    }
    state->subtree = current;
    return GUARDIAN_READY;
}

static guardian_result open_hierarchy(guardian_state *state) {
    const guardian_manifest *manifest = state->manifest;
    struct statfs filesystem;
    struct stat status;
    state->mount = gj_open_trusted_directory(manifest->cgroup_mount, manifest->hierarchy_owner);
    if (state->mount < 0) return refuse(state, 10, errno, GUARDIAN_REFUSED);
    if (fstatfs(state->mount, &filesystem) != 0 || filesystem.f_type != CGROUP2_SUPER_MAGIC)
        return refuse(state, 11, ENOTDIR, GUARDIAN_REFUSED);
    guardian_result opened = open_subtree(state);
    if (opened != GUARDIAN_READY) return opened;
    if (fstat(state->subtree, &status) != 0 || status.st_uid != manifest->hierarchy_owner ||
        (status.st_mode & (S_IWGRP | S_IWOTH)))
        return refuse(state, 13, EPERM, GUARDIAN_REFUSED);
    return GUARDIAN_READY;
}

static bool write_control(int directory, const char *name, const char *value) {
    int number = openat(directory, name, O_WRONLY | O_NOFOLLOW | O_CLOEXEC);
    if (number < 0) return false;
    size_t length = strlen(value);
    bool written = write(number, value, length) == (ssize_t)length;
    return close(number) == 0 && written;
}

static bool unpopulated(int directory) {
    char buffer[256] = {0};
    int number = openat(directory, "cgroup.events", O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (number < 0) return false;
    ssize_t count = read(number, buffer, sizeof(buffer) - 1);
    close(number);
    return count > 0 && strstr(buffer, "populated 0") != NULL;
}

/* Child cgroups first, then the directory itself. Interface files cannot be removed
 * and need not be: rmdir of a cgroup with no children and no tasks succeeds. */
static bool remove_tree(int parent, const char *name, unsigned depth) {
    if (depth > GUARDIAN_DEPTH_LIMIT) return false;
    int directory = openat(parent, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (directory < 0) return errno == ENOENT;
    int listing = dup(directory);
    DIR *entries = listing >= 0 ? fdopendir(listing) : NULL;
    bool removed = entries != NULL;
    if (!entries && listing >= 0) close(listing);
    for (struct dirent *entry = entries ? readdir(entries) : NULL; removed && entry; entry = readdir(entries))
        if (entry->d_type == DT_DIR && strcmp(entry->d_name, ".") && strcmp(entry->d_name, ".."))
            removed = remove_tree(directory, entry->d_name, depth + 1);
    if (entries) closedir(entries);
    close(directory);
    return removed && (unlinkat(parent, name, AT_REMOVEDIR) == 0 || errno == ENOENT);
}

/* An absent branch is already reclaimed. A present one is killed as a whole, must report
 * no task left, and is then removed bottom-up. */
static bool reclaim_branch(guardian_state *state, const char *name) {
    if (!name[0]) return true;
    int branch = openat(state->subtree, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (branch < 0) return errno == ENOENT;
    bool killed = write_control(branch, "cgroup.kill", "1");
    uint64_t limit = now_ns() + GUARDIAN_SETTLE_NS;
    bool empty = false;
    while (killed && !(empty = unpopulated(branch)) && now_ns() < limit) {
        struct timespec pause = {0, 10000000};
        nanosleep(&pause, NULL);
    }
    close(branch);
    return killed && empty && remove_tree(state->subtree, name, 0);
}

static void taint(guardian_state *state, int slice) {
    fprintf(stderr, "autocontrol-owner-guardian: payload slice %d left files it could not remove\n", slice);
    for (int s = 0; s < SERVICE_PAYLOAD_SLICES; ++s) if (slice < 0 || slice == s) state->tainted[s] = true;
}

void guardian_purge_abandon(guardian_state *state) {
    for (int s = 0; s < SERVICE_PAYLOAD_SLICES; ++s) {
        if (state->purging[s] < 0) continue;
        syscall(SYS_pidfd_send_signal, state->purging[s], SIGKILL, NULL, 0);
        struct pollfd ended = {.fd = state->purging[s], .events = POLLIN};
        int rc;
        do { rc = poll(&ended, 1, 5000); } while (rc < 0 && errno == EINTR);
        siginfo_t info;
        if (rc > 0) while (waitid(P_PIDFD, (id_t)state->purging[s], &info, WEXITED) < 0 && errno == EINTR) continue;
        close(state->purging[s]); /* One stuck in D state is left to init once the guardian exits. */
        state->purging[s] = -1;
    }
}

/* The purge child holds nothing of the guardian's (no journal lock, listener or channel),
 * dies with it, and answers signals again. */
static void purge_child(const guardian_state *state, int slice, pid_t guardian) {
    syscall(SYS_close_range, 3U, ~0U, 0);
    prctl(PR_SET_PDEATHSIG, SIGKILL);
    if (getppid() != guardian) _exit(1); /* It died before the signal was armed. */
    sigset_t none;
    sigemptyset(&none);
    sigprocmask(SIG_SETMASK, &none, NULL);
    guardian_purge_heartbeat = state->heartbeat ? &state->heartbeat[slice] : NULL;
    if (!guardian_purge_unshare())
        fprintf(stderr, "autocontrol-owner-guardian: purge keeps the host's mounts; it skips them\n");
    guardian_purge_outcome outcome = guardian_purge_payloads(state->manifest, slice);
    /* While serving it runs again at once: never a busy loop. At startup the rerun comes later. */
    if (outcome == PURGE_INCOMPLETE && state->purge_async) sleep(1);
    _exit((int)outcome);
}

/* Clean: nothing to do. Incomplete: run again before the slice is handed out. Anything
 * else (unclean, killed, an unknown status) taints. */
static void purge_settled(guardian_state *state, int slice, int outcome) {
    if (slice >= 0) state->stall_round[slice] = 0; /* It ended by itself. */
    if (outcome == PURGE_CLEAN) return;
    if (outcome != PURGE_INCOMPLETE) { taint(state, slice); return; }
    for (int s = 0; s < SERVICE_PAYLOAD_SLICES; ++s) if (slice < 0 || slice == s) state->repurge[s] = true;
}

void guardian_purge_reap(guardian_state *state, int slice) {
    if (state->purging[slice] < 0) return;
    siginfo_t info;
    memset(&info, 0, sizeof(info));
    int rc;
    do { rc = waitid(P_PIDFD, (id_t)state->purging[slice], &info, WEXITED); } while (rc < 0 && errno == EINTR);
    close(state->purging[slice]);
    state->purging[slice] = -1;
    if (state->stalled[slice]) { state->stalled[slice] = false; state->repurge[slice] = true; }
    else if (rc != 0 || info.si_code != CLD_EXITED) taint(state, slice);
    else purge_settled(state, slice, info.si_status);
}

#define PURGE_STALL_NS (60ULL * 1000000000ULL)
#define PURGE_CHECK_MS 5000

static void purge_start_watch(guardian_state *state, int slice) {
    if (state->heartbeat) __atomic_store_n(&state->heartbeat[slice], 0, __ATOMIC_RELAXED);
    state->beat_seen[slice] = 0;
    state->beat_at[slice] = now_ns();
    state->stalled[slice] = false;
}

/* Kills the purge child behind `pidfd` once its heartbeat stood still for a minute: a purge
 * stuck in one call, never one that is merely long. */
static void purge_check(guardian_state *state, int slice, int pidfd) {
    if (!state->heartbeat || state->stalled[slice]) return;
    uint64_t beat = __atomic_load_n(&state->heartbeat[slice], __ATOMIC_RELAXED), now = now_ns();
    if (beat != state->beat_seen[slice]) { state->beat_seen[slice] = beat; state->beat_at[slice] = now; return; }
    /* A minute, doubled after each stall of this slice in a row (up to an hour): one slow but
     * finite call (getdents over a huge emptied directory) gets through on a later run. */
    if (now - state->beat_at[slice] < PURGE_STALL_NS << state->stall_round[slice]) return;
    fprintf(stderr, "autocontrol-owner-guardian: purge of slice %d made no progress; it runs again\n", slice);
    syscall(SYS_pidfd_send_signal, pidfd, SIGKILL, NULL, 0);
    state->stalled[slice] = true;
    if (state->stall_round[slice] < 6) ++state->stall_round[slice];
}

int guardian_purge_watch(guardian_state *state) {
    int timeout = -1;
    for (int s = 0; s < SERVICE_PAYLOAD_SLICES; ++s) {
        if (state->purging[s] < 0) continue;
        purge_check(state, s, state->purging[s]);
        timeout = PURGE_CHECK_MS;
    }
    return timeout;
}

/* Waits here for a purge child (startup, or no pidfd to watch it from the loop), watching
 * its heartbeat all the same. */
static void await_purge(guardian_state *state, int slice, pid_t child) {
    int pidfd = (int)syscall(SYS_pidfd_open, child, 0);
    int grace = 0;
    while (pidfd >= 0) {
        struct pollfd ended = {.fd = pidfd, .events = POLLIN};
        int rc = poll(&ended, 1, PURGE_CHECK_MS);
        if (rc > 0 || (rc < 0 && errno != EINTR)) break;
        purge_check(state, slice, pidfd);
        if (state->stalled[slice] && ++grace > 6) {
            /* Killed, yet in a call no signal ends: the loop reaps it whenever it does end,
             * and the slice waits for it, but the guardian goes on. */
            state->purging[slice] = pidfd;
            return;
        }
    }
    if (pidfd >= 0) close(pidfd);
    int status = 0;
    while (waitpid(child, &status, 0) < 0 && errno == EINTR) continue;
    if (state->stalled[slice]) { state->stalled[slice] = false; state->repurge[slice] = true; }
    else if (!WIFEXITED(status)) taint(state, slice);
    else purge_settled(state, slice, WEXITSTATUS(status));
}

/* A slice's purge runs in a child, with its own mount namespace. While serving, the loop goes
 * on and the slice is not handed out until the child is reaped, so a large tree in a shared
 * directory cannot stall accepts or supervision; at startup the child is waited for here.
 * Only when no child can be made does it run in the guardian itself. An unclean purge taints
 * its slice: the guardian never grants it again. */
static void purge(guardian_state *state, int slice) {
    for (int s = 0; s < SERVICE_PAYLOAD_SLICES; ++s) if (slice < 0 || slice == s) state->repurge[s] = false;
    if (slice >= 0) {
        if (state->purge_async) guardian_purge_reap(state, slice);
        purge_start_watch(state, slice);
        pid_t guardian = getpid();
        pid_t child = fork();
        if (child == 0) purge_child(state, slice, guardian);
        if (child > 0) {
            int pidfd = state->purge_async ? (int)syscall(SYS_pidfd_open, child, 0) : -1;
            if (pidfd >= 0) { state->purging[slice] = pidfd; return; }
            await_purge(state, slice, child);
            return;
        }
    }
    fprintf(stderr, "autocontrol-owner-guardian: purge runs in the guardian: mounts are skipped\n");
    purge_settled(state, slice, (int)guardian_purge_payloads(state->manifest, slice));
}

void guardian_purge_resume(guardian_state *state) {
    for (int s = 0; s < SERVICE_PAYLOAD_SLICES; ++s)
        if (state->repurge[s] && state->purging[s] < 0 && !state->tainted[s]) purge(state, s);
}

guardian_result guardian_reclaim_retired(guardian_state *state, const char *epoch, int slice) {
    if (!reclaim_branch(state, epoch)) return refuse(state, 24, errno, GUARDIAN_UNRESOLVED);
    if (slice != GUARDIAN_PURGE_NONE) purge(state, slice);
    return GUARDIAN_READY;
}

/* A retiring epoch is not journaled: after a crash, every epoch branch the journal does
 * not name is reclaimed, and with nothing running, both halves of every range purged. */
static guardian_result sweep_strays(guardian_state *state) {
    int copy = dup(state->subtree);
    DIR *listing = copy < 0 ? NULL : fdopendir(copy);
    if (!listing) { if (copy >= 0) close(copy); return refuse(state, 25, errno, GUARDIAN_UNRESOLVED); }
    /* Up to eight per pass, and passes until none remain: nothing is purged while a stray
     * epoch could still run. */
    for (;;) {
        char names[8][GJ_COMPONENT_BYTES];
        size_t count = 0;
        rewinddir(listing);
        for (struct dirent *entry; (entry = readdir(listing)) && count < 8;)
            if (!strncmp(entry->d_name, "epoch-", 6) && strlen(entry->d_name) < GJ_COMPONENT_BYTES &&
                (state->journal.current.phase == GJ_CLEAN || strcmp(entry->d_name, state->journal.current.epoch)))
                strcpy(names[count++], entry->d_name);
        if (!count) break;
        for (size_t i = 0; i < count; ++i)
            if (!reclaim_branch(state, names[i])) { closedir(listing); return refuse(state, 25, errno,
                                                                                    GUARDIAN_UNRESOLVED); }
    }
    closedir(listing);
    return GUARDIAN_READY;
}

guardian_result guardian_recover(guardian_state *state, int slice) {
    gj_record *current = &state->journal.current;
    if (current->phase == GJ_CLEAN) return GUARDIAN_READY;
    if (current->phase != GJ_RECOVERING && gj_mark(&state->journal, GJ_RECOVERING) != GJ_ERROR_NONE)
        return refuse(state, 20, EIO, GUARDIAN_UNRESOLVED);
    close_slot(&state->epoch);
    /* The epoch holds the service leaf and every helper: one cgroup.kill takes them
     * together, and the kernel kills anything they fork while the kill runs. */
    if (!reclaim_branch(state, current->epoch)) return refuse(state, 22, errno, GUARDIAN_UNRESOLVED);
    /* Nothing runs as this epoch's payload IDs now: what they left is removed before reuse. */
    if (slice != GUARDIAN_PURGE_NONE) purge(state, slice);
    if (gj_mark(&state->journal, GJ_CLEAN) != GJ_ERROR_NONE) return refuse(state, 23, EIO, GUARDIAN_UNRESOLVED);
    return GUARDIAN_READY;
}

static int delegate(int directory, const guardian_manifest *manifest) {
    static const char *const files[] = {"cgroup.procs", "cgroup.threads", "cgroup.subtree_control"};
    if (fchown(directory, manifest->service_uid, manifest->service_gid) != 0) return errno;
    for (size_t i = 0; i < sizeof(files) / sizeof(files[0]); ++i)
        if (fchownat(directory, files[i], manifest->service_uid, manifest->service_gid, AT_SYMLINK_NOFOLLOW))
            return errno;
    return 0;
}

/* epoch-N is the delegated root: cgroup v2 lets a delegatee move a process only with
 * write access to the common ancestor's cgroup.procs (measured in WSL: EACCES when it
 * is root's), so the service leaf and the helper anchor share this delegated parent.
 * The service leaf itself stays root's, so nothing can be moved into it; `records` is
 * the anchor the service is granted. Payload accounts own nothing here. */
/* The service limits each helper's processes and memory; the controllers it needs are
 * enabled here, root's decision, before anything below is delegated. None of these
 * cgroups holds a process, so enabling them never meets the internal-process rule. */
static const char LIMITED[] = "+pids +memory";

/* Written by root to `records` before it is delegated: the service cannot change them.
 * They hold every helper of the epoch together, so memory a killed helper left charged
 * (tmpfs pages) adds up against them rather than escaping every limit. */
/* pids.max takes at most the kernel's PID_MAX_LIMIT; above it, "max" means the same. */
static bool write_pids(int directory, unsigned long long value) {
    char text[24];
    if (value > (1ULL << 22)) snprintf(text, sizeof(text), "max");
    else snprintf(text, sizeof(text), "%llu", value);
    return write_control(directory, "pids.max", text);
}

static int limit_records(int records, const service_policy *service) {
    /* A compromised service could otherwise nest cgroups past what reclaim removes. */
    if (!write_control(records, "cgroup.max.depth", "32")) return errno;
    if (!service) return 0;
    char value[24];
    if (!write_pids(records, (unsigned long long)(service->record_pids_max * service->record_capacity))) return errno;
    snprintf(value, sizeof(value), "%llu",
             (unsigned long long)(service->record_memory_max * service->record_capacity));
    if (!write_control(records, "memory.max", value)) return errno;
    if (!write_control(records, "memory.swap.max", "0") && errno != ENOENT) return errno;
    return 0;
}

/* epoch-N is delegated too, so its own limits, root's files, bound everything the service
 * may create or move beside `records`: depth below what reclaim removes, a descendant count,
 * and the records' limits plus room for the service itself. */
static int limit_epoch(int epoch, const service_policy *service) {
    if (!write_control(epoch, "cgroup.max.depth", "40") || !write_control(epoch, "cgroup.max.descendants", "4096"))
        return errno;
    if (!service) return 0;
    char value[24];
    if (!write_pids(epoch, (unsigned long long)(service->record_pids_max * service->record_capacity + 256)))
        return errno;
    snprintf(value, sizeof(value), "%llu",
             (unsigned long long)(service->record_memory_max * service->record_capacity + (512ULL << 20)));
    if (!write_control(epoch, "memory.max", value)) return errno;
    if (!write_control(epoch, "memory.swap.max", "0") && errno != ENOENT) return errno;
    return 0;
}

static int create_branches(guardian_state *state) {
    const gj_record *current = &state->journal.current;
    /* ENOENT here means the subtree's parent has not enabled pids and memory. */
    if (!write_control(state->subtree, "cgroup.subtree_control", LIMITED)) return errno;
    char cap[24];
    if (state->manifest->subtree_pids_max &&
        !write_pids(state->subtree, (unsigned long long)state->manifest->subtree_pids_max)) return errno;
    if (state->manifest->subtree_memory_max) {
        snprintf(cap, sizeof(cap), "%llu", (unsigned long long)state->manifest->subtree_memory_max);
        if (!write_control(state->subtree, "memory.max", cap)) return errno;
    }
    if (mkdirat(state->subtree, current->epoch, 0755) != 0) return errno;
    int epoch = openat(state->subtree, current->epoch, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (epoch < 0) return errno;
    int error = write_control(epoch, "cgroup.subtree_control", LIMITED) ? 0 : errno;
    if (!error) error = limit_epoch(epoch, state->manifest->service);
    if (!error && mkdirat(epoch, current->service, 0755) != 0) error = errno;
    if (!error && mkdirat(epoch, "records", 0755) != 0) error = errno;
    if (!error) {
        state->epoch = openat(epoch, "records", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        error = state->epoch < 0 ? errno : write_control(state->epoch, "cgroup.subtree_control", LIMITED) ? 0 : errno;
        if (!error) error = limit_records(state->epoch, state->manifest->service);
        if (!error) error = delegate(state->epoch, state->manifest);
    }
    if (!error) error = delegate(epoch, state->manifest);
    close(epoch);
    return error;
}

guardian_result guardian_prepare(guardian_state *state, const guardian_manifest *manifest) {
    *state = (guardian_state){.manifest = manifest, .mount = -1, .subtree = -1, .epoch = -1};
    for (int s = 0; s < SERVICE_PAYLOAD_SLICES; ++s) state->purging[s] = -1;
    void *beats = mmap(NULL, sizeof(uint64_t) * SERVICE_PAYLOAD_SLICES, PROT_READ | PROT_WRITE,
                       MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (beats == MAP_FAILED) fprintf(stderr, "autocontrol-owner-guardian: purges run without a stall watch\n");
    else state->heartbeat = beats;
    state->journal.directory = state->journal.lock = -1;
    gj_error opened = gj_open(&state->journal, manifest->state_directory, manifest->administrator,
                              manifest->installation);
    if (opened != GJ_ERROR_NONE) return refuse(state, 1, (int)opened, GUARDIAN_REFUSED);
    if (!state->journal.loaded &&
        gj_initialize(&state->journal, manifest->installation, manifest->manifest_version) != GJ_ERROR_NONE)
        return refuse(state, 2, EIO, GUARDIAN_REFUSED);
    guardian_result result = open_hierarchy(state);
    if (result != GUARDIAN_READY) return result;
    result = sweep_strays(state);
    if (result != GUARDIAN_READY) return result;
    result = guardian_recover(state, GUARDIAN_PURGE_NONE);
    if (result != GUARDIAN_READY) return result;
    /* Nothing of an earlier run is alive any more: each slice is purged once, here, and only
     * a slice whose leftovers can be neither removed nor neutralised is tainted. */
    for (int s = 0; s < SERVICE_PAYLOAD_SLICES; ++s) purge(state, s);
    if (result != GUARDIAN_READY) return result;
    return guardian_next_epoch(state);
}

guardian_result guardian_next_epoch(guardian_state *state) {
    close_slot(&state->epoch); /* A retiring service holds its own copy of its records anchor. */
    gj_error planned = gj_plan(&state->journal);
    if (planned != GJ_ERROR_NONE) return refuse(state, 3, (int)planned, GUARDIAN_REFUSED);
    int created = create_branches(state);
    if (!created) return GUARDIAN_READY;
    /* The counter is consumed; whatever was created is reclaimed before refusing. It never
     * ran, so no payload ID needs purging. */
    guardian_result result = guardian_recover(state, GUARDIAN_PURGE_NONE);
    return refuse(state, 4, created, result == GUARDIAN_READY ? GUARDIAN_REFUSED : GUARDIAN_UNRESOLVED);
}

void guardian_close(guardian_state *state) {
    if (state->heartbeat) munmap(state->heartbeat, sizeof(uint64_t) * SERVICE_PAYLOAD_SLICES);
    state->heartbeat = NULL;
    close_slot(&state->epoch);
    close_slot(&state->subtree);
    close_slot(&state->mount);
    gj_close(&state->journal);
}
