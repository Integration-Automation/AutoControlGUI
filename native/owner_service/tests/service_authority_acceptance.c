#define _GNU_SOURCE
/* Authority acceptance: nested admission, connection binding, guardian handoff, the
 * argument grammar, manifest validation, failed issuance and admission end.
 * Real connections and processes. The nested payload is the test's own cgroup,
 * published by hand below the closed gate: peer/lease authority evidence only. */
#include "native_owner.c"
#include "service_test_support.h"

static no_ticket parents[2];
static uint8_t capabilities[2][SERVICE_CAPABILITY_BYTES];
static uint32_t expected_status;

static no_deadline soon(void) { return (no_deadline){owner_now() + 1000000000ULL}; }

static void drain_and_free(service_state *service) {
    service_result result = service_drain(service, soon());
    if (result != SERVICE_CLEAN)
        fprintf(stderr, "drain %d phase %d uncertain %d error %d/%d/%u\n", result, service->phase,
                service->close_uncertain, service->first_error.kind, service->first_error.system_errno,
                service->first_error.operation_code);
    CHECK(result == SERVICE_CLEAN);
    CHECK(service_free(&service) && !service);
}

/* ---------- manifest, packets, bootstrap entry ---------- */

static void case_policy_validation(void) {
    no_error error;
    service_launch_policy entries[4];
    service_policy candidate = policy;
    candidate.policies = entries;
    struct { size_t entry; int field; } faults[] = {{1, 0}, {0, 1}, {0, 2}, {0, 3}, {0, 4}, {2, 5}, {0, 6},
                                                    {1, 7}, {0, 8}, {0, 9}, {0, 10}, {0, 11}, {0, 12},
                                                    {0, 13}, {0, 14}, {0, 15}, {1, 16}, {0, 17},
                                                    {0, 18}, {0, 19}, {0, 20}, {0, 21}, {2, 22}};
    for (size_t i = 0; i < sizeof(faults) / sizeof(faults[0]); ++i) {
        memcpy(entries, launch_policies, sizeof(entries));
        candidate = policy;
        candidate.policies = entries;
        service_launch_policy *entry = &entries[faults[i].entry];
        if (faults[i].field == 0) entry->payload_uid = policy.clients[0].uid;  /* Payload is a client. */
        if (faults[i].field == 1) entry->payload_uid = policy.guardian.uid;    /* Payload is the guardian. */
        if (faults[i].field == 2) candidate.guardian.uid = policy.clients[0].uid;
        if (faults[i].field == 3) entry->argument_alphabet = NULL;
        if (faults[i].field == 4) entry->argument_alphabet = "";
        if (faults[i].field == 5) entry->payload_gid = policy.clients[0].gid;  /* Shares the client's files. */
        if (faults[i].field == 6) entry->payload_gid = 0;
        if (faults[i].field == 7) entry->payload_uid = (uint32_t)geteuid();    /* The service's own account. */
        if (faults[i].field == 8) entry->payload_gid = candidate.socket_gid = 4242; /* Owns the socket group. */
        if (faults[i].field == 9) candidate.client_count = 2; /* Payload accounts would be shared by clients. */
        if (faults[i].field == 10) candidate.lease_max_age_ns = candidate.lease_lifetime_ns - 1;
        if (faults[i].field == 11) entry->payload_gid = (uint32_t)getegid();
        if (faults[i].field == 12) candidate.record_pids_max = SERVICE_MIN_PIDS - 1;
        if (faults[i].field == 13) candidate.record_memory_max = SERVICE_MIN_MEMORY - 1;
        if (faults[i].field == 14) candidate.connections_per_account = 0;
        if (faults[i].field == 15) candidate.connections_per_account = SERVICE_CONNECTION_LIMIT / 2 + 1;
        if (faults[i].field == 16) entry->payload_uid = 65533;                 /* Child runs as another account. */
        if (faults[i].field == 17) entry->child_policies |= UINT32_C(1) << 9;  /* Child policy does not exist. */
        if (faults[i].field == 18) entry->child_policies |= UINT32_C(1) << OTHER_TOP; /* Child is top-level. */
        if (faults[i].field == 19) candidate.nested_lease_quota = 0;
        if (faults[i].field == 20) candidate.nested_lease_quota = SERVICE_LEASE_LIMIT + 1;
        if (faults[i].field == 21) entry->payload_uid = policy.clients[0].uid - 5;  /* Range covers a client. */
        if (faults[i].field == 22) entry->payload_uid += 1;  /* Overlaps another policy's range unequally. */
        CHECK(service_allocate(&candidate, &error) == NULL && error.kind == NO_ERROR_ARGUMENT);
    }
    memcpy(entries, launch_policies, sizeof(entries));
    candidate = policy;
    candidate.policies = entries;
    service_state *service = service_allocate(&candidate, &error);
    CHECK(service != NULL && service_free(&service));
}

/* Truncated data or ancillary data never authenticates, whoever sent it. */
static void case_packet_flags(void) {
    int pair[2];
    no_error error;
    peer_identity connector = {0};
    CHECK(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, pair) == 0);
    CHECK(peer_identity_from_connection(&connector, pair[0], &error) && peer_enable_credentials(pair[0], &error));
    for (int variant = 0; variant < 3; ++variant) {
        service_request frame = make(OP_CLOSE, 1, 0);
        received_packet packet;
        CHECK(send(pair[1], &frame, sizeof(frame), 0) == (ssize_t)sizeof(frame));
        CHECK(packet_receive(pair[0], &frame, sizeof(frame), 0, &packet, &error));
        if (variant == 1) packet.flags |= MSG_CTRUNC;
        if (variant == 2) packet.flags |= MSG_TRUNC;
        CHECK(packet_authenticated(&packet, &connector, 0) == (variant == 0));
        CHECK(packet_release(&packet));
    }
    CHECK(service_close_fd(&connector.pidfd));
    close(pair[0]); close(pair[1]);
}

