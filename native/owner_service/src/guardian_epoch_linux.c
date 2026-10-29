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
#include <sys/statfs.h>
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

guardian_result guardian_reclaim_retired(guardian_state *state, const char *epoch, uint64_t counter) {
    if (!reclaim_branch(state, epoch)) return refuse(state, 24, errno, GUARDIAN_UNRESOLVED);
    guardian_purge_payloads(state->manifest->service, (int)(counter & 1));
    return GUARDIAN_READY;
}

/* A retiring epoch is not journaled: after a crash, every epoch branch the journal does
 * not name is reclaimed, and with nothing running, both halves of every range purged. */
static guardian_result sweep_strays(guardian_state *state) {
    int copy = dup(state->subtree);
    DIR *listing = copy < 0 ? NULL : fdopendir(copy);
    if (!listing) { if (copy >= 0) close(copy); return refuse(state, 25, errno, GUARDIAN_UNRESOLVED); }
    char names[8][GJ_COMPONENT_BYTES];
    size_t count = 0;
    for (struct dirent *entry; (entry = readdir(listing)) && count < 8;)
        if (!strncmp(entry->d_name, "epoch-", 6) && strlen(entry->d_name) < GJ_COMPONENT_BYTES &&
            (state->journal.current.phase == GJ_CLEAN || strcmp(entry->d_name, state->journal.current.epoch)))
            strcpy(names[count++], entry->d_name);
    closedir(listing);
    for (size_t i = 0; i < count; ++i)
        if (!reclaim_branch(state, names[i])) return refuse(state, 25, errno, GUARDIAN_UNRESOLVED);
    guardian_purge_payloads(state->manifest->service, -1);
    return GUARDIAN_READY;
}

guardian_result guardian_recover(guardian_state *state) {
    gj_record *current = &state->journal.current;
    if (current->phase == GJ_CLEAN) return GUARDIAN_READY;
    if (current->phase != GJ_RECOVERING && gj_mark(&state->journal, GJ_RECOVERING) != GJ_ERROR_NONE)
        return refuse(state, 20, EIO, GUARDIAN_UNRESOLVED);
    close_slot(&state->epoch);
    /* The epoch holds the service leaf and every helper: one cgroup.kill takes them
     * together, and the kernel kills anything they fork while the kill runs. */
    if (!reclaim_branch(state, current->epoch)) return refuse(state, 22, errno, GUARDIAN_UNRESOLVED);
    /* Nothing runs as this epoch's payload IDs now: what they left is removed before reuse. */
    guardian_purge_payloads(state->manifest->service, (int)(current->counter & 1));
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
static int limit_records(int records, const service_policy *service) {
    if (!service) return 0;
    char value[24];
    snprintf(value, sizeof(value), "%llu", (unsigned long long)(service->record_pids_max * service->record_capacity));
    if (!write_control(records, "pids.max", value)) return errno;
    snprintf(value, sizeof(value), "%llu",
             (unsigned long long)(service->record_memory_max * service->record_capacity));
    if (!write_control(records, "memory.max", value)) return errno;
    if (!write_control(records, "memory.swap.max", "0") && errno != ENOENT) return errno;
    return 0;
}

static int create_branches(guardian_state *state) {
    const gj_record *current = &state->journal.current;
    /* ENOENT here means the subtree's parent has not enabled pids and memory. */
    if (!write_control(state->subtree, "cgroup.subtree_control", LIMITED)) return errno;
    if (mkdirat(state->subtree, current->epoch, 0755) != 0) return errno;
    int epoch = openat(state->subtree, current->epoch, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (epoch < 0) return errno;
    int error = write_control(epoch, "cgroup.subtree_control", LIMITED) ? 0 : errno;
    if (!error) error = delegate(epoch, state->manifest);
    if (!error && mkdirat(epoch, current->service, 0755) != 0) error = errno;
    if (!error && mkdirat(epoch, "records", 0755) != 0) error = errno;
    if (!error) {
        state->epoch = openat(epoch, "records", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        error = state->epoch < 0 ? errno : write_control(state->epoch, "cgroup.subtree_control", LIMITED) ? 0 : errno;
        if (!error) error = limit_records(state->epoch, state->manifest->service);
        if (!error) error = delegate(state->epoch, state->manifest);
    }
    close(epoch);
    return error;
}

guardian_result guardian_prepare(guardian_state *state, const guardian_manifest *manifest) {
    *state = (guardian_state){.manifest = manifest, .mount = -1, .subtree = -1, .epoch = -1};
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
    result = guardian_recover(state);
    if (result != GUARDIAN_READY) return result;
    return guardian_next_epoch(state);
}

guardian_result guardian_next_epoch(guardian_state *state) {
    close_slot(&state->epoch); /* A retiring service holds its own copy of its records anchor. */
    gj_error planned = gj_plan(&state->journal);
    if (planned != GJ_ERROR_NONE) return refuse(state, 3, (int)planned, GUARDIAN_REFUSED);
    int created = create_branches(state);
    if (!created) return GUARDIAN_READY;
    /* The counter is consumed; whatever was created is reclaimed before refusing. */
    guardian_result result = guardian_recover(state);
    return refuse(state, 4, created, result == GUARDIAN_READY ? GUARDIAN_REFUSED : GUARDIAN_UNRESOLVED);
}

void guardian_close(guardian_state *state) {
    close_slot(&state->epoch);
    close_slot(&state->subtree);
    close_slot(&state->mount);
    gj_close(&state->journal);
}
