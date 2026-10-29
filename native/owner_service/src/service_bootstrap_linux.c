#define _GNU_SOURCE
#include "native_service.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/magic.h>
#include <poll.h>
#include <string.h>
#include <sys/pidfd.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <unistd.h>

/* The guardian is the only authority source: a root-owned supervisor hands the
 * service one inherited SOCK_SEQPACKET endpoint and grants a recovered epoch over
 * it. No path, flag or environment value can stand in for that grant. */

static bool socket_kind(int number, int type, int listening) {
    int value;
    socklen_t length = sizeof(value);
    if (getsockopt(number, SOL_SOCKET, SO_DOMAIN, &value, &length) == -1 || value != AF_UNIX) return false;
    length = sizeof(value);
    if (getsockopt(number, SOL_SOCKET, SO_TYPE, &value, &length) == -1 || value != type) return false;
    length = sizeof(value);
    return getsockopt(number, SOL_SOCKET, SO_ACCEPTCONN, &value, &length) == 0 && value == listening;
}

static bool owned_by_service(int directory, const char *name) {
    struct stat status;
    return fstatat(directory, name, &status, AT_SYMLINK_NOFOLLOW | (name[0] ? 0 : AT_EMPTY_PATH)) == 0 &&
        status.st_uid == geteuid();
}

static bool control_empty(int directory, const char *name) {
    int number;
    do { number = openat(directory, name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW); } while (number < 0 && errno == EINTR);
    if (number < 0) return false;
    owned_fd file = {FD_OWNED, number};
    char byte;
    ssize_t count;
    do { count = read(number, &byte, 1); } while (count < 0 && errno == EINTR);
    return service_close_fd(&file) && count == 0;
}

/* The documented cgroup v2 delegation contract: the directory and its procs,
 * threads and subtree_control files belong to the delegatee, and the fresh epoch
 * holds no task. Necessary evidence only; exclusivity is the guardian's duty. */
static bool delegated_epoch(int directory, uint64_t *device) {
    struct statfs filesystem;
    struct stat status;
    if (fstatfs(directory, &filesystem) == -1 || filesystem.f_type != CGROUP2_SUPER_MAGIC ||
        fstat(directory, &status) == -1 || !S_ISDIR(status.st_mode)) return false;
    static const char *const controls[] = {"", "cgroup.procs", "cgroup.threads", "cgroup.subtree_control"};
    for (size_t i = 0; i < sizeof(controls) / sizeof(controls[0]); ++i)
        if (!owned_by_service(directory, controls[i])) return false;
    if (!control_empty(directory, "cgroup.procs")) return false;
    *device = (uint64_t)status.st_dev;
    return true;
}

/* Readiness needs the kernel identity primitives the issuer relies on. There is
 * no credential-only fallback. */
static bool kernel_supported(const peer_identity *guardian) {
    struct pidfd_info info = {.mask = PIDFD_INFO_CGROUPID};
    return ioctl(guardian->pidfd.number, PIDFD_GET_INFO, &info) == 0 && (info.mask & PIDFD_INFO_CGROUPID);
}

static bool wait_readable(int number, no_deadline deadline) {
    for (;;) {
        uint64_t now = owner_now();
        if (now >= deadline.monotonic_ns) return false;
        uint64_t remaining = (deadline.monotonic_ns - now) / 1000000 + 1;
        struct pollfd event = {.fd = number, .events = POLLIN};
        int rc = poll(&event, 1, remaining > 1000 ? 1000 : (int)remaining);
        if (rc > 0) return true;
        if (rc < 0 && errno != EINTR) return false;
    }
}

static bootstrap_result unwind(service_state *service, no_error *error, no_error failure) {
    *error = failure;
    if (service->runtime) {
        no_error ignored;
        if (!no_runtime_shutdown(&service->runtime, (no_deadline){owner_now() + 1000000000ULL}, &ignored))
            service->close_uncertain = true;
    }
    owned_fd *acquired[] = {&service->listener, &service->epoch_anchor, &service->guardian_peer.pidfd,
                            &service->guardian};
    for (size_t i = 0; i < sizeof(acquired) / sizeof(acquired[0]); ++i)
        if (!service_close_fd(acquired[i])) service->close_uncertain = true;
    if (service->close_uncertain || service->runtime) {
        service->phase = BOOT_STICKY;
        return BOOTSTRAP_OWNED_UNRESOLVED;
    }
    service->phase = BOOT_EMPTY;
    return BOOTSTRAP_CLEAN_FAILURE;
}

static bool send_frame(int channel, const guardian_grant *frame) {
    ssize_t sent;
    do { sent = send(channel, frame, sizeof(*frame), MSG_NOSIGNAL); } while (sent < 0 && errno == EINTR);
    return sent == (ssize_t)sizeof(*frame);
}

