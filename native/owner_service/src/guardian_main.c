#define _GNU_SOURCE
/* The installed guardian: prepare the epoch, bind the listener, start the service with
 * only its endpoint, grant the epoch, supervise, and reclaim everything when the
 * service ends. Runs as root under the deployment supervisor. */
#include "guardian.h"
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <linux/sched.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <libgen.h>
#include <sys/xattr.h>
#include <linux/securebits.h>
#include <sys/prctl.h>
#include <sys/signalfd.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

enum { EXIT_STOPPED = 0, EXIT_REFUSED = 65, EXIT_UNRESOLVED = 70 };
#define GUARDIAN_GRANT_NS 10000000000ULL

extern const guardian_manifest guardian_compiled_manifest;

static int report(const char *stage, const guardian_state *state, int code) {
    fprintf(stderr, "autocontrol-owner-guardian: %s operation %u errno %d\n", stage, state->operation,
            state->system_errno);
    return code;
}

/* Every directory above the listener is root's alone, or a race could redirect the bind
 * or the chown that still go by path. */
static bool trusted_parent(const char *path) {
    char copy[sizeof(((struct sockaddr_un *)0)->sun_path)];
    strcpy(copy, path);
    int directory = gj_open_trusted_directory(dirname(copy), 0);
    if (directory < 0) return false;
    close(directory);
    return true;
}

/* POSIX ACL xattr layout (linux/posix_acl_xattr.h), which no libc header declares. */
typedef struct { uint16_t tag, permission; uint32_t id; } acl_entry;
enum { ACL_USER_OBJ = 1, ACL_USER = 2, ACL_GROUP_OBJ = 4, ACL_MASK = 0x10, ACL_OTHER = 0x20 };

/* Every listed client account may connect by name, so a nested-capable payload reaches
 * the guardian without holding any supplementary group: the service gives payloads none. */
#define ACL_USER_LIMIT (GUARDIAN_CLIENT_LIMIT * SERVICE_PAYLOAD_IDS)

/* Entries must be sorted by ID: take the next larger client UID, ranges expanded, each time. */
static bool next_client_uid(const guardian_manifest *manifest, bool first, uint32_t previous, uint32_t *next) {
    bool found = false;
    for (size_t i = 0; i < manifest->client_count; ++i) {
        const guardian_client *client = &manifest->clients[i];
        uint32_t span = client->id_count > 1 ? client->id_count : 1;
        for (uint32_t k = 0; k < span; ++k) {
            uint32_t uid = client->uid + k;
            if ((first || uid > previous) && (!found || uid < *next)) { *next = uid; found = true; }
        }
    }
    return found;
}

static bool grant_clients(const char *path, const guardian_manifest *manifest) {
    static struct { uint32_t version; acl_entry entries[ACL_USER_LIMIT + 4]; } acl;
    acl.version = 2;
    size_t count = 0;
    acl.entries[count++] = (acl_entry){ACL_USER_OBJ, 6, UINT32_MAX};
    uint32_t uid = 0;
    for (bool first = true; next_client_uid(manifest, first, uid, &uid); first = false) {
        if (count > ACL_USER_LIMIT) return false;
        acl.entries[count++] = (acl_entry){ACL_USER, 6, uid};
    }
    acl.entries[count++] = (acl_entry){ACL_GROUP_OBJ, 6, UINT32_MAX};
    acl.entries[count++] = (acl_entry){ACL_MASK, 6, UINT32_MAX};
    acl.entries[count++] = (acl_entry){ACL_OTHER, 0, UINT32_MAX};
    size_t size = sizeof(acl.version) + count * sizeof(acl_entry);
    return lsetxattr(path, "system.posix_acl_access", &acl, size, 0) == 0;
}

/* Only a stale socket at exactly this path is replaced; anything else refuses. */
static int open_listener(const char *path, uint32_t group, const guardian_manifest *manifest) {
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(path) >= sizeof(address.sun_path) || !trusted_parent(path)) return -1;
    strcpy(address.sun_path, path);
    struct stat status;
    if (lstat(path, &status) == 0 && (!S_ISSOCK(status.st_mode) || unlink(path) != 0)) return -1;
    int number = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    if (number < 0) return -1;
    no_error error;
    /* Accepted sockets inherit credential passing; a client frame queued before the
     * service adopts the connection would otherwise arrive without credentials. */
    mode_t previous = umask(0117); /* The socket is born 0660; no chmod by path afterwards. */
    int bound = bind(number, (struct sockaddr *)&address, sizeof(address));
    umask(previous);
    if (bound != 0 || fchownat(AT_FDCWD, path, 0, group, AT_SYMLINK_NOFOLLOW) != 0 ||
        !grant_clients(path, manifest) ||
        listen(number, 64) != 0 || !peer_enable_credentials(number, &error)) {
        close(number);
        return -1;
    }
    return number;
}

