/* Part of service_authority_acceptance.c, included where it stands there: the guardian
 * handoff cases. It uses that file's helpers and is not compiled on its own. */

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
    guardian_grant frame = {SERVICE_MAGIC, SERVICE_VERSION, GRANT_CONNECTION, epoch, generation, 0, 0};
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
