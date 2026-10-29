#define _GNU_SOURCE
/* Peer/lease acceptance. Real Unix connections, real processes, real pidfds.
 * None of this is protected containment evidence: the anchor is a plain
 * directory and the production gate stays closed throughout. */
#include "native_owner.c"
#include "service_test_support.h"

/* ---------- cases ---------- */

static void lifecycle_client(int in, int out) {
    (void)in; (void)out;
    int number = client_connect();
    no_id lease = open_top(number, 1);
    service_reply replay = call(number, make(OP_OPEN_TOP, 1, TOP));
    EXPECT(replay.status == STATUS_EXISTING && same_id(replay.lease, lease));
    EXPECT(call(number, make(OP_OPEN_TOP, 1, OTHER_TOP)).status == STATUS_CONFLICT);
    EXPECT(call(number, make(OP_OPEN_TOP, 2, NESTED)).status == STATUS_REJECTED);
    EXPECT(call(number, make(OP_OPEN_TOP, 3, 77)).status == STATUS_REJECTED);
    EXPECT(call(number, start_request(lease, 10)).status == STATUS_UNAVAILABLE);
    EXPECT(call(number, lease_request(OP_CLOSE, lease)).status == STATUS_OK);
    EXPECT(call(number, lease_request(OP_CLOSE, lease)).status == STATUS_CLOSED);
    EXPECT(call(number, start_request(lease, 11)).status == STATUS_CLOSED);
    EXPECT(call(number, make(OP_OPEN_TOP, 1, TOP)).status == STATUS_CLOSED);
    no_id unknown = {lease.high ^ 1, lease.low};
    EXPECT(call(number, start_request(unknown, 12)).status == STATUS_REJECTED);
    report_lease(out, lease);
}

static void case_lifecycle(service_state *service) {
    int pipe_out[2];
    CHECK(pipe2(pipe_out, O_CLOEXEC) == 0);
    pid_t child = spawn(lifecycle_client, -1, pipe_out[1]);
    CHECK(pump_until_exit(service, child) == 0);
    no_id id;
    CHECK(read(pipe_out[0], &id, sizeof(id)) == sizeof(id));
    close(pipe_out[0]); close(pipe_out[1]);
    service_lease *lease = lease_by_id(service, id);
    CHECK(lease && lease->phase == LEASE_CLOSED && lease->reason == CLOSE_REQUESTED);
    CHECK(registered(service->runtime, id) && revoked(service->runtime, id));
    authenticated_scope_slot *slot = &service->scopes.slots[lease - service->leases];
    CHECK(atomic_load(&slot->issuance_closed) && atomic_load(&slot->borrowers) == 0);
    CHECK(slot->peer.state == FD_CLOSED && slot->epoch_anchor.state == FD_CLOSED && slot->resources_settled);
    CHECK(slot->identity.parent_is_epoch && same_id(slot->identity.lease, id));
    CHECK(service->runtime->count == 0); /* The closed gate admitted nothing. */
}

static void seam_client(int in, int out) {
    int number = client_connect();
    no_id lease = open_top(number, 1);
    report_lease(out, lease);
    wait_byte(in);
    EXPECT(call(number, lease_request(OP_CLOSE, lease)).status == STATUS_OK);
}