/* Exactly what the approved payload drop needs: supplementary groups, GID and UID
 * changes, and emptying the payload's bounding set. Carried across exec as ambient. */
static const int service_capabilities[] = {CAP_SETUID, CAP_SETGID, CAP_SETPCAP};

static bool keep_service_capabilities(void) {
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct data[2] = {{0}, {0}};
    for (size_t i = 0; i < sizeof(service_capabilities) / sizeof(service_capabilities[0]); ++i) {
        uint32_t bit = UINT32_C(1) << (service_capabilities[i] % 32);
        data[service_capabilities[i] / 32].effective |= bit;
        data[service_capabilities[i] / 32].permitted |= bit;
        data[service_capabilities[i] / 32].inheritable |= bit;
    }
    if (syscall(SYS_capset, &header, data) != 0) return false;
    for (size_t i = 0; i < sizeof(service_capabilities) / sizeof(service_capabilities[0]); ++i)
        if (prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_RAISE, service_capabilities[i], 0, 0) != 0) return false;
    return true;
}

/* A code-execution bug in the service reaches no account beyond its payloads: its
 * bounding set holds only its three capabilities, UID 0 confers nothing on exec (NOROOT,
 * locked), exec never raises privileges (no_new_privs), and the identity filter lets the
 * set*id calls name only the service's and the payloads' IDs and forbids user namespaces.
 * Done while still root, before the UID drop, which the filter permits. */
static bool confine_service(const guardian_manifest *manifest) {
    for (unsigned long capability = 0;; ++capability) {
        int present = prctl(PR_CAPBSET_READ, capability, 0, 0, 0);
        if (present < 0) break;
        bool kept = capability == CAP_SETUID || capability == CAP_SETGID || capability == CAP_SETPCAP;
        if (present && !kept && prctl(PR_CAPBSET_DROP, capability, 0, 0, 0) != 0) return false;
    }
    sigset_t none;
    sigemptyset(&none);
    return prctl(PR_SET_SECUREBITS, SECBIT_NOROOT | SECBIT_NOROOT_LOCKED | SECBIT_KEEP_CAPS, 0, 0, 0) == 0 &&
        prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0 && sigprocmask(SIG_SETMASK, &none, NULL) == 0 &&
        guardian_confine_identities(&service_manifest, manifest->service_uid, manifest->service_gid);
}

/* The child keeps only its endpoint on SERVICE_GUARDIAN_FD and becomes the service
 * account before exec, with an empty environment and only its three capabilities. */
static void exec_service(const guardian_manifest *manifest, int channel) {
    if (dup2(channel, SERVICE_GUARDIAN_FD) == SERVICE_GUARDIAN_FD &&
        syscall(SYS_close_range, SERVICE_GUARDIAN_FD + 1U, ~0U, 0) == 0 && setgroups(0, NULL) == 0 &&
        confine_service(manifest) &&
        setresgid(manifest->service_gid, manifest->service_gid, manifest->service_gid) == 0 &&
        setresuid(manifest->service_uid, manifest->service_uid, manifest->service_uid) == 0 &&
        keep_service_capabilities()) {
        char *argv[] = {(char *)manifest->service_executable, NULL}, *env[] = {NULL};
        execve(manifest->service_executable, argv, env);
    }
    _exit(127);
}

