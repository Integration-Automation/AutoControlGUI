#define _GNU_SOURCE
#include "native_service.h"
#include <errno.h>
#include <linux/magic.h>
#include <poll.h>
#include <string.h>
#include <sys/pidfd.h>
#include <sys/random.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <unistd.h>

/* Consumes the integer before the syscall: EINTR or any close error is sticky and
 * the same number is never closed again, because it may already be reused. */
bool service_close_fd(owned_fd *slot) {
    if (slot->state != FD_OWNED) return slot->state != FD_CLOSE_ERROR;
    int number = slot->number;
    slot->number = -1;
    slot->state = close(number) == 0 ? FD_CLOSED : FD_CLOSE_ERROR;
    return slot->state == FD_CLOSED;
}

static void own_fd(owned_fd *slot, int number) {
    slot->number = number;
    slot->state = FD_OWNED;
}

/* The descriptor is owned first; validation failure leaves it for the caller's
 * single close. Only pidfs pidfds give a kernel identity that survives PID reuse. */
bool peer_identity_adopt(peer_identity *identity, int pidfd) {
    own_fd(&identity->pidfd, pidfd);
    struct statfs filesystem;
    struct stat status;
    if (fstatfs(pidfd, &filesystem) == -1 || filesystem.f_type != PID_FS_MAGIC ||
        fstat(pidfd, &status) == -1) return false;
    identity->inode = (uint64_t)status.st_ino;
    return true;
}

bool peer_alive(const peer_identity *identity) {
    if (identity->pidfd.state != FD_OWNED) return false;
    struct pollfd event = {.fd = identity->pidfd.number, .events = POLLIN};
    int rc;
    do { rc = poll(&event, 1, 0); } while (rc < 0 && errno == EINTR);
    return rc == 0;
}

/* Identity only. SCM_CREDENTIALS reports real IDs and SO_PEERCRED effective IDs
 * at connect time, so credentials are policy inputs taken from the connector. */
bool peer_same_process(const peer_identity *a, const peer_identity *b) {
    return a->pidfd.state == FD_OWNED && b->pidfd.state == FD_OWNED && a->inode == b->inode &&
        a->credentials.pid == b->credentials.pid;
}

bool peer_identity_from_connection(peer_identity *identity, int socket, no_error *error) {
    socklen_t length = sizeof(identity->credentials);
    if (getsockopt(socket, SOL_SOCKET, SO_PEERCRED, &identity->credentials, &length) == -1 ||
        length != sizeof(identity->credentials)) {
        *error = (no_error){NO_ERROR_UNAVAILABLE, errno, 1}; return false;
    }
    int pidfd = -1;
    length = sizeof(pidfd);
    if (getsockopt(socket, SOL_SOCKET, SO_PEERPIDFD, &pidfd, &length) == -1 || pidfd < 0) {
        *error = (no_error){NO_ERROR_UNAVAILABLE, errno, 2}; return false;
    }
    if (!peer_identity_adopt(identity, pidfd) || !peer_alive(identity)) {
        *error = (no_error){NO_ERROR_UNAVAILABLE, ESRCH, 3}; return false;
    }
    return true;
}

/* Membership is the kernel's cgroup ID for the live process, compared against the
 * cgroup2 directory inode the core published. Liveness brackets the query so a
 * reaped process cannot lend its last cgroup to a reused identity. */
bool peer_in_cgroup(const peer_identity *peer, uint64_t cgroup_inode) {
    if (!peer_alive(peer)) return false;
    struct pidfd_info info = {.mask = PIDFD_INFO_CGROUPID};
    if (ioctl(peer->pidfd.number, PIDFD_GET_INFO, &info) == -1 || !(info.mask & PIDFD_INFO_CGROUPID))
        return false;
    return info.cgroupid == cgroup_inode && peer_alive(peer);
}

static bool namespace_is(const peer_identity *peer, unsigned long request, uint64_t device, uint64_t inode) {
    int number = ioctl(peer->pidfd.number, request, 0);
    if (number < 0) return false;
    owned_fd namespace = {FD_OWNED, number};
    struct stat status;
    bool same = fstat(number, &status) == 0 && (uint64_t)status.st_dev == device && (uint64_t)status.st_ino == inode;
    return service_close_fd(&namespace) && same;
}

/* An unreadable namespace (EPERM without ptrace read access) is a mismatch. */
static bool in_namespaces(const peer_identity *peer, const service_namespaces *expected, bool mount) {
    return peer_alive(peer) &&
        namespace_is(peer, PIDFD_GET_USER_NAMESPACE, expected->device, expected->user) &&
        namespace_is(peer, PIDFD_GET_PID_NAMESPACE, expected->device, expected->pid) &&
        (!mount || namespace_is(peer, PIDFD_GET_MNT_NAMESPACE, expected->device, expected->mount)) &&
        namespace_is(peer, PIDFD_GET_CGROUP_NAMESPACE, expected->device, expected->cgroup) && peer_alive(peer);
}

bool peer_in_namespaces(const peer_identity *peer, const service_namespaces *expected) {
    return in_namespaces(peer, expected, true);
}

bool peer_in_namespaces_beside_mount(const peer_identity *peer, const service_namespaces *expected) {
    return in_namespaces(peer, expected, false);
}

bool peer_shares_mount_namespace(const peer_identity *peer, const peer_identity *other) {
    int number = ioctl(other->pidfd.number, PIDFD_GET_MNT_NAMESPACE, 0);
    if (number < 0) return false;
    owned_fd namespace = {FD_OWNED, number};
    struct stat status;
    /* Held open until the peer is compared, so its inode cannot be reused meanwhile. */
    bool same = fstat(number, &status) == 0 && peer_alive(other) &&
        namespace_is(peer, PIDFD_GET_MNT_NAMESPACE, (uint64_t)status.st_dev, (uint64_t)status.st_ino);
    return service_close_fd(&namespace) && same;
}