static void case_seam(service_state *service) {
    int to_child[2], from_child[2];
    CHECK(pipe2(to_child, O_CLOEXEC) == 0 && pipe2(from_child, O_CLOEXEC) == 0);
    pid_t child = spawn(seam_client, to_child[0], from_child[1]);
    service_lease *lease = lease_by_id(service, pump_lease(service, from_child[0]));
    CHECK(lease && lease->phase == LEASE_OPEN);
    authenticated_scope_slot *slot = lease->scope.reference.slot;
    CHECK(atomic_load(&slot->borrowers) == 1 && slot->peer.state == FD_OWNED && slot->epoch_anchor.state == FD_OWNED);
    owner_record *record = NULL, *duplicate = NULL;
    no_error error;
    CHECK(seam_admit(service->runtime, lease, 20, &record, &error) == NO_ACCEPTED && record);
    CHECK(atomic_load(&slot->borrowers) == 2 && record->retained_scope.slot == slot);
    CHECK(seam_admit(service->runtime, lease, 20, &duplicate, &error) == NO_EXISTING && !duplicate);
    send_byte(to_child[1]);
    CHECK(pump_until_exit(service, child) == 0);
    /* Revoke-before-submit at the core: the closed lease is fenced, and the record
     * still pins the slot, so the single owner scan must not close it yet. */
    CHECK(lease->phase == LEASE_CLOSED && atomic_load(&slot->borrowers) == 1);
    CHECK(slot->peer.state == FD_OWNED && slot->epoch_anchor.state == FD_OWNED);
    CHECK(record->admission == ADMISSION_FENCED);
    pthread_mutex_lock(&service->runtime->registry);
    without_thread(record);
    pthread_mutex_unlock(&service->runtime->registry);
    service_settle(service);
    CHECK(record->settled && atomic_load(&slot->borrowers) == 0);
    CHECK(slot->peer.state == FD_CLOSED && slot->epoch_anchor.state == FD_CLOSED && slot->resources_settled);
    CHECK(seam_admit(service->runtime, lease, 21, &duplicate, &error) == NO_REJECTED);
    close(to_child[0]); close(to_child[1]); close(from_child[0]); close(from_child[1]);
}

static void multiplex_client(int in, int out) {
    (void)in; (void)out;
    int number = client_connect();
    no_id source = open_top(number, 1), sibling = open_top(number, 2);
    EXPECT(!same_id(source, sibling));
    EXPECT(call(number, lease_request(OP_CLOSE, source)).status == STATUS_OK);
    EXPECT(call(number, start_request(sibling, 30)).status == STATUS_UNAVAILABLE);
    EXPECT(call(number, start_request(source, 31)).status == STATUS_CLOSED);
}

static void case_independence(service_state *service) {
    int to_a[2], from_a[2], to_b[2], from_b[2];
    CHECK(pipe2(to_a, O_CLOEXEC) == 0 && pipe2(from_a, O_CLOEXEC) == 0);
    CHECK(pipe2(to_b, O_CLOEXEC) == 0 && pipe2(from_b, O_CLOEXEC) == 0);
    pid_t a = spawn(holder_client, to_a[0], from_a[1]);
    service_lease *lease_a = lease_by_id(service, pump_lease(service, from_a[0]));
    pid_t b = spawn(holder_client, to_b[0], from_b[1]);
    service_lease *lease_b = lease_by_id(service, pump_lease(service, from_b[0]));
    send_byte(to_a[1]);
    CHECK(pump_until_exit(service, a) == 0);
    CHECK(lease_a->phase == LEASE_CLOSED &&
          (lease_a->reason == CLOSE_DISCONNECT || lease_a->reason == CLOSE_PEER_DEATH));
    CHECK(lease_b->phase == LEASE_OPEN);
    send_byte(to_b[1]);
    CHECK(pump_until_exit(service, b) == 0);
    CHECK(lease_b->phase == LEASE_CLOSED);
    pid_t c = spawn(multiplex_client, -1, -1);
    CHECK(pump_until_exit(service, c) == 0);
    int pipes[] = {to_a[0], to_a[1], from_a[0], from_a[1], to_b[0], to_b[1], from_b[0], from_b[1]};
    for (size_t i = 0; i < sizeof(pipes) / sizeof(pipes[0]); ++i) close(pipes[i]);
}