static int launch_service(guardian_state *state, int channel, peer_identity *service) {
    int epoch = openat(state->subtree, state->journal.current.epoch, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    int branch = epoch < 0 ? -1 : openat(epoch, state->journal.current.service, O_RDONLY | O_DIRECTORY | O_NOFOLLOW |
                                         O_CLOEXEC);
    int opened = errno;
    if (epoch >= 0) close(epoch);
    if (branch < 0) return opened;
    int pidfd = -1;
    struct clone_args args = {.flags = CLONE_PIDFD | CLONE_INTO_CGROUP, .pidfd = (uintptr_t)&pidfd,
        .exit_signal = SIGCHLD, .cgroup = (uint64_t)branch};
    long child = syscall(SYS_clone3, &args, sizeof(args));
    if (child == 0) exec_service(state->manifest, channel);
    int error = child < 0 ? errno : 0;
    close(branch);
    if (error) return error;
    service->credentials.pid = (pid_t)child;
    return peer_identity_adopt(service, pidfd) ? 0 : EPROTO;
}

static bool wait_frame(int channel, const peer_identity *service, guardian_grant *frame, uint64_t limit) {
    struct pollfd event = {.fd = channel, .events = POLLIN};
    while (owner_now() < limit) {
        if (poll(&event, 1, 100) <= 0) continue;
        received_packet packet;
        no_error error;
        memset(frame, 0, sizeof(*frame));
        if (!packet_receive(channel, frame, sizeof(*frame), MSG_DONTWAIT, &packet, &error)) return false;
        bool authentic = packet_authenticated(&packet, service, 0) && packet.bytes == (ssize_t)sizeof(*frame) &&
            frame->magic == SERVICE_MAGIC && frame->version == SERVICE_VERSION;
        packet_release(&packet);
        return authentic;
    }
    return false;
}

static bool send_grant(int channel, const guardian_grant *grant, int epoch) {
    int rights[GRANT_RIGHTS] = {[GRANT_EPOCH_DIRECTORY] = epoch};
    union { struct cmsghdr align; char buffer[CMSG_SPACE(sizeof(rights))]; } control;
    memset(&control, 0, sizeof(control));
    struct iovec vector = {.iov_base = (void *)grant, .iov_len = sizeof(*grant)};
    struct msghdr header = {.msg_iov = &vector, .msg_iovlen = 1, .msg_control = control.buffer,
        .msg_controllen = sizeof(control.buffer)};
    struct cmsghdr *message = CMSG_FIRSTHDR(&header);
    message->cmsg_level = SOL_SOCKET; message->cmsg_type = SCM_RIGHTS; message->cmsg_len = CMSG_LEN(sizeof(rights));
    memcpy(CMSG_DATA(message), rights, sizeof(rights));
    return sendmsg(channel, &header, MSG_NOSIGNAL) == (ssize_t)sizeof(*grant);
}

/* Request, grant, acknowledgment: each frame must come from the cloned service. */
static bool grant_epoch(guardian_state *state, int channel, const peer_identity *service, uint32_t slice,
                        guardian_grant *granted) {
    uint64_t limit = owner_now() + GUARDIAN_GRANT_NS;
    guardian_grant frame;
    if (!wait_frame(channel, service, &frame, limit) || frame.kind != GRANT_REQUESTED) return false;
    no_id epoch;
    memcpy(&epoch.high, state->manifest->installation, sizeof(epoch.high));
    epoch.low = state->journal.current.counter;
    guardian_grant grant = {SERVICE_MAGIC, SERVICE_VERSION, GRANT_EPOCH, epoch, state->journal.current.sequence,
                            slice, 0};
    if (!send_grant(channel, &grant, state->epoch)) return false;
    *granted = grant;
    return wait_frame(channel, service, &frame, limit) && frame.kind == GRANT_ACKNOWLEDGED &&
        frame.epoch.high == epoch.high && frame.epoch.low == epoch.low && frame.generation == grant.generation;
}

/* One running epoch: its service, the guardian's end of its channel and its grant. A
 * retiring epoch keeps its channel open: the service would read a closed one as guardian
 * loss and drain the leases it still serves. */
typedef struct {
    peer_identity service;
    int channel;
    guardian_grant grant;
    char epoch[GJ_COMPONENT_BYTES];
    uint64_t counter, started_ns;
    uint32_t slice; /* Of every payload range; no other running epoch uses it. */
} running_epoch;

/* Epochs that may retire at once beside the current one: every other slice. Builds for the
 * acceptance may lower it to exercise a handover that has to wait. */
#ifndef GUARDIAN_RETIRING_LIMIT
#define GUARDIAN_RETIRING_LIMIT (SERVICE_PAYLOAD_SLICES - 1)
#endif

typedef struct {
    running_epoch current;
    running_epoch retiring[GUARDIAN_RETIRING_LIMIT];
} running_set;

static void running_init(running_epoch *run) {
    *run = (running_epoch){.service = {.pidfd = {FD_EMPTY, -1}}, .channel = -1};
}

static bool running_live(const running_epoch *run) { return run->service.pidfd.state == FD_OWNED; }

/* Whatever ended the epoch, the service is killed if still alive, waited for and its
 * exit logged: no zombie keeps a PID, its pids charge or a dying service cgroup. */
static void reap_service(const peer_identity *service) {
    if (service->pidfd.state != FD_OWNED) return;
    syscall(SYS_pidfd_send_signal, service->pidfd.number, SIGKILL, NULL, 0);
    siginfo_t info;
    memset(&info, 0, sizeof(info));
    int rc;
    do { rc = waitid(P_PIDFD, (id_t)service->pidfd.number, &info, WEXITED); } while (rc < 0 && errno == EINTR);
    if (rc == 0)
        fprintf(stderr, "autocontrol-owner-guardian: service ended (%s %d)\n",
                info.si_code == CLD_EXITED ? "exit" : "signal", info.si_status);
}

static void running_close(running_epoch *run) {
    reap_service(&run->service);
    service_close_fd(&run->service.pidfd);
    if (run->channel >= 0) close(run->channel);
    run->channel = -1;
}

static uint64_t monotonic_ns(void) {
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    return (uint64_t)value.tv_sec * 1000000000ULL + (uint64_t)value.tv_nsec;
}

static bool slice_in_use(const running_set *set, uint32_t slice) {
    if (running_live(&set->current) && set->current.slice == slice) return true;
    for (size_t i = 0; i < GUARDIAN_RETIRING_LIMIT; ++i)
        if (running_live(&set->retiring[i]) && set->retiring[i].slice == slice) return true;
    return false;
}

typedef enum { SLICE_READY, SLICE_WAIT, SLICE_NONE } slice_choice;

/* A slice no running epoch uses, not tainted and not being purged. Never waits: WAIT means
 * a purge or a retiring epoch still holds the only usable ones, NONE that every slice not
 * in use is tainted. */
static slice_choice pick_slice(const guardian_state *state, const running_set *set, uint32_t *slice) {
    bool usable = false;
    for (uint32_t s = 0; s < SERVICE_PAYLOAD_SLICES; ++s) {
        if (state->tainted[s]) continue;
        usable = true;
        if (!slice_in_use(set, s) && state->purging[s] < 0 && !state->repurge[s]) { *slice = s; return SLICE_READY; }
    }
    return usable ? SLICE_WAIT : SLICE_NONE;
}

/* Launches the journal's current epoch: service, grant with its slice, then ACTIVE. */
static bool start_epoch(guardian_state *state, running_epoch *run, uint32_t slice) {
    running_init(run);
    run->slice = slice;
    int pair[2];
    if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, pair) != 0) {
        state->operation = 30; state->system_errno = errno;
        return false;
    }
    no_error error;
    int launch_error = launch_service(state, pair[1], &run->service);
    close(pair[1]);
    run->channel = pair[0];
    memcpy(run->epoch, state->journal.current.epoch, sizeof(run->epoch));
    run->counter = state->journal.current.counter;
    run->started_ns = monotonic_ns();
    if (!launch_error && peer_enable_credentials(pair[0], &error) &&
        grant_epoch(state, pair[0], &run->service, slice, &run->grant) &&
        gj_mark(&state->journal, GJ_ACTIVE) == GJ_ERROR_NONE)
        return true;
    state->operation = 31; state->system_errno = launch_error;
    return false;
}