/* REFUSED takes nothing: not a standard stream, not an unopened number, and not
 * a descriptor a started service already owns. */
static void case_bootstrap_refusals(void) {
    size_t baseline = open_descriptors();
    no_error error;
    service_state *fresh = service_allocate(&policy, &error);
    CHECK(fresh != NULL);
    CHECK(service_bootstrap(fresh, STDOUT_FILENO, soon(), &error) == BOOTSTRAP_REFUSED && error.operation_code == 32);
    CHECK(fcntl(STDOUT_FILENO, F_GETFD) != -1);
    CHECK(service_bootstrap(fresh, 1000, soon(), &error) == BOOTSTRAP_REFUSED && error.operation_code == 32);
    CHECK(fresh->phase == BOOT_EMPTY && service_free(&fresh));
    service_state *active = peer_service((no_id){139, 4});
    int listener = active->listener.number;
    CHECK(service_bootstrap(active, listener, soon(), &error) == BOOTSTRAP_REFUSED && error.operation_code == 20);
    CHECK(active->listener.state == FD_OWNED && fcntl(listener, F_GETFD) != -1);
    CHECK(active->guardian.state == FD_EMPTY);
    drain_and_free(active);
    CHECK(open_descriptors() == baseline);
}

/* ---------- admission end ---------- */

static void case_guardian_death(void) {
    service_state *service = peer_service((no_id){139, 3});
    int hold[2];
    CHECK(pipe2(hold, O_CLOEXEC) == 0);
    fflush(NULL);
    pid_t guardian = fork();
    if (guardian == 0) {
        close(hold[1]);
        char byte;
        _exit(read(hold[0], &byte, 1) < 0 ? 1 : 0);
    }
    int number = (int)syscall(SYS_pidfd_open, guardian, 0);
    CHECK(number >= 0 && peer_identity_adopt(&service->guardian_peer, number));
    CHECK(service_run_one(service, 0) == SERVICE_RUNNING && service->phase == BOOT_PEER_EVIDENCE_ONLY);
    close(hold[1]);
    int status;
    CHECK(waitpid(guardian, &status, 0) == guardian);
    CHECK(service_run_one(service, 100) == SERVICE_PENDING && service->phase == BOOT_DRAINING);
    close(hold[0]);
    drain_and_free(service);
}

static void capacity_client(int in, int out) {
    (void)in; (void)out;
    EXPECT(call(client_connect(), make(OP_OPEN_TOP, 1, TOP)).status == STATUS_CAPACITY);
}

/* A core registration that fails after the issuer duplicated its descriptors
 * leaves a tombstone the single owner scan closes. Then the core closes
 * admission and the service ends its own. */
static void case_failed_issue(void) {
    service_state *service = peer_service((no_id){139, 2});
    size_t baseline = open_descriptors();
    pthread_mutex_lock(&service->runtime->registry);
    for (size_t i = 0; i < NO_RECORD_LIMIT; ++i) service->runtime->registered_leases[i] = (no_id){7, i + 1};
    service->runtime->registered_lease_count = NO_RECORD_LIMIT;
    pthread_mutex_unlock(&service->runtime->registry);
    CHECK(pump_until_exit(service, spawn(capacity_client, -1, -1)) == 0);
    service_lease *lease = &service->leases[0];
    authenticated_scope_slot *slot = &service->scopes.slots[0];
    CHECK(service->lease_count == 1 && lease->phase == LEASE_CLOSED && lease->reason == CLOSE_FAILED_ISSUE);
    CHECK(atomic_load(&slot->borrowers) == 0 && slot->resources_settled);
    CHECK(slot->peer.state == FD_CLOSED && slot->epoch_anchor.state == FD_CLOSED);
    CHECK(open_descriptors() == baseline);
    pthread_mutex_lock(&service->runtime->registry);
    service->runtime->registered_lease_count = 0;
    service->runtime->admission_closed = true;
    pthread_mutex_unlock(&service->runtime->registry);
    service_settle(service);
    CHECK(service->phase == BOOT_DRAINING && service_run_one(service, 0) == SERVICE_PENDING);
    drain_and_free(service);
}

/* ---------- top-level authority ---------- */

/* One process, two connections: a lease and its nonce belong to one of them. */
static void cross_client(int in, int out) {
    (void)in; (void)out;
    int first = client_connect(), second = client_connect();
    no_id lease = open_top(first, 1);
    EXPECT(call(second, start_request(lease, 20)).status == STATUS_REJECTED);
    EXPECT(call(second, lease_request(OP_CLOSE, lease)).status == STATUS_REJECTED);
    service_reply again = call(second, make(OP_OPEN_TOP, 1, TOP));
    EXPECT(again.status == STATUS_OK && !same_id(again.lease, lease));
    EXPECT(call(first, start_request(lease, 21)).status == STATUS_UNAVAILABLE);
}

static void expecting_client(int in, int out) {
    (void)in; (void)out;
    EXPECT(call(client_connect(), make(OP_OPEN_TOP, 1, TOP)).status == expected_status);
}

