#define _GNU_SOURCE
/* The guardian owns the client listener. Root can read a peer's namespaces, so the
 * guardian verifies each client's principal and namespaces and hands the service only
 * connections that passed; the service never listens and never reads namespaces. */
#include "guardian.h"
#include <errno.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

/* Index of the listed client `peer` proves to be, or -1. */
static long verified_client(const guardian_manifest *manifest, const peer_identity *peer) {
    for (size_t i = 0; i < manifest->client_count; ++i) {
        const guardian_client *client = &manifest->clients[i];
        uint32_t span = client->id_count > 1 ? client->id_count : 1;
        uint32_t offset = peer->credentials.uid - client->uid;
        if (peer->credentials.uid >= client->uid && offset < span && peer->credentials.gid >= client->gid &&
            peer->credentials.gid - client->gid == offset)
            return peer_in_namespaces(peer, &client->namespaces) ? (long)i : -1;
    }
    return -1;
}

bool guardian_client_verified(const guardian_manifest *manifest, const peer_identity *peer) {
    return verified_client(manifest, peer) >= 0;
}

/* Connections each user ID may have handed over per second. Past it the rest are dropped
 * at once, so one ID's flood, a single helper's included, cannot crowd out another's. The
 * table recycles the slot of the ID quiet longest. */
#define RATE_SLOTS 64
typedef struct { uint32_t uid; uint64_t window_ns; unsigned count; bool used; } rate_slot;
static rate_slot rates[RATE_SLOTS];

void guardian_forward_reset_rates(void) { memset(rates, 0, sizeof(rates)); }

static bool within_rate(long client, uint32_t uid) {
    if (client < 0) return false;
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    uint64_t now = (uint64_t)value.tv_sec * 1000000000ULL + (uint64_t)value.tv_nsec;
    size_t slot = 0;
    for (size_t i = 0; i < RATE_SLOTS; ++i) {
        if (rates[i].used && rates[i].uid == uid) { slot = i; break; }
        if (!rates[i].used || rates[i].window_ns < rates[slot].window_ns) slot = i;
    }
    if (!rates[slot].used || rates[slot].uid != uid || now - rates[slot].window_ns >= 1000000000ULL)
        rates[slot] = (rate_slot){uid, now, 0, true};
    return ++rates[slot].count <= GUARDIAN_ACCEPT_BURST;
}

static bool send_connection(int channel, int connection, no_id epoch, uint64_t generation) {
    guardian_grant frame = {SERVICE_MAGIC, SERVICE_VERSION, GRANT_CONNECTION, epoch, generation, 0, 0};
    union { struct cmsghdr align; char buffer[CMSG_SPACE(sizeof(int))]; } control;
    memset(&control, 0, sizeof(control));
    struct iovec vector = {.iov_base = &frame, .iov_len = sizeof(frame)};
    struct msghdr header = {.msg_iov = &vector, .msg_iovlen = 1, .msg_control = control.buffer,
        .msg_controllen = sizeof(control.buffer)};
    struct cmsghdr *message = CMSG_FIRSTHDR(&header);
    message->cmsg_level = SOL_SOCKET; message->cmsg_type = SCM_RIGHTS; message->cmsg_len = CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(message), &connection, sizeof(connection));
    ssize_t sent;
    /* Never blocks: a service that stopped reading (draining) loses the client, not the guardian. */
    do { sent = sendmsg(channel, &header, MSG_NOSIGNAL | MSG_DONTWAIT); } while (sent < 0 && errno == EINTR);
    if (sent < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return true;
    return sent == (ssize_t)sizeof(frame);
}

/* One pending client. The guardian's copy of the connection is always closed here: the
 * service owns the handed-over one, and a refused one is simply dropped. */
guardian_forward_result guardian_forward(int listener, int channel, const guardian_manifest *manifest, no_id epoch,
                                         uint64_t generation) {
    int connection;
    do { connection = accept4(listener, NULL, NULL, SOCK_CLOEXEC); } while (connection < 0 && errno == EINTR);
    if (connection < 0) return errno == EAGAIN || errno == EWOULDBLOCK ? FORWARD_IDLE : FORWARD_REFUSED;
    peer_identity peer = {.pidfd = {FD_EMPTY, -1}};
    no_error error;
    guardian_forward_result result = FORWARD_REFUSED;
    if (peer_identity_from_connection(&peer, connection, &error) &&
        within_rate(verified_client(manifest, &peer), peer.credentials.uid))
        result = send_connection(channel, connection, epoch, generation) ? FORWARD_HANDED : FORWARD_CHANNEL_FAILED;
    service_close_fd(&peer.pidfd);
    close(connection);
    return result;
}
