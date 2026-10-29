#ifndef SERVICE_TEST_SUPPORT_H
#define SERVICE_TEST_SUPPORT_H
/* Shared by the service acceptance binaries. Each includes native_owner.c and then
 * this header exactly once, so the static helpers below exist once per binary. */
#include "native_service.h"
#include <dirent.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(expression) do { if (!(expression)) { \
    fprintf(stderr, "failed line %d: %s\n", __LINE__, #expression); abort(); } ++checks; } while (0)
/* Loop invariants: fail like CHECK but are not counted, so totals do not depend on timing. */
#define REQUIRE(expression) do { if (!(expression)) { \
    fprintf(stderr, "failed line %d: %s\n", __LINE__, #expression); abort(); } } while (0)
#define EXPECT(expression) do { if (!(expression)) { \
    fprintf(stderr, "child failed line %d: %s\n", __LINE__, #expression); _exit(1); } } while (0)

static char directory_path[64], listener_path[108];
static service_policy policy;
static const char *const fixed_argv[] = {"/usr/bin/true"};
static const char *const fixed_env[] = {"LANG=C"};
static service_launch_policy launch_policies[4];

/* NESTED_OTHER is a nested policy TOP does not permit under its records. */
enum { TOP = 1, NESTED = 2, OTHER_TOP = 3, NESTED_OTHER = 4 };
#define ARGUMENT_ALPHABET "abcdefghijklmnopqrstuvwxyz0123456789._"

static uint64_t namespace_inode(const char *name, uint64_t *device) {
    char path[64];
    struct stat status;
    snprintf(path, sizeof(path), "/proc/self/ns/%s", name);
    if (stat(path, &status) != 0) { fprintf(stderr, "no namespace %s\n", name); abort(); }
    *device = (uint64_t)status.st_dev;
    return (uint64_t)status.st_ino;
}

static inline service_namespaces own_namespaces(void) {
    service_namespaces own;
    own.user = namespace_inode("user", &own.device);
    own.pid = namespace_inode("pid", &own.device);
    own.mount = namespace_inode("mnt", &own.device);
    own.cgroup = namespace_inode("cgroup", &own.device);
    return own;
}

/* The test's own cgroup2 directory: an observed identity, never a protected payload. */
static inline struct stat own_cgroup(void) {
    FILE *file = fopen("/proc/self/cgroup", "r");
    char line[512] = {0}, path[600];
    struct stat status;
    if (!file || !fgets(line, sizeof(line), file) || strncmp(line, "0::", 3) != 0) abort();
    fclose(file);
    line[strcspn(line, "\n")] = 0;
    snprintf(path, sizeof(path), "/sys/fs/cgroup%s", line + 3);
    if (stat(path, &status) != 0) abort();
    return status;
}

/* Guardian, clients and payloads are disjoint, as the manifest validation demands:
 * the peer tests never use the guardian principal, so it is a distinct account. */
static void fixture_setup(const char *prefix) {
    signal(SIGPIPE, SIG_IGN);
    snprintf(directory_path, sizeof(directory_path), "/tmp/%s-XXXXXX", prefix);
    if (!mkdtemp(directory_path)) abort();
    snprintf(listener_path, sizeof(listener_path), "%s/listener", directory_path);
    uint32_t uid = (uint32_t)getuid(), gid = (uint32_t)getgid();
    launch_policies[0] = (service_launch_policy){.id = TOP, .executable = "/usr/bin/true", .cwd = "/",
        .fixed_argv = fixed_argv, .fixed_argc = 1, .env = fixed_env, .envc = 1, .max_client_arguments = 4,
        .argument_alphabet = ARGUMENT_ALPHABET, .payload_uid = 65534, .payload_gid = 65534,
        .child_policies = UINT32_C(1) << NESTED};
    launch_policies[1] = launch_policies[0];
    launch_policies[1].id = NESTED; launch_policies[1].nested = true; launch_policies[1].child_policies = 0;
    launch_policies[2] = launch_policies[0];
    launch_policies[2].id = OTHER_TOP;
    launch_policies[3] = launch_policies[1];
    launch_policies[3].id = NESTED_OTHER;
    policy = (service_policy){.guardian = {uid + 1, gid + 1}, .clients = {{uid, gid}},
        .client_count = 1, .policies = launch_policies, .policy_count = 4, .lease_lifetime_ns = 30000000000ULL,
        .client_lease_quota = SERVICE_LEASE_LIMIT, .lease_max_age_ns = 300000000000ULL,
        .record_pids_max = 64, .record_memory_max = 256ULL << 20, .connections_per_account = 8,
        .record_capacity = 8};
}

static void fixture_teardown(void) {
    unlink(listener_path);
    if (rmdir(directory_path) != 0) abort();
}

static size_t open_descriptors(void) {
    DIR *directory = opendir("/proc/self/fd");
    size_t count = 0;
    for (struct dirent *entry = readdir(directory); entry; entry = readdir(directory))
        if (entry->d_name[0] != '.') ++count;
    closedir(directory);
    return count;
}

/* ---------- client side, run only in forked children ---------- */

static int client_connect(void) {
    int number = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    strcpy(address.sun_path, listener_path);
    EXPECT(connect(number, (struct sockaddr *)&address, sizeof(address)) == 0);
    struct timeval timeout = {3, 0};
    setsockopt(number, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    return number;
}

static service_request make(uint16_t opcode, uint64_t nonce, uint32_t launch) {
    service_request request;
    memset(&request, 0, sizeof(request));
    request.magic = SERVICE_MAGIC; request.version = SERVICE_VERSION; request.opcode = opcode;
    request.nonce = (no_id){0, nonce}; request.request = (no_id){0, nonce}; request.policy = launch;
    return request;
}

static service_reply receive_reply(int number) {
    service_reply reply;
    memset(&reply, 0, sizeof(reply));
    reply.status = 0xffffffffu;
    if (recv(number, &reply, sizeof(reply), 0) != (ssize_t)sizeof(reply)) reply.status = 0xffffffffu;
    return reply;
}

static service_reply call(int number, service_request request) {
    if (send(number, &request, sizeof(request), MSG_NOSIGNAL) != (ssize_t)sizeof(request)) {
        service_reply failed = {.status = 0xfffffffeu};
        return failed;
    }
    return receive_reply(number);
}

static service_request start_request(no_id lease, uint64_t request) {
    service_request start = make(OP_START, request, 0);
    start.lease = lease; start.argc = 1;
    strcpy(start.arguments, "alpha");
    return start;
}

static service_request lease_request(uint16_t opcode, no_id lease) {
    service_request request = make(opcode, 900, 0);
    request.lease = lease;
    return request;
}

static no_id open_top(int number, uint64_t nonce) {
    service_reply reply = call(number, make(OP_OPEN_TOP, nonce, TOP));
    if (reply.status != STATUS_OK)
        fprintf(stderr, "open_top status %u error %d/%d/%u\n", reply.status, reply.error.kind,
                reply.error.system_errno, reply.error.operation_code);
    EXPECT(reply.status == STATUS_OK && (reply.lease.high || reply.lease.low) && reply.lease_deadline_ns);
    return reply.lease;
}

static void wait_byte(int number) { char byte; EXPECT(read(number, &byte, 1) == 1); }
static void report_lease(int number, no_id lease) { EXPECT(write(number, &lease, sizeof(lease)) == sizeof(lease)); }

/* ---------- parent side ---------- */

static pid_t spawn(void (*body)(int, int), int in, int out) {
    fflush(NULL);
    pid_t child = fork();
    if (child == 0) { body(in, out); _exit(0); }
    CHECK(child > 0);
    return child;
}

/* Pending is legitimate only once admission has ended and the service drains. */
static int pump_until_exit(service_state *service, pid_t child) {
    uint64_t limit = owner_now() + 10000000000ULL;
    for (;;) {
        service_result result = service_run_one(service, 5);
        REQUIRE(result == SERVICE_RUNNING || (result == SERVICE_PENDING && service->phase == BOOT_DRAINING));
        if (result == SERVICE_PENDING) { struct timespec pause = {0, 5000000}; nanosleep(&pause, NULL); }
        int status;
        if (waitpid(child, &status, WNOHANG) == child) {
            for (int i = 0; i < 5; ++i) service_run_one(service, 1);
            return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
        }
        REQUIRE(owner_now() < limit);
    }
}

static no_id pump_lease(service_state *service, int number) {
    uint64_t limit = owner_now() + 10000000000ULL;
    for (;;) {
        REQUIRE(service_run_one(service, 5) == SERVICE_RUNNING);
        struct pollfd event = {.fd = number, .events = POLLIN};
        if (poll(&event, 1, 0) == 1) break;
        REQUIRE(owner_now() < limit);
    }
    no_id lease;
    CHECK(read(number, &lease, sizeof(lease)) == sizeof(lease));
    return lease;
}

static void send_byte(int number) { CHECK(write(number, "g", 1) == 1); }
static inline bool tickets_equal(no_ticket a, no_ticket b) {
    return same_id(a.service_epoch, b.service_epoch) && same_id(a.record, b.record);
}

static void holder_client(int in, int out) {
    int number = client_connect();
    report_lease(out, open_top(number, 1));
    wait_byte(in);
}
static bool registered(no_runtime *runtime, no_id lease) { return owner_lease_registered(runtime, lease); }
static bool revoked(no_runtime *runtime, no_id lease) { return owner_lease_closed(runtime, lease); }

static service_lease *lease_by_id(service_state *service, no_id id) {
    for (size_t i = 0; i < service->lease_count; ++i)
        if (same_id(service->leases[i].id, id)) return &service->leases[i];
    return NULL;
}

static void without_thread(owner_record *record) {
    owner_fence_locked(record);
    record->start = THREAD_NO_THREAD;
    record->join = JOIN_ELIGIBLE;
    record->proof = (finished_proof){.kind = PROOF_WITHOUT_SCOPE, .no_child = true,
        .io_settled = true, .wait = {NO_WAIT_NOT_APPLICABLE, 0},
        .detail.without_scope = {NO_WORKER_CREATED}};
    record->report.start = (no_start_outcome){NO_START_FAILED_WITHOUT_CHILD, {NO_ERROR_THREAD_START, EAGAIN, 0}};
    atomic_store_explicit(&record->finished, true, memory_order_release);
}

/* Admission below the closed production gate, driven by the issuer's real scope. */
static no_submit_result seam_admit_with(no_runtime *runtime, service_lease *lease, uint64_t request,
                                        const uint8_t *capability, owner_record **record, no_error *error) {
    static const char *argv[] = {"/usr/bin/true", "alpha", NULL};
    no_validated_spec input = {"/usr/bin/true", "/", argv, fixed_env, 2, 1, 65534, 65534, capability, 0, 0};
    *error = (no_error){0};
    scope_reference prepared = {0};
    if (!scope_retain(lease->scope.reference, &prepared)) { error->kind = NO_ERROR_ARGUMENT; return NO_REJECTED; }
    immutable_spec_arena *spec = copy_spec(&input, error);
    CHECK(spec != NULL);
    no_ticket ticket;
    pthread_mutex_lock(&runtime->registry);
    no_submit_result result = admit_protected_locked(runtime, &prepared, (no_request_key){lease->id, {0, request}},
                                                     &spec, record, &ticket, error);
    pthread_mutex_unlock(&runtime->registry);
    scope_release(&prepared); free(spec);
    return result;
}

static no_submit_result seam_admit(no_runtime *runtime, service_lease *lease, uint64_t request,
                                   owner_record **record, no_error *error) {
    return seam_admit_with(runtime, lease, request, NULL, record, error);
}

static service_state *peer_service(no_id epoch) {
    no_error error;
    service_state *service = service_allocate(&policy, &error);
    CHECK(service != NULL);
    int listener = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    strcpy(address.sun_path, listener_path);
    unlink(listener_path);
    CHECK(bind(listener, (struct sockaddr *)&address, sizeof(address)) == 0 && listen(listener, 16) == 0);
    int anchor = open(directory_path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    CHECK(anchor >= 0);
    CHECK(fixture_service_peer_only(service, listener, anchor, epoch));
    return service;
}
#endif