static void argument_client(int in, int out) {
    (void)in; (void)out;
    int number = client_connect();
    no_id lease = open_top(number, 1);
    const char *refused[] = {"a;b", "-x", "", "ALPHA", "a b"};
    for (size_t i = 0; i < sizeof(refused) / sizeof(refused[0]); ++i) {
        service_request request = start_request(lease, 40 + i);
        memset(request.arguments, 0, sizeof(request.arguments));
        strcpy(request.arguments, refused[i]);
        EXPECT(call(number, request).status == STATUS_MALFORMED);
    }
    EXPECT(call(number, start_request(lease, 50)).status == STATUS_UNAVAILABLE);
}

/* One account may use only its quota of an epoch's positions, open or spent. */
static void quota_client(int in, int out) {
    (void)in; (void)out;
    int number = client_connect();
    no_id first = open_top(number, 1), second = open_top(number, 2);
    EXPECT(call(number, lease_request(OP_CLOSE, first)).status == STATUS_OK);
    service_reply refused = call(number, make(OP_OPEN_TOP, 3, TOP));
    EXPECT(refused.status == STATUS_CAPACITY);
    EXPECT(call(number, start_request(second, 70)).status == STATUS_UNAVAILABLE);
}

/* Three connections serve; the fourth from the same account is closed unanswered,
 * and closing one makes room again. */
static void account_limit_client(int in, int out) {
    (void)in; (void)out;
    int held[3];
    for (int i = 0; i < 3; ++i) {
        held[i] = client_connect();
        EXPECT(call(held[i], make(OP_OPEN_TOP, 10 + (uint64_t)i, TOP)).status == STATUS_OK);
    }
    int excess = client_connect();
    service_reply refused = call(excess, make(OP_OPEN_TOP, 20, TOP));
    EXPECT(refused.status == 0xffffffffu || refused.status == 0xfffffffeu);
    close(excess);
    close(held[0]);
    struct timespec pause = {0, 100000000};
    nanosleep(&pause, NULL); /* The service notices the closed connection on its next turn. */
    int again = client_connect();
    EXPECT(call(again, make(OP_OPEN_TOP, 21, TOP)).status == STATUS_OK);
}

static void case_account_connections(void) {
    size_t limit = policy.connections_per_account;
    policy.connections_per_account = 3;
    service_state *service = peer_service((no_id){155, 1});
    CHECK(pump_until_exit(service, spawn(account_limit_client, -1, -1)) == 0);
    size_t refused = 0;
    for (size_t i = 0; i < SERVICE_CONNECTION_LIMIT; ++i)
        if (service->connections[i].phase != CONNECTION_OPEN && service->connections[i].generation) ++refused;
    CHECK(service->lease_count == 4 && refused >= 1);
    drain_and_free(service);
    policy.connections_per_account = limit;
}

/* Spends its quota of one, then holds the connection idle until the parent lets go. */
static void idle_client(int in, int out) {
    int number = client_connect();
    no_id lease = open_top(number, 1);
    EXPECT(call(number, lease_request(OP_CLOSE, lease)).status == STATUS_OK);
    report_lease(out, lease);
    wait_byte(in);
}

/* A spent epoch waits for a lease-less connection only through the grace: an idle or
 * abandoned client cannot keep the host from its next epoch. */
static void case_idle_connection(void) {
    size_t quota = policy.client_lease_quota;
    policy.client_lease_quota = 1;
    int to_child[2], from_child[2];
    CHECK(pipe(to_child) == 0 && pipe(from_child) == 0);
    service_state *service = peer_service((no_id){162, 1});
    pid_t child = spawn(idle_client, to_child[0], from_child[1]);
    pump_lease(service, from_child[0]);
    service_settle(service);
    CHECK(service->phase == BOOT_PEER_EVIDENCE_ONLY); /* Within the grace the client may still observe. */
    for (size_t i = 0; i < SERVICE_CONNECTION_LIMIT; ++i)
        if (service->connections[i].phase == CONNECTION_OPEN)
            service->connections[i].active_ns -= SERVICE_IDLE_GRACE_NS + 1;
    service_settle(service);
    CHECK(service->phase == BOOT_DRAINING);
    CHECK(write(to_child[1], "g", 1) == 1);
    int status = 0;
    CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    for (int i = 0; i < 2; ++i) { close(to_child[i]); close(from_child[i]); }
    drain_and_free(service);
    policy.client_lease_quota = quota;
}

static void case_quota(void) {
    size_t quota = policy.client_lease_quota;
    policy.client_lease_quota = 2;
    service_state *service = peer_service((no_id){151, 1});
    CHECK(pump_until_exit(service, spawn(quota_client, -1, -1)) == 0);
    /* The quota is spent and nothing is open: the epoch drains so the guardian can grant the next. */
    service_settle(service);
    CHECK(service->lease_count == 2 && service->phase == BOOT_DRAINING);
    drain_and_free(service);
    policy.client_lease_quota = quota;
    no_error error;
    service_policy candidate = policy;
    candidate.client_lease_quota = 0;
    CHECK(service_allocate(&candidate, &error) == NULL && error.kind == NO_ERROR_ARGUMENT);
    candidate.client_lease_quota = SERVICE_LEASE_LIMIT + 1;
    CHECK(service_allocate(&candidate, &error) == NULL && error.kind == NO_ERROR_ARGUMENT);
}

/* Leaves its renewed lease open; the parent reads the deadline after the client is gone. */
static void renew_client(int in, int out) {
    (void)in; (void)out;
    int number = client_connect();
    no_id lease = open_top(number, 1);
    EXPECT(call(number, lease_request(OP_RENEW, lease)).status == STATUS_OK);
}