/* The connector opens a lease; its child sends on the inherited endpoint. */
static void inherited_client(int in, int out) {
    (void)in; (void)out;
    int number = client_connect();
    no_id lease = open_top(number, 1);
    fflush(NULL);
    pid_t child = fork();
    if (child == 0) {
        EXPECT(call(number, start_request(lease, 40)).status == STATUS_UNAUTHENTICATED);
        _exit(0);
    }
    int status;
    EXPECT(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    /* The service closed the connection: send fails or no reply arrives. */
    EXPECT(call(number, start_request(lease, 41)).status >= 0xfffffffeu);
}

/* The endpoint travels by SCM_RIGHTS to a process that never inherited it. */
static void passed_client(int in, int out) {
    (void)in; (void)out;
    int pair[2];
    EXPECT(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, pair) == 0);
    fflush(NULL);
    pid_t child = fork();
    if (child == 0) {
        close(pair[0]);
        union { struct cmsghdr align; char buffer[CMSG_SPACE(sizeof(int))]; } control;
        no_id lease;
        struct iovec vector = {.iov_base = &lease, .iov_len = sizeof(lease)};
        struct msghdr header = {.msg_iov = &vector, .msg_iovlen = 1, .msg_control = control.buffer,
            .msg_controllen = sizeof(control.buffer)};
        EXPECT(recvmsg(pair[1], &header, MSG_CMSG_CLOEXEC) == sizeof(lease));
        int passed;
        memcpy(&passed, CMSG_DATA(CMSG_FIRSTHDR(&header)), sizeof(passed));
        struct timeval timeout = {3, 0};
        setsockopt(passed, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        EXPECT(call(passed, start_request(lease, 50)).status == STATUS_UNAUTHENTICATED);
        _exit(0);
    }
    close(pair[1]);
    int number = client_connect();
    no_id lease = open_top(number, 1);
    union { struct cmsghdr align; char buffer[CMSG_SPACE(sizeof(int))]; } control;
    memset(&control, 0, sizeof(control));
    struct iovec vector = {.iov_base = &lease, .iov_len = sizeof(lease)};
    struct msghdr header = {.msg_iov = &vector, .msg_iovlen = 1, .msg_control = control.buffer,
        .msg_controllen = sizeof(control.buffer)};
    struct cmsghdr *message = CMSG_FIRSTHDR(&header);
    message->cmsg_level = SOL_SOCKET; message->cmsg_type = SCM_RIGHTS; message->cmsg_len = CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(message), &number, sizeof(number));
    EXPECT(sendmsg(pair[0], &header, 0) == sizeof(lease));
    int status;
    EXPECT(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
}

/* The connector dies while a child keeps the socket open: peer death, not EOF. */
static void orphaned_client(int in, int out) {
    int number = client_connect();
    no_id lease = open_top(number, 1);
    fflush(NULL);
    if (fork() == 0) { wait_byte(in); close(number); _exit(0); }
    report_lease(out, lease);
}

static void case_sender_identity(service_state *service) {
    void (*bodies[])(int, int) = {inherited_client, passed_client};
    for (size_t i = 0; i < 2; ++i) {
        size_t before = service->lease_count;
        pid_t child = spawn(bodies[i], -1, -1);
        CHECK(pump_until_exit(service, child) == 0);
        CHECK(service->lease_count == before + 1);
        CHECK(service->leases[before].phase == LEASE_CLOSED && service->leases[before].reason == CLOSE_SENDER_MISMATCH);
    }
    int to_child[2], from_child[2];
    CHECK(pipe2(to_child, O_CLOEXEC) == 0 && pipe2(from_child, O_CLOEXEC) == 0);
    pid_t connector = spawn(orphaned_client, to_child[0], from_child[1]);
    service_lease *lease = lease_by_id(service, pump_lease(service, from_child[0]));
    CHECK(pump_until_exit(service, connector) == 0);
    CHECK(lease->phase == LEASE_CLOSED && lease->reason == CLOSE_PEER_DEATH);
    send_byte(to_child[1]); /* Release the orphan, which the init reaper collects. */
    close(to_child[0]); close(to_child[1]); close(from_child[0]); close(from_child[1]);
}

static void rights_client(int in, int out) {
    (void)in; (void)out;
    int number = client_connect();
    service_request request = make(OP_OPEN_TOP, 1, TOP);
    int smuggled = open("/dev/null", O_RDONLY | O_CLOEXEC);
    union { struct cmsghdr align; char buffer[CMSG_SPACE(sizeof(int))]; } control;
    memset(&control, 0, sizeof(control));
    struct iovec vector = {.iov_base = &request, .iov_len = sizeof(request)};
    struct msghdr header = {.msg_iov = &vector, .msg_iovlen = 1, .msg_control = control.buffer,
        .msg_controllen = sizeof(control.buffer)};
    struct cmsghdr *message = CMSG_FIRSTHDR(&header);
    message->cmsg_level = SOL_SOCKET; message->cmsg_type = SCM_RIGHTS; message->cmsg_len = CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(message), &smuggled, sizeof(smuggled));
    EXPECT(sendmsg(number, &header, 0) == sizeof(request));
    EXPECT(receive_reply(number).status == STATUS_UNAUTHENTICATED);
}

