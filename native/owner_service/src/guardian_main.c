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
#include <sys/prctl.h>
#include <sys/signalfd.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/un.h>
#include <unistd.h>

enum { EXIT_STOPPED = 0, EXIT_REFUSED = 65, EXIT_UNRESOLVED = 70 };
#define GUARDIAN_GRANT_NS 10000000000ULL

extern const guardian_manifest guardian_compiled_manifest;

static int report(const char *stage, const guardian_state *state, int code) {
    fprintf(stderr, "autocontrol-owner-guardian: %s operation %u errno %d\n", stage, state->operation,
            state->system_errno);
    return code;
}

/* Only a stale socket at exactly this path is replaced; anything else refuses. */
static int open_listener(const char *path, uint32_t group) {
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    if (strlen(path) >= sizeof(address.sun_path)) return -1;
    strcpy(address.sun_path, path);
    struct stat status;
    if (lstat(path, &status) == 0 && (!S_ISSOCK(status.st_mode) || unlink(path) != 0)) return -1;
    int number = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    if (number < 0) return -1;
    no_error error;
    /* Accepted sockets inherit credential passing; a client frame queued before the
     * service adopts the connection would otherwise arrive without credentials. */
    if (bind(number, (struct sockaddr *)&address, sizeof(address)) != 0 || chown(path, 0, group) != 0 ||
        chmod(path, 0660) != 0 ||
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

/* The child keeps only its endpoint on SERVICE_GUARDIAN_FD and becomes the service
 * account before exec, with an empty environment and only its three capabilities. */
static void exec_service(const guardian_manifest *manifest, int channel) {
    if (dup2(channel, SERVICE_GUARDIAN_FD) == SERVICE_GUARDIAN_FD &&
        syscall(SYS_close_range, SERVICE_GUARDIAN_FD + 1U, ~0U, 0) == 0 && setgroups(0, NULL) == 0 &&
        prctl(PR_SET_KEEPCAPS, 1, 0, 0, 0) == 0 &&
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

/* Forwards verified clients until the service exits, the channel fails, or the
 * supervisor asks the guardian to stop. */
static void supervise(const guardian_state *state, const peer_identity *service, int signals, int listener,
                      int channel, const guardian_grant *grant) {
    struct pollfd events[3] = {{.fd = service->pidfd.number, .events = POLLIN}, {.fd = signals, .events = POLLIN},
                               {.fd = listener, .events = POLLIN}};
    for (;;) {
        if (poll(events, 3, -1) < 0) { if (errno == EINTR) continue; return; }
        if (events[0].revents || events[1].revents) return;
        if (events[2].revents & POLLIN &&
            guardian_forward(listener, channel, state->manifest, grant->epoch, grant->generation) ==
            FORWARD_CHANNEL_FAILED) return;
    }
}

static int serve(guardian_state *state, int signals) {
    int listener = open_listener(state->manifest->listener_path, state->manifest->listener_gid);
    int pair[2] = {-1, -1};
    if (listener < 0 || socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, pair) != 0) {
        state->operation = 30; state->system_errno = errno;
        if (listener >= 0) close(listener);
        return EXIT_REFUSED;
    }
    peer_identity service = {.pidfd = {FD_EMPTY, -1}};
    no_error error;
    int launch_error = launch_service(state, pair[1], &service);
    close(pair[1]);
    guardian_grant granted;
    if (!launch_error && peer_enable_credentials(pair[0], &error) && grant_epoch(state, pair[0], &service, &granted) &&
        gj_mark(&state->journal, GJ_ACTIVE) == GJ_ERROR_NONE)
        supervise(state, &service, signals, listener, pair[0], &granted);
    else { state->operation = 31; state->system_errno = launch_error; }
    close(pair[0]);
    close(listener);
    unlink(state->manifest->listener_path);
    service_close_fd(&service.pidfd);
    return EXIT_STOPPED;
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
    int served = signals < 0 ? EXIT_REFUSED : serve(&state, signals);
    /* Whatever happened, the epoch is reclaimed before the guardian exits. */
    guardian_result recovered = guardian_recover(&state);
    guardian_close(&state);
    if (recovered != GUARDIAN_READY) return report("recover", &state, EXIT_UNRESOLVED);
    return served == EXIT_STOPPED ? EXIT_STOPPED : report("serve", &state, served);
}