/* One frame from a running service; only GRANT_RETIRING is expected after the grant.
 * False on loss or a frame the service did not send. `kind` is 0 when nothing waited. */
static bool service_frame(const running_epoch *run, uint16_t *kind) {
    guardian_grant frame;
    received_packet packet;
    no_error error;
    memset(&frame, 0, sizeof(frame));
    *kind = 0;
    if (!packet_receive(run->channel, &frame, sizeof(frame), MSG_DONTWAIT, &packet, &error))
        return error.system_errno == EAGAIN || error.system_errno == EWOULDBLOCK;
    bool authentic = packet.bytes == (ssize_t)sizeof(frame) && packet_authenticated(&packet, &run->service, 0) &&
        frame.magic == SERVICE_MAGIC && frame.version == SERVICE_VERSION && frame.epoch.low == run->grant.epoch.low &&
        frame.epoch.high == run->grant.epoch.high && frame.generation == run->grant.generation;
    packet_release(&packet);
    if (authentic) *kind = frame.kind;
    return authentic;
}

static running_epoch *free_retiring_slot(running_set *set) {
    for (size_t i = 0; i < GUARDIAN_RETIRING_LIMIT; ++i) if (!running_live(&set->retiring[i])) return &set->retiring[i];
    return NULL;
}

typedef enum { HANDOVER_WAIT, HANDOVER_DONE, HANDOVER_RESTART, HANDOVER_FAILED } handover_result;