static void malformed_client(int in, int out) {
    (void)in; (void)out;
    int number = client_connect();
    char shortened[8] = {0};
    EXPECT(send(number, shortened, sizeof(shortened), 0) == sizeof(shortened));
    EXPECT(receive_reply(number).status == STATUS_MALFORMED);
    service_request request = make(OP_OPEN_TOP, 1, TOP);
    request.magic ^= 1;
    EXPECT(call(number, request).status == STATUS_MALFORMED);
    EXPECT(call(number, make(99, 2, TOP)).status == STATUS_MALFORMED);
    no_id lease = open_top(number, 3);
    service_request bad = start_request(lease, 60);
    bad.argc = 9;
    EXPECT(call(number, bad).status == STATUS_MALFORMED);
    bad = start_request(lease, 61);
    bad.arguments[SERVICE_ARGUMENT_BYTES - 1] = 'x';
    EXPECT(call(number, bad).status == STATUS_MALFORMED);
    service_request child = make(OP_OPEN_CHILD, 4, NESTED);
    child.parent = (no_ticket){{138, 1}, {0, 1}};
    EXPECT(call(number, child).status == STATUS_REJECTED);
}

static void foreign_client(int in, int out) {
    (void)in; (void)out;
    EXPECT(call(client_connect(), make(OP_OPEN_TOP, 1, TOP)).status == STATUS_UNAUTHENTICATED);
}

static void case_rejections(service_state *service) {
    size_t baseline = open_descriptors();
    size_t before = service->lease_count;
    pid_t child = spawn(rights_client, -1, -1);
    CHECK(pump_until_exit(service, child) == 0);
    CHECK(service->lease_count == before && open_descriptors() == baseline);
    child = spawn(malformed_client, -1, -1);
    CHECK(pump_until_exit(service, child) == 0);
    CHECK(service->lease_count == before + 1);
    policy.clients[0].uid += 1;
    child = spawn(foreign_client, -1, -1);
    CHECK(pump_until_exit(service, child) == 0);
    policy.clients[0].uid -= 1;
    CHECK(service->lease_count == before + 1 && open_descriptors() == baseline);
}

static void expiring_client(int in, int out) {
    (void)in; (void)out;
    int number = client_connect();
    no_id lease = open_top(number, 1);
    struct timespec delay = {0, 300000000};
    nanosleep(&delay, NULL);
    EXPECT(call(number, start_request(lease, 70)).status == STATUS_CLOSED);
}

/* The reply cannot be delivered: the client shut its endpoint after sending. */
static void lost_reply_client(int in, int out) {
    int number = client_connect();
    service_request request = make(OP_OPEN_TOP, 1, TOP);
    EXPECT(send(number, &request, sizeof(request), 0) == sizeof(request));
    close(number);
    report_lease(out, (no_id){0, 0});
    wait_byte(in);
}

