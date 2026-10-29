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
static bool grant_epoch(guardian_state *state, int channel, const peer_identity *service, guardian_grant *granted) {
    uint64_t limit = owner_now() + GUARDIAN_GRANT_NS;
    guardian_grant frame;
    if (!wait_frame(channel, service, &frame, limit) || frame.kind != GRANT_REQUESTED) return false;
    no_id epoch;
    memcpy(&epoch.high, state->manifest->installation, sizeof(epoch.high));
    epoch.low = state->journal.current.counter;
    guardian_grant grant = {SERVICE_MAGIC, SERVICE_VERSION, GRANT_EPOCH, epoch, state->journal.current.sequence};
    if (!send_grant(channel, &grant, state->epoch)) return false;
    *granted = grant;
    return wait_frame(channel, service, &frame, limit) && frame.kind == GRANT_ACKNOWLEDGED &&
        frame.epoch.high == epoch.high && frame.epoch.low == epoch.low && frame.generation == grant.generation;
}

typedef enum { SERVED_SERVICE_ENDED, SERVED_STOP_REQUESTED, SERVED_FAILED } served_result;

/* Forwards verified clients until the service exits, the channel fails, or the
 * supervisor asks the guardian to stop. */
static served_result supervise(const guardian_state *state, const peer_identity *service, int signals,
                               int listener, int channel, const guardian_grant *grant) {
    struct pollfd events[3] = {{.fd = service->pidfd.number, .events = POLLIN}, {.fd = signals, .events = POLLIN},
                               {.fd = listener, .events = POLLIN}};
    for (;;) {
        if (poll(events, 3, -1) < 0) { if (errno == EINTR) continue; return SERVED_FAILED; }
        if (events[1].revents) return SERVED_STOP_REQUESTED;
        if (events[0].revents) return SERVED_SERVICE_ENDED;
        if (events[2].revents & POLLIN &&
            guardian_forward(listener, channel, state->manifest, grant->epoch, grant->generation) ==
            FORWARD_CHANNEL_FAILED) return SERVED_SERVICE_ENDED;
    }
}

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

static uint64_t monotonic_ns(void) {
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    return (uint64_t)value.tv_sec * 1000000000ULL + (uint64_t)value.tv_nsec;
}

/* A service that ends within a second of starting is crashing: wait a second before the
 * next epoch, still answering a stop request at once. True when asked to stop. */
static bool back_off(int signals) {
    struct pollfd event = {.fd = signals, .events = POLLIN};
    int rc;
    do { rc = poll(&event, 1, 1000); } while (rc < 0 && errno == EINTR);
    return rc > 0;
}

static served_result serve(guardian_state *state, int signals) {
    int listener = open_listener(state->manifest->listener_path, state->manifest->listener_gid, state->manifest);
    int pair[2] = {-1, -1};
    if (listener < 0 || socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, pair) != 0) {
        state->operation = 30; state->system_errno = errno;
        if (listener >= 0) close(listener);
        return SERVED_FAILED;
    }
    peer_identity service = {.pidfd = {FD_EMPTY, -1}};
    no_error error;
    int launch_error = launch_service(state, pair[1], &service);
    close(pair[1]);
    guardian_grant granted;
    served_result result = SERVED_FAILED;
    if (!launch_error && peer_enable_credentials(pair[0], &error) && grant_epoch(state, pair[0], &service, &granted) &&
        gj_mark(&state->journal, GJ_ACTIVE) == GJ_ERROR_NONE)
        result = supervise(state, &service, signals, listener, pair[0], &granted);
    else { state->operation = 31; state->system_errno = launch_error; }
    close(pair[0]);
    close(listener);
    unlink(state->manifest->listener_path);
    reap_service(&service);
    service_close_fd(&service.pidfd);
    return result;
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
    guardian_result prepared = guardian_prepare(&state, &guardian_compiled_manifest);
    if (prepared != GUARDIAN_READY) {
        guardian_close(&state);
        return report("prepare", &state, prepared == GUARDIAN_REFUSED ? EXIT_REFUSED : EXIT_UNRESOLVED);
    }
    if (signals < 0) {
        guardian_recover(&state);
        guardian_close(&state);
        return EXIT_REFUSED;
    }
    /* A service that drained its spent epoch ends normally: reclaim it and grant the next.
     * A stop request or a failure reclaims the epoch and leaves. */
    for (;;) {
        uint64_t started = monotonic_ns();
        served_result served = serve(&state, signals);
        guardian_result recovered = guardian_recover(&state);
        if (recovered != GUARDIAN_READY) {
            guardian_close(&state);
            return report("recover", &state, EXIT_UNRESOLVED);
        }
        if (served == SERVED_STOP_REQUESTED) break;
        if (served == SERVED_SERVICE_ENDED && monotonic_ns() - started < 1000000000ULL && back_off(signals)) break;
        if (served == SERVED_FAILED) {
            guardian_close(&state);
            return report("serve", &state, EXIT_REFUSED);
        }
        guardian_result next = guardian_next_epoch(&state);
        if (next != GUARDIAN_READY) {
            guardian_close(&state);
            return report("rollover", &state, next == GUARDIAN_REFUSED ? EXIT_REFUSED : EXIT_UNRESOLVED);
        }
    }
    guardian_close(&state);
    return EXIT_STOPPED;
}
