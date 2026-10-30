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

/* Connections each listed client entry may have handed over per second: an account, or a
 * whole payload range together, so no number of helper IDs multiplies it. Past it the rest
 * are dropped at once, and one entry's flood cannot crowd out another's. */
static struct { uint64_t window_ns; unsigned count; } rates[GUARDIAN_CLIENT_LIMIT];

void guardian_forward_reset_rates(void) { memset(rates, 0, sizeof(rates)); }

static bool within_rate(long client) {
    if (client < 0 || client >= GUARDIAN_CLIENT_LIMIT) return false;
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    uint64_t now = (uint64_t)value.tv_sec * 1000000000ULL + (uint64_t)value.tv_nsec;
    if (now - rates[client].window_ns >= 1000000000ULL) { rates[client].window_ns = now; rates[client].count = 0; }
    return ++rates[client].count <= GUARDIAN_ACCEPT_BURST;
}

bool guardian_send_connection(int channel, int connection, no_id epoch, uint64_t generation) {
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
guardian_forward_result guardian_forward_routed(int listener, const guardian_manifest *manifest,
                                                guardian_route route, void *context, int *used, int *held) {
    *used = -1;
    *held = -1;
    int connection;
    do { connection = accept4(listener, NULL, NULL, SOCK_CLOEXEC); } while (connection < 0 && errno == EINTR);
    if (connection < 0) return errno == EAGAIN || errno == EWOULDBLOCK ? FORWARD_IDLE : FORWARD_REFUSED;
    peer_identity peer = {.pidfd = {FD_EMPTY, -1}};
    no_error error;
    guardian_target target;
    guardian_forward_result result = FORWARD_REFUSED;
    guardian_route_result routed = ROUTE_DROP;
    if (peer_identity_from_connection(&peer, connection, &error) && within_rate(verified_client(manifest, &peer)))
        routed = route(context, peer.credentials.uid, &target);
    if (routed == ROUTE_SEND) {
        *used = target.channel;
        result = guardian_send_connection(target.channel, connection, target.epoch, target.generation) ?
            FORWARD_HANDED : FORWARD_CHANNEL_FAILED;
    } else if (routed == ROUTE_HOLD) {
        *held = connection;
        connection = -1;
        result = FORWARD_HELD;
    }
    service_close_fd(&peer.pidfd);
    if (connection >= 0) close(connection);
    return result;
}

static guardian_route_result fixed_route(void *context, uint32_t uid, guardian_target *target) {
    (void)uid;
    *target = *(const guardian_target *)context;
    return ROUTE_SEND;
}

guardian_forward_result guardian_forward(int listener, int channel, const guardian_manifest *manifest, no_id epoch,
                                         uint64_t generation) {
    guardian_target target = {channel, epoch, generation};
    int used, held;
    return guardian_forward_routed(listener, manifest, fixed_route, &target, &used, &held);
}