static void case_expiry_and_lost_reply(service_state *service) {
    uint64_t lifetime = policy.lease_lifetime_ns;
    policy.lease_lifetime_ns = 100000000ULL;
    size_t before = service->lease_count;
    pid_t child = spawn(expiring_client, -1, -1);
    CHECK(pump_until_exit(service, child) == 0);
    policy.lease_lifetime_ns = lifetime;
    CHECK(service->leases[before].phase == LEASE_CLOSED && service->leases[before].reason == CLOSE_EXPIRED);
    int to_child[2], from_child[2];
    CHECK(pipe2(to_child, O_CLOEXEC) == 0 && pipe2(from_child, O_CLOEXEC) == 0);
    child = spawn(lost_reply_client, to_child[0], from_child[1]);
    pump_lease(service, from_child[0]);
    for (int i = 0; i < 20; ++i) service_run_one(service, 2);
    CHECK(service->lease_count == before + 2);
    CHECK(service->leases[before + 1].phase == LEASE_CLOSED && service->leases[before + 1].reason == CLOSE_REPLY_LOST);
    CHECK(!registered(service->runtime, (no_id){0, 0}) && revoked(service->runtime, service->leases[before + 1].id));
    send_byte(to_child[1]);
    CHECK(pump_until_exit(service, child) == 0);
    close(to_child[0]); close(to_child[1]); close(from_child[0]); close(from_child[1]);
}

static void exhausting_client(int in, int out) {
    (void)in; (void)out;
    int number = client_connect();
    service_reply reply;
    uint64_t nonce = 1;
    do { reply = call(number, make(OP_OPEN_TOP, nonce++, TOP)); } while (reply.status == STATUS_OK && nonce < 64);
    EXPECT(reply.status == STATUS_CAPACITY);
}

static void case_exhaustion(service_state *service) {
    pid_t child = spawn(exhausting_client, -1, -1);
    CHECK(pump_until_exit(service, child) == 0);
    CHECK(service->lease_count == SERVICE_LEASE_LIMIT);
    size_t issued = 0;
    for (size_t i = 0; i < service->lease_count; ++i) {
        CHECK(service->leases[i].phase == LEASE_CLOSED);
        if (service->leases[i].reason != CLOSE_FAILED_ISSUE) ++issued;
    }
    CHECK(service->runtime->registered_lease_count == issued);
    /* Every position of the epoch is spent and none is open: admission has ended
     * and the service asks to be drained so the guardian can grant a fresh epoch. */
    CHECK(service->phase == BOOT_DRAINING && service_run_one(service, 0) == SERVICE_PENDING);
}

/* Drain with a scope borrowed by an unsettled record keeps every resource. */
static void case_drain(void) {
    service_state *service = peer_service((no_id){138, 2});
    int to_child[2], from_child[2];
    CHECK(pipe2(to_child, O_CLOEXEC) == 0 && pipe2(from_child, O_CLOEXEC) == 0);
    pid_t child = spawn(holder_client, to_child[0], from_child[1]);
    service_lease *lease = lease_by_id(service, pump_lease(service, from_child[0]));
    owner_record *record = NULL;
    no_error error;
    CHECK(seam_admit(service->runtime, lease, 80, &record, &error) == NO_ACCEPTED);
    authenticated_scope_slot *slot = lease->scope.reference.slot;
    CHECK(service_drain(service, (no_deadline){owner_now() + 50000000ULL}) == SERVICE_PENDING);
    CHECK(service->runtime && lease->phase == LEASE_CLOSED && atomic_load(&slot->borrowers) == 1);
    CHECK(slot->peer.state == FD_OWNED && service->epoch_anchor.state == FD_OWNED);
    CHECK(!service_free(&service) && service);
    pthread_mutex_lock(&service->runtime->registry);
    without_thread(record);
    pthread_mutex_unlock(&service->runtime->registry);
    CHECK(service_drain(service, (no_deadline){owner_now() + 1000000000ULL}) == SERVICE_CLEAN);
    CHECK(!service->runtime && slot->peer.state == FD_CLOSED && slot->epoch_anchor.state == FD_CLOSED);
    CHECK(service_free(&service) && !service);
    send_byte(to_child[1]);
    int status;
    CHECK(waitpid(child, &status, 0) == child);
    close(to_child[0]); close(to_child[1]); close(from_child[0]); close(from_child[1]);
}