/* The current epoch is spent but serves open leases: it keeps them as a retiring epoch, no
 * longer journaled (a crash sweeps it), and the next epoch starts beside it. WAIT when no
 * retiring slot or clean slice is free yet; RESTART when the next epoch could not be
 * planned or started (it is retried, the retiring ones keep running); FAILED when the
 * journal or a reclaim failed. */
static handover_result hand_over(guardian_state *state, running_set *set) {
    running_epoch *slot = free_retiring_slot(set);
    uint32_t slice;
    if (!slot || pick_slice(state, set, &slice) != SLICE_READY) return HANDOVER_WAIT;
    *slot = set->current;
    running_init(&set->current);
    if (gj_mark(&state->journal, GJ_RECOVERING) != GJ_ERROR_NONE || gj_mark(&state->journal, GJ_CLEAN) != GJ_ERROR_NONE)
        return HANDOVER_FAILED;
    guardian_result next = guardian_next_epoch(state);
    if (next != GUARDIAN_READY) return next == GUARDIAN_REFUSED ? HANDOVER_RESTART : HANDOVER_FAILED;
    return start_epoch(state, &set->current, slice) ? HANDOVER_DONE : HANDOVER_RESTART;
}

typedef enum { LOOP_STOPPED, LOOP_REFUSED, LOOP_UNRESOLVED } loop_result;

/* Starts the planned epoch once a slice is free. While a purge or a retiring epoch holds
 * the slices, there is no current epoch: clients are held until one starts. */
static loop_result start_when_free(guardian_state *state, running_set *set, bool *waiting) {
    uint32_t slice;
    slice_choice choice = pick_slice(state, set, &slice);
    *waiting = choice == SLICE_WAIT;
    if (choice == SLICE_NONE) return LOOP_UNRESOLVED; /* Every slice not in use is tainted. */
    if (choice == SLICE_WAIT) return LOOP_STOPPED;
    return start_epoch(state, &set->current, slice) ? LOOP_STOPPED : LOOP_REFUSED;
}

/* A start that failed, and a service that ends within a second of starting, are retried
 * after 1, 2, 4 ... up to 30 seconds. The wait is the main poll's timeout, so a stop
 * request, retiring epochs and purges are answered meanwhile. */
typedef struct { unsigned failures; uint64_t retry_at; } restart_plan;

static loop_result retry_later(restart_plan *plan) {
    ++plan->failures;
    uint64_t wait_ms = plan->failures > 5 ? 30000 : 1000ULL << (plan->failures - 1);
    plan->retry_at = monotonic_ns() + wait_ms * 1000000ULL;
    return LOOP_STOPPED;
}

/* The retry's deadline; and while a slice waits for a purge to run again with no purge child
 * to wake the loop (one ran here, a fork having failed), a second. */
static int poll_timeout(const guardian_state *state, const restart_plan *plan) {
    int timeout = -1;
    for (int s = 0; s < SERVICE_PAYLOAD_SLICES; ++s)
        if (state->repurge[s] && state->purging[s] < 0 && !state->tainted[s]) timeout = 1000;
    if (!plan->retry_at) return timeout;
    uint64_t now = monotonic_ns();
    int retry = now >= plan->retry_at ? 0 : (int)((plan->retry_at - now + 999999) / 1000000);
    return timeout >= 0 && timeout < retry ? timeout : retry;
}

/* Kills and reclaims the current epoch, whatever ended it. Its slice is purged only when
 * a service was launched for it. */
static bool end_current(guardian_state *state, running_set *set) {
    bool launched = set->current.started_ns != 0;
    int slice = (int)set->current.slice;
    running_close(&set->current);
    running_init(&set->current);
    return guardian_recover(state, launched ? slice : GUARDIAN_PURGE_NONE) == GUARDIAN_READY;
}

/* A refused start is reclaimed and retried later; anything else stands. */
static loop_result settle_start(guardian_state *state, running_set *set, restart_plan *plan, loop_result started) {
    if (started != LOOP_REFUSED) return started;
    return end_current(state, set) ? retry_later(plan) : LOOP_UNRESOLVED;
}

