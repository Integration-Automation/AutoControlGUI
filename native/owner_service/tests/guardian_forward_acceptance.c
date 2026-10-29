#define _GNU_SOURCE
/* Guardian client forwarding, unprivileged: the client principal is the test account in
 * its own namespaces, which a process may read for its own UID. Real clients of another
 * account need the root guardian; that is the reason the check lives there. */
#include "guardian.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(expression) do { if (!(expression)) { \
    fprintf(stderr, "failed line %d: %s\n", __LINE__, #expression); abort(); } ++checks; } while (0)

static char path[108];
static guardian_client client;
static guardian_manifest manifest;
static const no_id epoch = {149, 7};

static size_t open_descriptors(void) {
    DIR *directory = opendir("/proc/self/fd");
    size_t count = 0;
    for (struct dirent *entry = readdir(directory); entry; entry = readdir(directory))
        if (entry->d_name[0] != '.') ++count;
    closedir(directory);
    return count;
}

static uint64_t namespace_inode(const char *name, uint64_t *device) {
    char link[64];
    struct stat status;
    snprintf(link, sizeof(link), "/proc/self/ns/%s", name);
    if (stat(link, &status) != 0) abort();
    *device = (uint64_t)status.st_dev;
    return (uint64_t)status.st_ino;
}

/* Connects, sends one packet, then waits for the guardian's verdict as EOF or a reply. */
static pid_t spawn_client(int *report) {
    int pipe_out[2];
    CHECK(pipe2(pipe_out, O_CLOEXEC) == 0);
    fflush(NULL);
    pid_t child = fork();
    if (child == 0) {
        close(pipe_out[0]);
        int number = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
        struct sockaddr_un address = {.sun_family = AF_UNIX};
        strcpy(address.sun_path, path);
        if (connect(number, (struct sockaddr *)&address, sizeof(address)) != 0) _exit(2);
        if (send(number, "hi", 2, 0) != 2) _exit(3);
        struct timeval timeout = {3, 0};
        setsockopt(number, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        char reply[8];
        ssize_t count = recv(number, reply, sizeof(reply), 0);
        /* A refused connection is dropped with our packet unread: EOF or ECONNRESET. */
        bool dropped = count == 0 || (count < 0 && errno == ECONNRESET);
        char verdict = dropped ? 'E' : count == 2 && !memcmp(reply, "ok", 2) ? 'K' : 'X';
        _exit(write(pipe_out[1], &verdict, 1) == 1 ? 0 : 4);
    }
    close(pipe_out[1]);
    *report = pipe_out[0];
    return child;
}

static char verdict_of(pid_t child, int report) {
    char verdict = 0;
    CHECK(read(report, &verdict, 1) == 1);
    int status;
    CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    close(report);
    return verdict;
}

/* The handed-over descriptor is the client's own connection, still carrying credentials. */
static void receive_handoff(int service_end, pid_t client_pid) {
    guardian_grant frame;
    received_packet packet;
    no_error error;
    CHECK(packet_receive(service_end, &frame, sizeof(frame), 0, &packet, &error));
    CHECK(packet.bytes == (ssize_t)sizeof(frame) && frame.kind == GRANT_CONNECTION && packet.right_count == 1);
    CHECK(frame.epoch.high == epoch.high && frame.epoch.low == epoch.low && frame.generation == 3);
    CHECK(packet.credentials_seen && packet.credentials.pid == getpid()); /* Sent by the guardian. */
    int connection = packet.rights[0].number;
    char data[4];
    received_packet inner;
    CHECK(packet_receive(connection, data, sizeof(data), 0, &inner, &error));
    CHECK(inner.bytes == 2 && !memcmp(data, "hi", 2) && inner.credentials_seen &&
          inner.credentials.pid == client_pid);
    CHECK(packet_release(&inner));
    CHECK(send(connection, "ok", 2, MSG_NOSIGNAL) == 2);
    CHECK(packet_release(&packet));
}

static guardian_forward_result forward(int listener, int channel) {
    return guardian_forward(listener, channel, &manifest, epoch, 3);
}

int main(void) {
    signal(SIGPIPE, SIG_IGN);
    snprintf(path, sizeof(path), "/tmp/guardian-forward-%d.sock", (int)getpid());
    client.uid = (uint32_t)getuid();
    client.gid = (uint32_t)getgid();
    client.namespaces.user = namespace_inode("user", &client.namespaces.device);
    client.namespaces.pid = namespace_inode("pid", &client.namespaces.device);
    client.namespaces.mount = namespace_inode("mnt", &client.namespaces.device);
    client.namespaces.cgroup = namespace_inode("cgroup", &client.namespaces.device);
    manifest = (guardian_manifest){.clients = &client, .client_count = 1};
    size_t baseline = open_descriptors();

    int listener = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    strcpy(address.sun_path, path);
    no_error error;
    CHECK(bind(listener, (struct sockaddr *)&address, sizeof(address)) == 0 && listen(listener, 8) == 0 &&
          peer_enable_credentials(listener, &error));
    int pair[2];
    CHECK(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, pair) == 0 && peer_enable_credentials(pair[1], &error));
    CHECK(forward(listener, pair[0]) == FORWARD_IDLE);

    int report;
    pid_t child = spawn_client(&report);
    struct pollfd ready = {.fd = listener, .events = POLLIN};
    CHECK(poll(&ready, 1, 3000) == 1 && forward(listener, pair[0]) == FORWARD_HANDED);
    receive_handoff(pair[1], child);
    CHECK(verdict_of(child, report) == 'K');

    /* Any namespace or the principal differing: refused, the client sees EOF. */
    uint64_t *fields[] = {&client.namespaces.user, &client.namespaces.pid, &client.namespaces.mount,
                          &client.namespaces.cgroup, &client.namespaces.device};
    for (size_t i = 0; i <= sizeof(fields) / sizeof(fields[0]); ++i) {
        guardian_client saved = client;
        if (i < sizeof(fields) / sizeof(fields[0])) *fields[i] += 1;
        else client.uid += 1;
        child = spawn_client(&report);
        CHECK(poll(&ready, 1, 3000) == 1 && forward(listener, pair[0]) == FORWARD_REFUSED);
        CHECK(verdict_of(child, report) == 'E');
        client = saved;
    }

    /* The service end gone: forwarding reports the channel failure. */
    close(pair[1]);
    child = spawn_client(&report);
    CHECK(poll(&ready, 1, 3000) == 1 && forward(listener, pair[0]) == FORWARD_CHANNEL_FAILED);
    CHECK(verdict_of(child, report) == 'E');
    close(pair[0]);
    close(listener);
    unlink(path);
    CHECK(open_descriptors() == baseline);
    printf("{\"checks\": %u, \"evidence\": \"guardian forwarding, unprivileged, own namespaces\"}\n", checks);
    return 0;
}