/* Observation only: the kernel cgroup ID of a live process against a directory
 * inode. The test's own cgroup is not a protected payload. */
static void case_membership_observation(void) {
    struct stat status = own_cgroup();
    int hold[2];
    CHECK(pipe2(hold, O_CLOEXEC) == 0);
    fflush(NULL);
    pid_t child = fork();
    if (child == 0) {
        close(hold[1]);
        char byte;
        ssize_t ignored = read(hold[0], &byte, 1);
        (void)ignored;
        _exit(0);
    }
    int number = (int)syscall(SYS_pidfd_open, child, 0);
    CHECK(number >= 0);
    peer_identity peer = {0};
    CHECK(peer_identity_adopt(&peer, number));
    CHECK(peer_alive(&peer) && peer_in_cgroup(&peer, (uint64_t)status.st_ino));
    CHECK(!peer_in_cgroup(&peer, (uint64_t)status.st_ino + 1));
    close(hold[1]);
    int exit_status;
    CHECK(waitpid(child, &exit_status, 0) == child);
    CHECK(!peer_alive(&peer) && !peer_in_cgroup(&peer, (uint64_t)status.st_ino));
    CHECK(service_close_fd(&peer.pidfd));
    close(hold[0]);
}

/* ---------- bootstrap ----------
 * The guardian creates the socketpair, as in production, so SO_PEERCRED and
 * SO_PEERPIDFD on the service end name it. The service runs in a forked child. */

typedef enum { GRANT_TMP, GRANT_CGROUP_ROOT, GRANT_NO_RIGHT, GRANT_TWO_RIGHTS, GRANT_TRUNCATED,
               GRANT_SILENT, GRANT_FROM_CHILD, GRANT_BAD_FRAME } grant_case;