static void renew_refusal_client(int in, int out) {
    (void)in; (void)out;
    int number = client_connect();
    no_id lease = open_top(number, 1), unknown = lease;
    unknown.low ^= 1;
    EXPECT(call(number, lease_request(OP_RENEW, unknown)).status == STATUS_REJECTED);
    EXPECT(call(number, lease_request(OP_CLOSE, lease)).status == STATUS_OK);
    EXPECT(call(number, lease_request(OP_RENEW, lease)).status == STATUS_CLOSED);
}

/* Renewal moves the deadline to one lifetime from now, never past the maximum age. */
static void case_renew(void) {
    uint64_t age = policy.lease_max_age_ns;
    service_state *service = peer_service((no_id){153, 1});
    CHECK(pump_until_exit(service, spawn(renew_client, -1, -1)) == 0);
    const service_lease *renewed = &service->leases[0];
    CHECK(renewed->expires_ns > renewed->opened_ns + policy.lease_lifetime_ns);
    CHECK(pump_until_exit(service, spawn(renew_refusal_client, -1, -1)) == 0);
    drain_and_free(service);
    policy.lease_max_age_ns = policy.lease_lifetime_ns;
    service = peer_service((no_id){153, 2});
    CHECK(pump_until_exit(service, spawn(renew_client, -1, -1)) == 0);
    CHECK(service->leases[0].expires_ns == service->leases[0].opened_ns + policy.lease_max_age_ns);
    drain_and_free(service);
    policy.lease_max_age_ns = age;
}

static void case_top_level(service_state *service) {
    CHECK(pump_until_exit(service, spawn(cross_client, -1, -1)) == 0);
    CHECK(pump_until_exit(service, spawn(argument_client, -1, -1)) == 0);
    policy.clients[0].uid += 1;
    expected_status = STATUS_UNAUTHENTICATED;
    CHECK(pump_until_exit(service, spawn(expecting_client, -1, -1)) == 0);
    policy.clients[0].uid -= 1;
    expected_status = STATUS_OK;
    CHECK(pump_until_exit(service, spawn(expecting_client, -1, -1)) == 0);
}

/* ---------- guardian handoff ----------
 * The test creates the guardian channel, so it is the guardian the service authenticates.
 * It accepts a client on its own listener and hands the connection over. */

static char guardian_path[128];

static void handoff_client(int in, int out) {
    int number = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    strcpy(address.sun_path, guardian_path);
    EXPECT(connect(number, (struct sockaddr *)&address, sizeof(address)) == 0);
    struct timeval timeout = {3, 0};
    setsockopt(number, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    report_lease(out, open_top(number, 1));
    wait_byte(in);
}

static bool hand_over(int channel, int connection, no_id epoch, uint64_t generation) {
    guardian_grant frame = {SERVICE_MAGIC, SERVICE_VERSION, GRANT_CONNECTION, epoch, generation};
    union { struct cmsghdr align; char buffer[CMSG_SPACE(sizeof(int))]; } control;
    memset(&control, 0, sizeof(control));
    struct iovec vector = {.iov_base = &frame, .iov_len = sizeof(frame)};
    struct msghdr header = {.msg_iov = &vector, .msg_iovlen = 1, .msg_control = control.buffer,
        .msg_controllen = sizeof(control.buffer)};
    struct cmsghdr *message = CMSG_FIRSTHDR(&header);
    message->cmsg_level = SOL_SOCKET; message->cmsg_type = SCM_RIGHTS; message->cmsg_len = CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(message), &connection, sizeof(connection));
    return sendmsg(channel, &header, MSG_NOSIGNAL) == (ssize_t)sizeof(frame);
}

static service_state *guarded_service(no_id epoch, int pair[2]) {
    service_state *service = peer_service(epoch);
    CHECK(socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, pair) == 0);
    CHECK(fixture_service_guardian(service, pair[0]));
    return service;
}

/* Spent with a lease still open: the service asks the guardian, once, to start the next
 * epoch beside it, and keeps serving instead of draining. */
static void case_retiring(void) {
    size_t quota = policy.client_lease_quota;
    policy.client_lease_quota = 1;
    int pair[2], to_holder[2], from_holder[2];
    no_id epoch = {172, 1};
    service_state *service = guarded_service(epoch, pair);
    CHECK(pipe2(to_holder, O_CLOEXEC) == 0 && pipe2(from_holder, O_CLOEXEC) == 0);
    pid_t holder = spawn(holder_client, to_holder[0], from_holder[1]);
    pump_lease(service, from_holder[0]);
    service_settle(service);
    guardian_grant frame;
    memset(&frame, 0, sizeof(frame));
    CHECK(recv(pair[1], &frame, sizeof(frame), MSG_DONTWAIT) == (ssize_t)sizeof(frame));
    CHECK(frame.kind == GRANT_RETIRING && same_id(frame.epoch, epoch) && frame.generation == 1);
    service_settle(service);
    CHECK(recv(pair[1], &frame, sizeof(frame), MSG_DONTWAIT) < 0 && errno == EAGAIN);  /* Once only. */
    CHECK(service->retiring && service->phase == BOOT_PEER_EVIDENCE_ONLY);              /* Still serving. */
    send_byte(to_holder[1]);
    CHECK(pump_until_exit(service, holder) == 0);
    drain_and_free(service);
    close(pair[1]);
    int pipes[] = {to_holder[0], to_holder[1], from_holder[0], from_holder[1]};
    for (size_t i = 0; i < sizeof(pipes) / sizeof(pipes[0]); ++i) close(pipes[i]);
    policy.client_lease_quota = quota;
}