bool peer_enable_credentials(int socket, no_error *error) {
    int on = 1;
    if (setsockopt(socket, SOL_SOCKET, SO_PASSCRED, &on, sizeof(on)) == -1 ||
        setsockopt(socket, SOL_SOCKET, SO_PASSPIDFD, &on, sizeof(on)) == -1) {
        *error = (no_error){NO_ERROR_UNAVAILABLE, errno, 4}; return false;
    }
    return true;
}

static size_t descriptor_count(const struct cmsghdr *message) {
    return message->cmsg_len < CMSG_LEN(0) ? 0 : (message->cmsg_len - CMSG_LEN(0)) / sizeof(int);
}

static int descriptor_at(struct cmsghdr *message, size_t index) {
    int number;
    memcpy(&number, CMSG_DATA(message) + index * sizeof(int), sizeof(number));
    return number;
}

/* Fresh, never-published numbers: a raw close cannot hit a reused descriptor. */
static void collect_rights(received_packet *packet, struct cmsghdr *message) {
    for (size_t i = 0; i < descriptor_count(message); ++i) {
        int number = descriptor_at(message, i);
        /* The kernel never delivers more than SCM_MAX_FD; the bound is still checked. */
        if (packet->right_count < SERVICE_RIGHTS_LIMIT) own_fd(&packet->rights[packet->right_count++], number);
        else close(number);
    }
}

/* Exactly one pidfs pidfd per packet. Any other shape is closed and rejected. */
static void collect_pidfd(received_packet *packet, struct cmsghdr *message) {
    size_t count = descriptor_count(message);
    for (size_t i = 0; i < count; ++i) {
        int number = descriptor_at(message, i);
        if (count == 1 && packet->sender.pidfd.state == FD_EMPTY && number >= 0) {
            if (!peer_identity_adopt(&packet->sender, number)) packet->duplicate_credentials = true;
        } else {
            packet->duplicate_credentials = true;
            if (number >= 0) close(number);
        }
    }
    if (count != 1) packet->duplicate_credentials = true;
}

static void collect_control(received_packet *packet, struct msghdr *header) {
    for (struct cmsghdr *message = CMSG_FIRSTHDR(header); message; message = CMSG_NXTHDR(header, message)) {
        if (message->cmsg_level != SOL_SOCKET) continue;
        if (message->cmsg_type == SCM_RIGHTS) collect_rights(packet, message);
        else if (message->cmsg_type == SCM_CREDENTIALS &&
                 message->cmsg_len == CMSG_LEN(sizeof(struct ucred))) {
            packet->duplicate_credentials |= packet->credentials_seen;
            packet->credentials_seen = true;
            memcpy(&packet->credentials, CMSG_DATA(message), sizeof(packet->credentials));
        } else if (message->cmsg_type == SCM_PIDFD) {
            collect_pidfd(packet, message);
        }
    }
}

/* One bounded receive. Every delivered descriptor is owned before any check, so a
 * rejected packet still closes exactly what it carried. */
bool packet_receive(int socket, void *frame, size_t size, int flags, received_packet *packet, no_error *error) {
    memset(packet, 0, sizeof(*packet));
    union {
        struct cmsghdr align;
        char buffer[CMSG_SPACE(sizeof(struct ucred)) + CMSG_SPACE(sizeof(int)) +
                    CMSG_SPACE(sizeof(int) * SERVICE_RIGHTS_LIMIT)];
    } control;
    memset(&control, 0, sizeof(control));
    struct iovec vector = {.iov_base = frame, .iov_len = size};
    struct msghdr header = {.msg_iov = &vector, .msg_iovlen = 1,
        .msg_control = control.buffer, .msg_controllen = sizeof(control.buffer)};
    ssize_t count;
    do { count = recvmsg(socket, &header, MSG_CMSG_CLOEXEC | flags); } while (count < 0 && errno == EINTR);
    if (count < 0) { *error = (no_error){NO_ERROR_UNAVAILABLE, errno, 5}; return false; }
    packet->bytes = count;
    packet->flags = header.msg_flags;
    collect_control(packet, &header);
    packet->sender.credentials = packet->credentials;
    return true;
}

/* The connector proved who connected, not who sent: an inherited or passed endpoint
 * delivers another process's packets on the same connection (measured on Linux 6.18). */
bool packet_authenticated(const received_packet *packet, const peer_identity *connector, size_t expected_rights) {
    if (packet->flags & (MSG_TRUNC | MSG_CTRUNC) || !packet->credentials_seen ||
        packet->duplicate_credentials || packet->right_count != expected_rights) return false;
    if (packet->sender.pidfd.state != FD_OWNED || !peer_alive(&packet->sender)) return false;
    return peer_same_process(&packet->sender, connector);
}

bool packet_release(received_packet *packet) {
    bool clean = service_close_fd(&packet->sender.pidfd);
    for (size_t i = 0; i < packet->right_count; ++i) clean &= service_close_fd(&packet->rights[i]);
    packet->right_count = 0;
    return clean;
}

bool service_random(void *buffer, size_t size) {
    unsigned char *cursor = buffer;
    while (size) {
        ssize_t count = getrandom(cursor, size, 0);
        if (count < 0) { if (errno == EINTR) continue; return false; }
        cursor += count; size -= (size_t)count;
    }
    return true;
}