static bool guardian_send(int channel, grant_case variant) {
    guardian_grant request;
    struct timeval timeout = {3, 0};
    setsockopt(channel, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    if (recv(channel, &request, sizeof(request), 0) != (ssize_t)sizeof(request) ||
        request.magic != SERVICE_MAGIC || request.kind != GRANT_REQUESTED) return false;
    int directory = open(variant == GRANT_CGROUP_ROOT ? "/sys/fs/cgroup" : directory_path,
                         O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    int listener = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    struct sockaddr_un autobind = {.sun_family = AF_UNIX};
    if (directory < 0 || listener < 0 || bind(listener, (struct sockaddr *)&autobind, sizeof(sa_family_t)) != 0 ||
        listen(listener, 1) != 0) {
        if (directory >= 0) close(directory);
        if (listener >= 0) close(listener);
        return false;
    }
    int rights[3] = {directory, listener, listener};
    /* The grant carries the epoch directory only. */
    size_t count = variant == GRANT_NO_RIGHT ? 0 : variant == GRANT_TWO_RIGHTS ? 2 : 1;
    struct { guardian_grant grant; char extra[8]; } frame = {{SERVICE_MAGIC, SERVICE_VERSION, GRANT_EPOCH,
        {138, 9}, 1, 0, 0}, {0}};
    if (variant == GRANT_BAD_FRAME) frame.grant.generation = 0;
    union { struct cmsghdr align; char buffer[CMSG_SPACE(sizeof(rights))]; } control;
    memset(&control, 0, sizeof(control));
    struct iovec vector = {.iov_base = &frame,
        .iov_len = sizeof(frame.grant) + (variant == GRANT_TRUNCATED ? sizeof(frame.extra) : 0)};
    struct msghdr header = {.msg_iov = &vector, .msg_iovlen = 1, .msg_control = control.buffer,
        .msg_controllen = count ? CMSG_SPACE(sizeof(int) * count) : 0};
    struct cmsghdr *message = CMSG_FIRSTHDR(&header);
    if (count) {
        message->cmsg_level = SOL_SOCKET; message->cmsg_type = SCM_RIGHTS;
        message->cmsg_len = CMSG_LEN(sizeof(int) * count);
        memcpy(CMSG_DATA(message), rights, sizeof(int) * count);
    } else {
        header.msg_control = NULL;
    }
    bool sent = sendmsg(channel, &header, MSG_NOSIGNAL) == (ssize_t)vector.iov_len;
    close(directory); close(listener);
    return sent;
}

typedef struct { bootstrap_result result; no_error error; bool descriptors_restored, freed; } bootstrap_outcome;

static void service_side(int channel, int report, uint32_t guardian_uid) {
    size_t baseline = open_descriptors();
    bootstrap_outcome outcome = {0};
    policy.guardian.uid = guardian_uid;
    policy.guardian.gid = (uint32_t)getgid();
    policy.clients[0].uid = guardian_uid + 2; /* Disjoint from the guardian; no client connects here. */
    service_state *service = service_allocate(&policy, &outcome.error);
    EXPECT(service != NULL);
    outcome.result = service_bootstrap(service, channel, (no_deadline){owner_now() + 300000000ULL}, &outcome.error);
    outcome.freed = service->phase == BOOT_EMPTY && service_free(&service);
    outcome.descriptors_restored = open_descriptors() == baseline - 1; /* The channel is consumed. */
    EXPECT(write(report, &outcome, sizeof(outcome)) == sizeof(outcome));
}

static bootstrap_outcome run_bootstrap(grant_case variant, int type, uint32_t guardian_uid) {
    int pair[2], report[2];
    CHECK(socketpair(AF_UNIX, type | SOCK_CLOEXEC, 0, pair) == 0 && pipe2(report, O_CLOEXEC) == 0);
    fflush(NULL);
    pid_t service = fork();
    if (service == 0) {
        close(pair[1]); close(report[0]);
        service_side(pair[0], report[1], guardian_uid);
        _exit(0);
    }
    close(pair[0]); close(report[1]);
    if (variant == GRANT_FROM_CHILD) {
        pid_t inner = fork();
        if (inner == 0) _exit(guardian_send(pair[1], GRANT_TMP) ? 0 : 1);
        int status;
        CHECK(waitpid(inner, &status, 0) == inner && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    } else if (type == SOCK_SEQPACKET && variant != GRANT_SILENT) {
        /* Best effort: a service that refuses before reading closes the channel
         * first. A grant that never arrived shows up as operation 24 below. */
        (void)guardian_send(pair[1], variant);
    }
    bootstrap_outcome outcome;
    CHECK(read(report[0], &outcome, sizeof(outcome)) == sizeof(outcome));
    int status;
    CHECK(waitpid(service, &status, 0) == service && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    close(pair[1]); close(report[0]);
    return outcome;
}

static void case_bootstrap(void) {
    size_t baseline = open_descriptors();
    uint32_t self = (uint32_t)getuid();
    struct { grant_case variant; int type; uint32_t uid; uint32_t operation; } cases[] = {
        {GRANT_TMP, SOCK_STREAM, self, 21},
        {GRANT_TMP, SOCK_SEQPACKET, self + 1, 22},
        {GRANT_SILENT, SOCK_SEQPACKET, self, 24},
        {GRANT_FROM_CHILD, SOCK_SEQPACKET, self, 25},
        {GRANT_NO_RIGHT, SOCK_SEQPACKET, self, 25},
        {GRANT_TWO_RIGHTS, SOCK_SEQPACKET, self, 25},
        {GRANT_TRUNCATED, SOCK_SEQPACKET, self, 25},
        {GRANT_BAD_FRAME, SOCK_SEQPACKET, self, 26},
        {GRANT_TMP, SOCK_SEQPACKET, self, 27},
        {GRANT_CGROUP_ROOT, SOCK_SEQPACKET, self, 27},
    };
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        bootstrap_outcome outcome = run_bootstrap(cases[i].variant, cases[i].type, cases[i].uid);
        if (outcome.error.operation_code != cases[i].operation)
            fprintf(stderr, "bootstrap case %zu: operation %u errno %d\n", i,
                    outcome.error.operation_code, outcome.error.system_errno);
        CHECK(outcome.result == BOOTSTRAP_CLEAN_FAILURE && outcome.error.operation_code == cases[i].operation);
        CHECK(outcome.freed && outcome.descriptors_restored);
        if (open_descriptors() != baseline) {
            fprintf(stderr, "bootstrap case %zu: descriptors %zu, baseline %zu\n", i, open_descriptors(), baseline);
            fflush(NULL);
            if (system("ls -l /proc/$PPID/fd >&2") == -1) perror("system");
        }
        CHECK(open_descriptors() == baseline);
    }
}

/* ---------- the installed entry ----------
 * service_main built with the fixture manifest, exec'd the way the guardian will:
 * endpoint on SERVICE_GUARDIAN_FD, nothing else. Refusals only, as above. */

typedef struct { int exit; char diagnostic[256]; } entry_outcome;

static entry_outcome run_entry(const char *path, bool with_channel) {
    int pair[2], diagnostics[2];
    CHECK(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, pair) == 0 && pipe2(diagnostics, O_CLOEXEC) == 0);
    fflush(NULL);
    pid_t service = fork();
    if (service == 0) {
        if (dup2(diagnostics[1], STDERR_FILENO) != STDERR_FILENO) _exit(90);
        if (with_channel && pair[0] == SERVICE_GUARDIAN_FD) {
            if (fcntl(pair[0], F_SETFD, 0) != 0) _exit(91);
        } else if (with_channel && dup2(pair[0], SERVICE_GUARDIAN_FD) != SERVICE_GUARDIAN_FD) {
            _exit(92);
        } else if (!with_channel) {
            close(SERVICE_GUARDIAN_FD);
        }
        char *argv[] = {(char *)path, NULL}, *env[] = {NULL};
        execve(path, argv, env);
        _exit(93);
    }
    close(pair[0]); close(diagnostics[1]);
    if (with_channel) CHECK(guardian_send(pair[1], GRANT_TMP));
    entry_outcome outcome = {0};
    ssize_t length = read(diagnostics[0], outcome.diagnostic, sizeof(outcome.diagnostic) - 1);
    outcome.diagnostic[length > 0 ? length : 0] = 0;
    int status;
    CHECK(waitpid(service, &status, 0) == service && WIFEXITED(status));
    outcome.exit = WEXITSTATUS(status);
    close(pair[1]); close(diagnostics[0]);
    return outcome;
}

static void case_service_entry(const char *path) {
    entry_outcome refused = run_entry(path, false);
    CHECK(refused.exit == 65 && strstr(refused.diagnostic, "refused") && strstr(refused.diagnostic, "operation 32"));
    entry_outcome delegated = run_entry(path, true);
    CHECK(delegated.exit == 66 && strstr(delegated.diagnostic, "operation 27"));
}

int main(int argc, char **argv) {
    if (argc != 2) return 64;
    fixture_setup("service-acceptance");
    size_t baseline = open_descriptors();

    case_membership_observation();
    service_state *service = peer_service((no_id){138, 1});
    case_lifecycle(service);
    case_seam(service);
    case_independence(service);
    case_sender_identity(service);
    case_rejections(service);
    case_expiry_and_lost_reply(service);
    case_exhaustion(service);
    CHECK(service_drain(service, (no_deadline){owner_now() + 1000000000ULL}) == SERVICE_CLEAN);
    CHECK(service_free(&service));
    case_drain();
    case_bootstrap();
    case_service_entry(argv[1]);
    CHECK(open_descriptors() == baseline);
    fixture_teardown();
    printf("{\"checks\": %u, \"evidence\": \"peer/lease only\", \"protected_execution\": false, "
           "\"positive_bootstrap\": \"unexecuted: no service-owned delegated cgroup2 epoch exists here\"}\n",
           checks);
    return 0;
}