/* Plans the next epoch and starts it as soon as a slice is free. */
static loop_result begin_next(guardian_state *state, running_set *set, restart_plan *plan, bool *waiting) {
    guardian_result next = guardian_next_epoch(state);
    loop_result started = next == GUARDIAN_READY ? start_when_free(state, set, waiting) :
        next == GUARDIAN_REFUSED ? LOOP_REFUSED : LOOP_UNRESOLVED;
    return settle_start(state, set, plan, started);
}

/* The current epoch ended on its own: reclaim it and start the next, at once after a run
 * of a second or more, after the backoff when it was crashing. */
static loop_result current_ended(guardian_state *state, running_set *set, restart_plan *plan, bool *waiting) {
    bool quick = monotonic_ns() - set->current.started_ns < 1000000000ULL;
    if (!end_current(state, set)) return LOOP_UNRESOLVED;
    if (quick) return retry_later(plan);
    plan->failures = 0;
    return begin_next(state, set, plan, waiting);
}

static bool any_retiring(const running_set *set) {
    for (size_t i = 0; i < GUARDIAN_RETIRING_LIMIT; ++i) if (running_live(&set->retiring[i])) return true;
    return false;
}

static const service_policy *const service_manifest_for_routing = &service_manifest;

/* Clients accepted while no current epoch ran. */
#define GUARDIAN_HELD_LIMIT 32
typedef struct { int connections[GUARDIAN_HELD_LIMIT]; size_t count; } held_clients;
typedef struct { const running_set *set; const held_clients *held; } routing;

/* A helper's own connection (a nested parent opening children) goes to the epoch that runs
 * its slice, retiring or current: only that service knows the parent's record. Anyone else
 * goes to the current epoch, is held while none runs, and is dropped once the held clients
 * are full: the listener stays read for helpers of retiring epochs. */
static guardian_route_result route_client(void *context, uint32_t uid, guardian_target *target) {
    const routing *route = context;
    const running_set *set = route->set;
    const running_epoch *chosen = &set->current;
    const service_policy *service = service_manifest_for_routing;
    for (size_t i = 0; service && i < service->policy_count; ++i) {
        uint32_t base = service->policies[i].payload_uid;
        if (uid < base || uid - base >= SERVICE_PAYLOAD_IDS) continue;
        uint32_t slice = (uid - base) / SERVICE_EPOCH_IDS;
        for (size_t r = 0; r < GUARDIAN_RETIRING_LIMIT; ++r)
            if (running_live(&set->retiring[r]) && set->retiring[r].slice == slice) chosen = &set->retiring[r];
        break;
    }
    if (!running_live(chosen)) return route->held->count < GUARDIAN_HELD_LIMIT ? ROUTE_HOLD : ROUTE_DROP;
    *target = (guardian_target){chosen->channel, chosen->grant.epoch, chosen->grant.generation};
    return ROUTE_SEND;
}

static void release_held(held_clients *held, const running_epoch *current) {
    for (size_t i = 0; i < held->count; ++i) {
        if (current) guardian_send_connection(current->channel, held->connections[i], current->grant.epoch,
                                              current->grant.generation);
        close(held->connections[i]);
    }
    held->count = 0;
}

/* Accepts one client. True when the current epoch's channel failed. */
static bool forward_client(const guardian_state *state, int listener, running_set *set, held_clients *held) {
    int used = -1, connection = -1;
    routing route = {set, held};
    guardian_forward_result forwarded = guardian_forward_routed(listener, state->manifest, route_client, &route,
                                                                &used, &connection);
    if (forwarded == FORWARD_HELD) held->connections[held->count++] = connection;
    return forwarded == FORWARD_CHANNEL_FAILED && running_live(&set->current) && used == set->current.channel;
}

enum { EVENT_SIGNALS, EVENT_LISTENER, EVENT_CURRENT, EVENT_CHANNEL, EVENT_RETIRING,
       EVENT_PURGE = EVENT_RETIRING + GUARDIAN_RETIRING_LIMIT, EVENT_COUNT = EVENT_PURGE + SERVICE_PAYLOAD_SLICES };

