#define _GNU_SOURCE
/* The guardian owns the client listener. Root can read a peer's namespaces, so the
 * guardian verifies each client's principal and namespaces and hands the service only
 * connections that passed; the service never listens and never reads namespaces. */
#include "guardian.h"
#include <errno.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

bool guardian_client_verified(const guardian_manifest *manifest, const peer_identity *peer) {
    for (size_t i = 0; i < manifest->client_count; ++i) {
        const guardian_client *client = &manifest->clients[i];
        if (client->uid == peer->credentials.uid && client->gid == peer->credentials.gid)
            return peer_in_namespaces(peer, &client->namespaces);
    }
    return false;
}

static bool send_connection(int channel, int connection, no_id epoch, uint64_t generation) {
    guardian_grant frame = {SERVICE_MAGIC, SERVICE_VERSION, GRANT_CONNECTION, epoch, generation};
    union { struct cmsghdr align; char buffer[CMSG_SPACE(sizeof(int))]; } control;
    memset(&control, 0, sizeof(control));
    struct iovec vector = {.iov_base = &frame, .iov_len = sizeof(frame)};
    struct msghdr header = {.msg_iov = &vector, .msg_iovlen = 1, .msg_control = control.buffer,
        .msg_controllen = sizeof(control.buffer)};
    struct cmsghdr *message = CMSG_FIRSTHDR(&header);
    message->cmsg_level = SOL_SOCKET; message->cmsg_type = SCM_RIGHTS; message->cmsg_len = CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(message), &connection, sizeof(connection));
    ssize_t sent;
    do { sent = sendmsg(channel, &header, MSG_NOSIGNAL); } while (sent < 0 && errno == EINTR);
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
    if (peer_identity_from_connection(&peer, connection, &error) && guardian_client_verified(manifest, &peer))
        result = send_connection(channel, connection, epoch, generation) ? FORWARD_HANDED : FORWARD_CHANNEL_FAILED;
    service_close_fd(&peer.pidfd);
    close(connection);
    return result;
}