static no_error failure(int system_errno, uint32_t operation) {
    return (no_error){NO_ERROR_UNAVAILABLE, system_errno, operation};
}

static bool adopt_grant(service_state *service, guardian_grant *grant, no_deadline deadline, no_error *error) {
    if (!wait_readable(service->guardian.number, deadline)) { *error = failure(ETIMEDOUT, 24); return false; }
    received_packet packet;
    memset(grant, 0, sizeof(*grant));
    if (!packet_receive(service->guardian.number, grant, sizeof(*grant), MSG_DONTWAIT, &packet, error))
        return false;
    bool authentic = packet_authenticated(&packet, &service->guardian_peer, GRANT_RIGHTS);
    if (authentic) {
        service->epoch_anchor = packet.rights[GRANT_EPOCH_DIRECTORY];
        packet.right_count = 0;
    }
    if (!packet_release(&packet)) service->close_uncertain = true;
    if (!authentic) { *error = failure(EPERM, 25); return false; }
    if (packet.bytes != (ssize_t)sizeof(*grant) || grant->magic != SERVICE_MAGIC ||
        grant->version != SERVICE_VERSION || grant->kind != GRANT_EPOCH ||
        (grant->epoch.high == 0 && grant->epoch.low == 0) || grant->generation == 0) {
        *error = failure(EPROTO, 26); return false;
    }
    return true;
}

/* Consumes inherited_channel unless REFUSED. REFUSED touches nothing: a started
 * service may already own that number, 0-2 are the process's standard streams,
 * and a number that is not open has nothing to consume.
 * CLEAN_FAILURE means every received descriptor was closed; OWNED_UNRESOLVED keeps
 * the service and its sticky state. */
bootstrap_result service_bootstrap(service_state *service, int inherited_channel, no_deadline deadline,
                                   no_error *error) {
    *error = (no_error){0};
    if (service->phase != BOOT_EMPTY) { *error = failure(EALREADY, 20); return BOOTSTRAP_REFUSED; }
    if (inherited_channel <= STDERR_FILENO || fcntl(inherited_channel, F_GETFD) == -1) {
        *error = failure(EBADF, 32); return BOOTSTRAP_REFUSED;
    }
    service->guardian = (owned_fd){FD_OWNED, inherited_channel};
    no_error step = {0};
    /* No payload may inherit the guardian channel, whatever number it arrived on. */
    if (fcntl(inherited_channel, F_SETFD, FD_CLOEXEC) == -1) return unwind(service, error, failure(errno, 33));
    if (!socket_kind(inherited_channel, SOCK_SEQPACKET, 0)) return unwind(service, error, failure(ENOTSOCK, 21));
    if (!peer_identity_from_connection(&service->guardian_peer, inherited_channel, &step))
        return unwind(service, error, step);
    /* The guardian created this endpoint and exec'd the service; it is bound by its
     * pidfs identity and principal. The service never reads anyone's namespaces. */
    if (service->guardian_peer.credentials.uid != service->policy->guardian.uid ||
        service->guardian_peer.credentials.gid != service->policy->guardian.gid)
        return unwind(service, error, failure(EPERM, 22));
    if (!kernel_supported(&service->guardian_peer)) return unwind(service, error, failure(ENOSYS, 23));
    if (!peer_enable_credentials(inherited_channel, &step)) return unwind(service, error, step);
    guardian_grant request = {SERVICE_MAGIC, SERVICE_VERSION, GRANT_REQUESTED, {0, 0}, 0};
    if (!send_frame(inherited_channel, &request)) return unwind(service, error, failure(errno, 31));
    guardian_grant grant;
    if (!adopt_grant(service, &grant, deadline, &step)) return unwind(service, error, step);
    if (!delegated_epoch(service->epoch_anchor.number, &service->epoch_device))
        return unwind(service, error, failure(EACCES, 27));
    no_boot_policy policy = {.capacity = service->policy->record_capacity, .epoch = grant.epoch};
    service->runtime = no_runtime_create(&policy, &step);
    if (!service->runtime) return unwind(service, error, step);
    guardian_grant acknowledgement = {SERVICE_MAGIC, SERVICE_VERSION, GRANT_ACKNOWLEDGED, grant.epoch,
                                      grant.generation};
    if (!send_frame(inherited_channel, &acknowledgement)) return unwind(service, error, failure(errno, 30));
    service->epoch = grant.epoch;
    service->generation = grant.generation;
    service->phase = BOOT_ACTIVE;
    return BOOTSTRAP_READY;
}