/* Reaps retiring epochs whose service ended and purge children that finished. */
static bool settle_finished(guardian_state *state, running_set *set, const struct pollfd *events) {
    for (size_t i = 0; i < GUARDIAN_RETIRING_LIMIT; ++i) {
        if (!events[EVENT_RETIRING + i].revents || !running_live(&set->retiring[i])) continue;
        running_close(&set->retiring[i]);
        if (guardian_reclaim_retired(state, set->retiring[i].epoch, (int)set->retiring[i].slice) != GUARDIAN_READY)
            return false;
        running_init(&set->retiring[i]);
    }
    for (int s = 0; s < SERVICE_PAYLOAD_SLICES; ++s)
        if (events[EVENT_PURGE + s].revents) guardian_purge_reap(state, s);
    guardian_purge_resume(state);
    return true;
}

/* The supervisor's state between polls. GRANT_RETIRING arrives once: while no retiring slot
 * or clean slice is free it stays pending and is acted on as soon as one is. `waiting`: the
 * next epoch is planned but no slice was free; it starts once a purge or a retiring epoch
 * ends. */
typedef struct { bool retire_pending, waiting; restart_plan plan; held_clients held; } supervision;

/* What the current epoch's events ask for: its end, or its handover once it is spent. */
static loop_result serve_current(guardian_state *state, running_set *set, const struct pollfd *events,
                                 supervision *run) {
    bool ended = events[EVENT_CURRENT].revents != 0;
    uint16_t kind = 0;
    if (!ended && events[EVENT_CHANNEL].revents) ended = !service_frame(&set->current, &kind);
    if (ended) {
        run->retire_pending = false;
        return current_ended(state, set, &run->plan, &run->waiting);
    }
    if (kind == GRANT_RETIRING) run->retire_pending = true;
    if (!run->retire_pending) return LOOP_STOPPED;
    handover_result handed = hand_over(state, set);
    if (handed == HANDOVER_WAIT) return LOOP_STOPPED;
    run->retire_pending = false;
    if (handed == HANDOVER_FAILED) return LOOP_UNRESOLVED;
    return handed == HANDOVER_RESTART ? settle_start(state, set, &run->plan, LOOP_REFUSED) : LOOP_STOPPED;
}

static loop_result supervise_loop(guardian_state *state, int signals, int listener, running_set *set,
                                  supervision *run) {
    for (;;) {
        bool live = running_live(&set->current);
        if (live && run->held.count) release_held(&run->held, &set->current);
        bool accepting = live || any_retiring(set);
        struct pollfd events[EVENT_COUNT] = {
            [EVENT_SIGNALS] = {.fd = signals, .events = POLLIN},
            [EVENT_LISTENER] = {.fd = accepting ? listener : -1, .events = POLLIN},
            [EVENT_CURRENT] = {.fd = live ? set->current.service.pidfd.number : -1, .events = POLLIN},
            [EVENT_CHANNEL] = {.fd = live ? set->current.channel : -1, .events = POLLIN}};
        for (size_t i = 0; i < GUARDIAN_RETIRING_LIMIT; ++i)
            events[EVENT_RETIRING + i] = (struct pollfd){
                .fd = running_live(&set->retiring[i]) ? set->retiring[i].service.pidfd.number : -1, .events = POLLIN};
        for (int s = 0; s < SERVICE_PAYLOAD_SLICES; ++s)
            events[EVENT_PURGE + s] = (struct pollfd){.fd = state->purging[s], .events = POLLIN};
        int timeout = poll_timeout(state, &run->plan), watch = guardian_purge_watch(state);
        if (watch >= 0 && (timeout < 0 || watch < timeout)) timeout = watch;
        if (poll(events, EVENT_COUNT, timeout) < 0) {
            if (errno == EINTR) continue;
            return LOOP_REFUSED;
        }
        if (events[EVENT_SIGNALS].revents) return LOOP_STOPPED;
        if (!settle_finished(state, set, events)) return LOOP_UNRESOLVED;
        loop_result step = LOOP_STOPPED;
        if (run->plan.retry_at && monotonic_ns() >= run->plan.retry_at) {
            run->plan.retry_at = 0;
            step = begin_next(state, set, &run->plan, &run->waiting);
        } else if (run->waiting) {
            step = settle_start(state, set, &run->plan, start_when_free(state, set, &run->waiting));
        } else if (live) {
            step = serve_current(state, set, events, run);
        }
        if (step == LOOP_STOPPED && events[EVENT_LISTENER].revents & POLLIN &&
            forward_client(state, listener, set, &run->held))
            step = current_ended(state, set, &run->plan, &run->waiting);
        if (step != LOOP_STOPPED) return step;
    }
}

/* Forwards verified clients, rolls epochs over, reclaims retiring ones when their services
 * end and reaps purges, until asked to stop or something fails. */