static void case_guardian_handoff(void) {
    snprintf(guardian_path, sizeof(guardian_path), "%s/guardian", directory_path);
    int listener = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    strcpy(address.sun_path, guardian_path);
    no_error error;
    /* Credentials must be on before any client packet is queued: accepted sockets inherit
     * them from the listener, and a frame queued earlier arrives without them. */
    CHECK(bind(listener, (struct sockaddr *)&address, sizeof(address)) == 0 && listen(listener, 4) == 0 &&
          peer_enable_credentials(listener, &error));
    int pair[2], to_client[2], from_client[2];
    no_id epoch = {149, 1};
    service_state *service = guarded_service(epoch, pair);
    CHECK(pipe2(to_client, O_CLOEXEC) == 0 && pipe2(from_client, O_CLOEXEC) == 0);
    pid_t client = spawn(handoff_client, to_client[0], from_client[1]);
    int connection = accept4(listener, NULL, NULL, SOCK_CLOEXEC);
    CHECK(connection >= 0 && hand_over(pair[1], connection, epoch, 1));
    close(connection);
    service_lease *lease = lease_by_id(service, pump_lease(service, from_client[0]));
    CHECK(lease && lease->phase == LEASE_OPEN); /* The handed-over connection was adopted and served. */
    send_byte(to_client[1]);
    CHECK(pump_until_exit(service, client) == 0);
    /* A frame on the guardian channel from any other process ends admission. */
    fflush(NULL);
    pid_t forger = fork();
    if (forger == 0) _exit(hand_over(pair[1], 0, epoch, 1) ? 0 : 1);
    int status;
    CHECK(waitpid(forger, &status, 0) == forger && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    CHECK(service_run_one(service, 200) == SERVICE_PENDING && service->phase == BOOT_DRAINING);
    drain_and_free(service);
    close(pair[1]);
    /* So does a frame from the guardian itself for another epoch. */
    service = guarded_service(epoch, pair);
    int spare = dup(listener);
    CHECK(spare >= 0 && hand_over(pair[1], spare, (no_id){149, 2}, 1));
    close(spare);
    CHECK(service_run_one(service, 200) == SERVICE_PENDING && service->phase == BOOT_DRAINING);
    drain_and_free(service);
    close(pair[1]);
    close(listener);
    unlink(guardian_path);
    int pipes[] = {to_client[0], to_client[1], from_client[0], from_client[1]};
    for (size_t i = 0; i < sizeof(pipes) / sizeof(pipes[0]); ++i) close(pipes[i]);
}

/* ---------- nested authority ---------- */

static service_request child_open(uint64_t nonce, uint32_t launch, int parent, int capability) {
    service_request request = make(OP_OPEN_CHILD, nonce, launch);
    request.parent = parents[parent];
    memcpy(request.capability, capabilities[capability], SERVICE_CAPABILITY_BYTES);
    return request;
}

static void helper_client(int in, int out) {
    int number = client_connect();
    service_reply opened = call(number, child_open(1, NESTED, 0, 0));
    EXPECT(opened.status == STATUS_OK);
    no_id lease = opened.lease;
    service_reply replay = call(number, child_open(1, NESTED, 0, 0));
    EXPECT(replay.status == STATUS_EXISTING && same_id(replay.lease, lease));
    EXPECT(call(number, child_open(1, NESTED, 1, 1)).status == STATUS_CONFLICT);
    EXPECT(call(number, child_open(2, NESTED, 0, 1)).status == STATUS_REJECTED);   /* A sibling's capability. */
    service_request forged = child_open(3, NESTED, 0, 0);
    forged.capability[0] ^= 1;
    EXPECT(call(number, forged).status == STATUS_REJECTED);
    EXPECT(call(number, child_open(4, NESTED_OTHER, 0, 0)).status == STATUS_REJECTED);
    EXPECT(call(number, child_open(5, TOP, 0, 0)).status == STATUS_REJECTED);
    EXPECT(call(number, child_open(9, NESTED, 0, 0)).status == STATUS_CAPACITY);    /* Parent 0's quota is 1. */
    EXPECT(call(number, child_open(10, NESTED, 1, 1)).status == STATUS_OK);         /* Parent 1 has its own. */
    EXPECT(call(number, start_request(lease, 10)).status == STATUS_UNAVAILABLE);   /* Member; gate closed. */
    report_lease(out, lease); wait_byte(in);                                         /* Payload moved. */
    EXPECT(call(number, start_request(lease, 11)).status == STATUS_UNAUTHENTICATED);
    EXPECT(call(number, child_open(6, NESTED, 0, 0)).status == STATUS_UNAUTHENTICATED);
    report_lease(out, lease); wait_byte(in);                                         /* Other payload account. */
    EXPECT(call(number, child_open(7, NESTED, 0, 0)).status == STATUS_UNAUTHENTICATED);
    report_lease(out, lease); wait_byte(in);                                         /* Parent fenced. */
    EXPECT(call(number, child_open(8, NESTED, 0, 0)).status == STATUS_CLOSED);
    EXPECT(call(number, start_request(lease, 12)).status == STATUS_CLOSED);
    EXPECT(call(number, lease_request(OP_CLOSE, lease)).status == STATUS_OK);
}

static void publish(no_runtime *runtime, owner_record *record, struct stat cgroup, uint32_t uid) {
    pthread_mutex_lock(&runtime->registry);
    record->anchor.state = ANCHOR_READY;
    record->published_payload = (payload_identity){true, (uint64_t)cgroup.st_dev, (uint64_t)cgroup.st_ino,
        uid, (uint32_t)getgid()};
    pthread_mutex_unlock(&runtime->registry);
}

static void grant(service_state *service, owner_record *record, int index) {
    nested_grant *slot = &service->grants[record->ticket.record.low - 1];
    *slot = (nested_grant){.policy = TOP};
    CHECK(service_random(slot->capability, sizeof(slot->capability)));
    slot->issued = true;
    parents[index] = record->ticket;
    memcpy(capabilities[index], slot->capability, SERVICE_CAPABILITY_BYTES);
}

static service_lease *step(service_state *service, int from, int to, void (*change)(void *), void *argument) {
    service_lease *lease = lease_by_id(service, pump_lease(service, from));
    if (change) change(argument);
    send_byte(to);
    return lease;
}

static owner_record *nested_parents[2];
static service_state *nested_service;
static struct stat nested_cgroup;

static void move_payload(void *unused) {
    (void)unused;
    pthread_mutex_lock(&nested_service->runtime->registry);
    nested_parents[0]->published_payload.inode += 1;
    pthread_mutex_unlock(&nested_service->runtime->registry);
}

static void other_account(void *unused) {
    (void)unused;
    publish(nested_service->runtime, nested_parents[0], nested_cgroup, (uint32_t)getuid() + 1);
}

static void fence_parent(void *unused) {
    (void)unused;
    publish(nested_service->runtime, nested_parents[0], nested_cgroup, (uint32_t)getuid());
    pthread_mutex_lock(&nested_service->runtime->registry);
    owner_fence_locked(nested_parents[0]);
    pthread_mutex_unlock(&nested_service->runtime->registry);
}

static void case_nested(void) {
    size_t children = policy.nested_lease_quota;
    policy.nested_lease_quota = 1;
    service_state *service = nested_service = peer_service((no_id){139, 1});
    nested_cgroup = own_cgroup();
    service->epoch_device = (uint64_t)nested_cgroup.st_dev;
    int to_holder[2], from_holder[2], to_helper[2], from_helper[2];
    CHECK(pipe2(to_holder, O_CLOEXEC) == 0 && pipe2(from_holder, O_CLOEXEC) == 0);
    CHECK(pipe2(to_helper, O_CLOEXEC) == 0 && pipe2(from_helper, O_CLOEXEC) == 0);
    pid_t holder = spawn(holder_client, to_holder[0], from_holder[1]);
    service_lease *top = lease_by_id(service, pump_lease(service, from_holder[0]));
    no_error error;
    for (int i = 0; i < 2; ++i) {
        CHECK(seam_admit(service->runtime, top, 30 + (uint64_t)i, &nested_parents[i], &error) == NO_ACCEPTED);
        publish(service->runtime, nested_parents[i], nested_cgroup, (uint32_t)getuid());
        grant(service, nested_parents[i], i);
    }
    pid_t helper = spawn(helper_client, to_helper[0], from_helper[1]);
    service_lease *child = step(service, from_helper[0], to_helper[1], move_payload, NULL);
    authenticated_scope_slot *slot = child->scope.reference.slot;
    CHECK(child->nested && tickets_equal(child->parent, parents[0]) && registered(service->runtime, child->id));
    CHECK(!slot->identity.parent_is_epoch && tickets_equal(slot->identity.permitted_parent, parents[0]));
    CHECK(slot->peer.state == FD_OWNED && slot->epoch_anchor.state == FD_EMPTY);
    step(service, from_helper[0], to_helper[1], other_account, NULL);
    step(service, from_helper[0], to_helper[1], fence_parent, NULL);
    CHECK(pump_until_exit(service, helper) == 0);
    CHECK(child->phase == LEASE_CLOSED && child->reason == CLOSE_REQUESTED && revoked(service->runtime, child->id));
    /* Registration itself refuses a fenced parent and accepts an eligible one. */
    no_id probe = {139, 77};
    CHECK(!owner_register_lease(service->runtime, probe, &parents[0], &error) &&
          error.kind == NO_ERROR_ADMISSION_CLOSED);
    CHECK(owner_register_lease(service->runtime, probe, &parents[1], &error));
    no_revoke_lease(service->runtime, probe);
    CHECK(revoked(service->runtime, probe));
    send_byte(to_holder[1]);
    CHECK(pump_until_exit(service, holder) == 0);
    pthread_mutex_lock(&service->runtime->registry);
    for (int i = 0; i < 2; ++i) {
        nested_parents[i]->anchor.state = ANCHOR_INVALIDATED; /* The worker's cleanup step, emulated. */
        without_thread(nested_parents[i]);
    }
    pthread_mutex_unlock(&service->runtime->registry);
    drain_and_free(service);
    int pipes[] = {to_holder[0], to_holder[1], from_holder[0], from_holder[1],
                   to_helper[0], to_helper[1], from_helper[0], from_helper[1]};
    for (size_t i = 0; i < sizeof(pipes) / sizeof(pipes[0]); ++i) close(pipes[i]);
    policy.nested_lease_quota = children;
}

/* ---------- capability in the validated spec ---------- */

static bool zeroed(const uint8_t *bytes) {
    for (size_t i = 0; i < SERVICE_CAPABILITY_BYTES; ++i) if (bytes[i]) return false;
    return true;
}

/* The capability is moved from the spec into the record's delivery slot. A replay
 * keeps the first bytes; only whether a capability exists belongs to the request. */
static void case_capability_spec(void) {
    service_state *service = peer_service((no_id){139, 6});
    int to_holder[2], from_holder[2];
    CHECK(pipe2(to_holder, O_CLOEXEC) == 0 && pipe2(from_holder, O_CLOEXEC) == 0);
    pid_t holder = spawn(holder_client, to_holder[0], from_holder[1]);
    service_lease *top = lease_by_id(service, pump_lease(service, from_holder[0]));
    uint8_t first[SERVICE_CAPABILITY_BYTES], second[SERVICE_CAPABILITY_BYTES];
    memset(first, 0x5a, sizeof(first)); memset(second, 0xa5, sizeof(second));
    owner_record *record = NULL, *other = NULL;
    no_error error;
    CHECK(seam_admit_with(service->runtime, top, 60, first, &record, &error) == NO_ACCEPTED && record);
    CHECK(record->delivery.wanted && memcmp(record->delivery.capability, first, sizeof(first)) == 0);
    CHECK(record->spec->delivery.wanted && zeroed(record->spec->delivery.capability));
    CHECK(seam_admit_with(service->runtime, top, 60, second, &other, &error) == NO_EXISTING && !other);
    CHECK(memcmp(record->delivery.capability, first, sizeof(first)) == 0);
    CHECK(seam_admit_with(service->runtime, top, 60, NULL, &other, &error) == NO_REJECTED &&
          error.kind == NO_ERROR_KEY_CONFLICT);
    CHECK(seam_admit_with(service->runtime, top, 61, NULL, &other, &error) == NO_ACCEPTED && other);
    CHECK(!other->delivery.wanted && zeroed(other->delivery.capability));
    send_byte(to_holder[1]);
    CHECK(pump_until_exit(service, holder) == 0);
    pthread_mutex_lock(&service->runtime->registry);
    without_thread(record);
    without_thread(other);
    pthread_mutex_unlock(&service->runtime->registry);
    drain_and_free(service);
    int pipes[] = {to_holder[0], to_holder[1], from_holder[0], from_holder[1]};
    for (size_t i = 0; i < sizeof(pipes) / sizeof(pipes[0]); ++i) close(pipes[i]);
}

/* ---------- application relay ---------- */

static service_request relay_frame(uint16_t opcode, no_id lease, no_ticket ticket, uint64_t nonce, const char *data) {
    service_request request = make(opcode, nonce, 0);
    request.lease = lease;
    request.ticket = ticket;
    if (data) {
        request.data_length = (uint32_t)strlen(data);
        memcpy(request.data, data, request.data_length);
    }
    return request;
}

static no_ticket wait_ticket(int number) {
    no_ticket ticket;
    EXPECT(read(number, &ticket, sizeof(ticket)) == (ssize_t)sizeof(ticket));
    return ticket;
}

static void relay_client(int in, int out) {
    int number = client_connect();
    no_id lease = open_top(number, 1);
    report_lease(out, lease);
    no_ticket ticket = wait_ticket(in), foreign = wait_ticket(in);
    /* A record admitted under another client's lease is neither writable nor observable here. */
    EXPECT(call(number, relay_frame(OP_WRITE, lease, foreign, 12, "x\n")).status == STATUS_REJECTED);
    EXPECT(call(number, relay_frame(OP_OBSERVE, lease, foreign, 13, NULL)).status == STATUS_REJECTED);
    service_reply wrote = call(number, relay_frame(OP_WRITE, lease, ticket, 2, "abc\n"));
    EXPECT(wrote.status == STATUS_OK && wrote.data_length == 4);
    service_reply empty = call(number, relay_frame(OP_READ, lease, ticket, 3, NULL));
    EXPECT(empty.status == STATUS_OK && empty.data_length == 0 && !(empty.flags & REPLY_EOF));
    report_lease(out, lease); wait_byte(in);                                   /* The worker's reply arrives. */
    service_reply read = call(number, relay_frame(OP_READ, lease, ticket, 4, NULL));
    EXPECT(read.status == STATUS_OK && read.data_length == 4 && !memcmp(read.data, "xyz\n", 4));
    EXPECT(read.flags & REPLY_EOF);
    report_lease(out, lease); wait_byte(in);                                   /* The record is fenced. */
    EXPECT(call(number, relay_frame(OP_WRITE, lease, ticket, 8, "late")).status == STATUS_CLOSED);
    service_request oversized = relay_frame(OP_WRITE, lease, ticket, 5, NULL);
    oversized.data_length = SERVICE_DATA_BYTES + 1;
    EXPECT(call(number, oversized).status == STATUS_MALFORMED);
    no_ticket unknown = ticket;
    unknown.record.low += 5;
    EXPECT(call(number, relay_frame(OP_WRITE, lease, unknown, 6, "x\n")).status == STATUS_REJECTED);
    EXPECT(call(number, lease_request(OP_CLOSE, lease)).status == STATUS_OK);
    EXPECT(call(number, relay_frame(OP_READ, lease, ticket, 7, NULL)).status == STATUS_CLOSED);
    service_reply pending = call(number, relay_frame(OP_OBSERVE, lease, ticket, 9, NULL));
    EXPECT(pending.status == STATUS_OK && pending.report_kind == NO_REPORT_PENDING);
    EXPECT(call(number, relay_frame(OP_OBSERVE, lease, unknown, 10, NULL)).status == STATUS_REJECTED);
    report_lease(out, lease); wait_byte(in);                                   /* The record settles. */
    service_reply settled = call(number, relay_frame(OP_OBSERVE, lease, ticket, 11, NULL));
    EXPECT(settled.status == STATUS_OK && settled.report_kind == NO_REPORT_SETTLED_WITHOUT_SCOPE);
}

/* The client vanishes after sending OP_READ: the drained bytes cannot reach it. */
static void lost_relay_client(int in, int out) {
    int number = client_connect();
    no_id lease = open_top(number, 1);
    report_lease(out, lease);
    no_ticket ticket = wait_ticket(in);
    service_request request = relay_frame(OP_READ, lease, ticket, 2, NULL);
    EXPECT(send(number, &request, sizeof(request), 0) == (ssize_t)sizeof(request));
    close(number);
    report_lease(out, lease);
    wait_byte(in);
}

static owner_record *relay_record(service_state *service, service_lease *lease, uint64_t request) {
    owner_record *record = NULL;
    no_error error;
    CHECK(seam_admit(service->runtime, lease, request, &record, &error) == NO_ACCEPTED && record);
    CHECK(record->relay_enabled);
    return record;
}

static void inject_reply(owner_record *record, const char *bytes) {
    pthread_mutex_lock(&record->relay.lock);
    memcpy(record->relay.reply, bytes, strlen(bytes));
    record->relay.reply_length = strlen(bytes);
    record->relay.reply_eof = true;
    pthread_mutex_unlock(&record->relay.lock);
}

/* Records are seam-admitted below the closed gate and have no worker, so the test
 * plays the worker's side of the buffers. */
static void case_relay(void) {
    service_state *service = peer_service((no_id){141, 1});
    int to_client[2], from_client[2], to_holder[2], from_holder[2];
    CHECK(pipe2(to_client, O_CLOEXEC) == 0 && pipe2(from_client, O_CLOEXEC) == 0);
    CHECK(pipe2(to_holder, O_CLOEXEC) == 0 && pipe2(from_holder, O_CLOEXEC) == 0);
    pid_t holder = spawn(holder_client, to_holder[0], from_holder[1]);
    service_lease *held = lease_by_id(service, pump_lease(service, from_holder[0]));
    owner_record *foreign = relay_record(service, held, 69);
    pid_t client = spawn(relay_client, to_client[0], from_client[1]);
    service_lease *lease = lease_by_id(service, pump_lease(service, from_client[0]));
    owner_record *record = relay_record(service, lease, 70);
    CHECK(write(to_client[1], &record->ticket, sizeof(record->ticket)) == (ssize_t)sizeof(record->ticket));
    CHECK(write(to_client[1], &foreign->ticket, sizeof(foreign->ticket)) == (ssize_t)sizeof(foreign->ticket));
    pump_lease(service, from_client[0]);
    CHECK(record->relay.request_length == 4 && !memcmp(record->relay.request, "abc\n", 4));
    inject_reply(record, "xyz\n");
    send_byte(to_client[1]);
    pump_lease(service, from_client[0]);
    pthread_mutex_lock(&service->runtime->registry);
    owner_fence_locked(record);
    pthread_mutex_unlock(&service->runtime->registry);
    send_byte(to_client[1]);
    pump_lease(service, from_client[0]);
    pthread_mutex_lock(&service->runtime->registry);
    without_thread(record);
    pthread_mutex_unlock(&service->runtime->registry);
    service_settle(service);
    send_byte(to_client[1]);
    CHECK(pump_until_exit(service, client) == 0);
    CHECK(record->relay.request_length == 4 && record->relay.reply_length == 0 && lease->phase == LEASE_CLOSED && lease->reason == CLOSE_REQUESTED);

    pid_t lost = spawn(lost_relay_client, to_client[0], from_client[1]);
    service_lease *second = lease_by_id(service, pump_lease(service, from_client[0]));
    owner_record *other = relay_record(service, second, 71);
    inject_reply(other, "lost\n");
    CHECK(write(to_client[1], &other->ticket, sizeof(other->ticket)) == (ssize_t)sizeof(other->ticket));
    pump_lease(service, from_client[0]);
    for (int i = 0; i < 20; ++i) service_run_one(service, 2);
    CHECK(second->phase == LEASE_CLOSED && second->reason == CLOSE_REPLY_LOST);
    send_byte(to_client[1]);
    CHECK(pump_until_exit(service, lost) == 0);

    send_byte(to_holder[1]);
    CHECK(pump_until_exit(service, holder) == 0);
    pthread_mutex_lock(&service->runtime->registry);
    without_thread(other);
    without_thread(foreign);
    pthread_mutex_unlock(&service->runtime->registry);
    drain_and_free(service);
    int pipes[] = {to_client[0], to_client[1], from_client[0], from_client[1],
                   to_holder[0], to_holder[1], from_holder[0], from_holder[1]};
    for (size_t i = 0; i < sizeof(pipes) / sizeof(pipes[0]); ++i) close(pipes[i]);
}

int main(void) {
    fixture_setup("service-authority");
    size_t baseline = open_descriptors();
    case_policy_validation();
    case_packet_flags();
    case_bootstrap_refusals();
    case_guardian_death();
    case_failed_issue();
    case_quota();
    case_renew();
    case_account_connections();
    case_idle_connection();
    case_retiring();
    service_state *service = peer_service((no_id){139, 5});
    case_top_level(service);
    drain_and_free(service);
    case_nested();
    case_capability_spec();
    case_guardian_handoff();
    case_relay();
    CHECK(open_descriptors() == baseline);
    fixture_teardown();
    printf("{\"checks\": %u, \"evidence\": \"peer/lease authority only\", \"protected_execution\": false, "
           "\"nested_payload\": \"the test's own cgroup, published by hand below the closed gate\"}\n", checks);
    return 0;
}