static loop_result supervise(guardian_state *state, int signals, int listener, running_set *set, bool waiting) {
    supervision run = {.retire_pending = false, .waiting = waiting};
    loop_result result = supervise_loop(state, signals, listener, set, &run);
    release_held(&run.held, NULL);
    return result;
}

/* Kills and reclaims every running epoch first, then ends any purge without waiting: the
 * next start purges every slice before it serves. */
static guardian_result shut_down(guardian_state *state, running_set *set) {
    running_close(&set->current);
    guardian_result recovered = guardian_recover(state, GUARDIAN_PURGE_NONE);
    for (size_t i = 0; i < GUARDIAN_RETIRING_LIMIT; ++i) {
        if (!running_live(&set->retiring[i])) continue;
        running_close(&set->retiring[i]);
        if (guardian_reclaim_retired(state, set->retiring[i].epoch, GUARDIAN_PURGE_NONE) != GUARDIAN_READY)
            recovered = GUARDIAN_UNRESOLVED;
    }
    guardian_purge_abandon(state);
    return recovered;
}

/* Helpers start with a core limit of 0, which a pipe core_pattern handler receives but the
 * kernel does not enforce: systemd-coredump honours it and apport's reports land in the
 * purged /var/crash; any other handler may keep a helper's memory where the next helper with
 * the same ID can read it. */
static void warn_core_pattern(void) {
    FILE *pattern = fopen("/proc/sys/kernel/core_pattern", "re");
    char line[256] = "";
    if (pattern) {
        if (!fgets(line, sizeof(line), pattern)) line[0] = 0;
        fclose(pattern);
    }
    if (line[0] == '|' && !strstr(line, "systemd-coredump") && !strstr(line, "apport"))
        fprintf(stderr, "autocontrol-owner-guardian: core_pattern pipes to a handler this guardian does not know; "
                        "it may keep crashed helpers' memory\n");
}

int main(void) {
    sigset_t stopping;
    sigemptyset(&stopping);
    sigaddset(&stopping, SIGTERM);
    sigaddset(&stopping, SIGINT);
    signal(SIGPIPE, SIG_IGN);
    if (sigprocmask(SIG_BLOCK, &stopping, NULL) != 0) return EXIT_REFUSED;
    int signals = signalfd(-1, &stopping, SFD_CLOEXEC);
    guardian_state state;
    warn_core_pattern();
    if (!guardian_manifest_valid(&guardian_compiled_manifest)) {
        fprintf(stderr, "autocontrol-owner-guardian: the compiled manifest is invalid\n");
        return EXIT_REFUSED;
    }
    guardian_result prepared = guardian_prepare(&state, &guardian_compiled_manifest);
    if (prepared != GUARDIAN_READY) {
        guardian_close(&state);
        return report("prepare", &state, prepared == GUARDIAN_REFUSED ? EXIT_REFUSED : EXIT_UNRESOLVED);
    }
    int listener = signals < 0 ? -1 : open_listener(state.manifest->listener_path, state.manifest->listener_gid,
                                                    state.manifest);
    running_set set;
    running_init(&set.current);
    for (size_t i = 0; i < GUARDIAN_RETIRING_LIMIT; ++i) running_init(&set.retiring[i]);
    loop_result result = LOOP_REFUSED;
    state.purge_async = true;
    guardian_purge_resume(&state); /* A startup purge that stopped short runs again, in a child. */
    if (listener < 0) { state.operation = 30; state.system_errno = errno; }
    else {
        uint32_t slice;
        slice_choice choice = pick_slice(&state, &set, &slice);
        if (choice == SLICE_NONE) result = LOOP_UNRESOLVED;
        else if (choice == SLICE_WAIT) result = supervise(&state, signals, listener, &set, true);
        else if (start_epoch(&state, &set.current, slice)) result = supervise(&state, signals, listener, &set, false);
    }
    if (listener >= 0) {
        close(listener);
        unlink(state.manifest->listener_path);
    }
    guardian_result recovered = shut_down(&state, &set);
    guardian_close(&state);
    if (recovered != GUARDIAN_READY) return report("recover", &state, EXIT_UNRESOLVED);
    if (result == LOOP_UNRESOLVED) return report("serve", &state, EXIT_UNRESOLVED);
    return result == LOOP_STOPPED ? EXIT_STOPPED : report("serve", &state, EXIT_REFUSED);
}
