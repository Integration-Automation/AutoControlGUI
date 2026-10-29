#define _GNU_SOURCE
#include "owner_fixture.h"
#include "owner_internal.h"
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdatomic.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/sysmacros.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static uint64_t now(void) {
    struct timespec value; clock_gettime(CLOCK_MONOTONIC, &value);
    return (uint64_t)value.tv_sec * 1000000000ULL + (uint64_t)value.tv_nsec;
}
static no_deadline deadline(unsigned ms) { return (no_deadline){now() + ms * 1000000ULL}; }
static void pause_once(void) { struct timespec d = {.tv_nsec = 1000000}; nanosleep(&d, NULL); }
static int failed;

static void emit(const char *name, bool passed, fixture_snapshot s, no_report report) {
    printf("{\"case\":\"%s\",\"expected\":\"pass\",\"observed\":\"%s\","
        "\"launch_attempts\":%u,\"launch_active\":%d,\"owned_slots\":%u,\"close_attempts\":%u,"
        "\"worker_finished\":%d,\"joined\":%d,\"child_dead\":%d,\"no_child\":%d,"
        "\"wait_kind\":%d,\"wait_value\":%d,\"io_settled\":%d,\"sticky\":%d,"
        "\"fixture_complete\":%d,\"production_receipt\":%d,\"scope_removal\":\"not_applicable_direct_fixture\","
        "\"request_id\":%llu,\"successful_joins\":%u,\"started_published\":%d,\"creation_returned\":%d,"
        "\"startup_kind\":%d,\"startup_errno\":%d,\"scratch_diagnostic\":%d,"
        "\"native_success\":%d,\"pidfd_adopted\":%d}\n",
        name, passed ? "pass" : "fail", s.launch_attempts, !s.joined, s.owned_count, s.close_attempts,
        s.worker_finished, s.joined, s.child_dead, s.no_child, s.wait.kind, s.wait.value,
        s.io_settled, s.sticky, s.direct_fixture_complete, report.kind == NO_REPORT_RETIRED,
        (unsigned long long)s.request_id, s.successful_joins, s.started_published,
        s.creation_returned, s.start.kind, s.start.failure.system_errno, s.scratch_diagnostic,
        s.native_success, s.pidfd_adopted);
    fflush(stdout);
    failed += !passed;
}

static fixture_snapshot wait_state(no_runtime *runtime, no_ticket ticket, unsigned mode) {
    fixture_snapshot snapshot = {0}; no_deadline end = deadline(6500);
    do {
        no_runtime_maintain(runtime, deadline(2));
        if (fixture_inspect(runtime, ticket, &snapshot)) {
            if ((mode == 0 && snapshot.joined) || (mode == 1 && snapshot.before_call) ||
                (mode == 2 && snapshot.after_success) || (mode == 3 && snapshot.worker_finished) ||
                (mode == 4 && snapshot.failed_call) || (mode == 5 && snapshot.creation_returned) ||
                (mode == 6 && snapshot.native_success)) return snapshot;
        }
        pause_once();
    } while (now() < end.monotonic_ns);
    return snapshot;
}

static bool shutdown_ok(no_runtime **runtime) {
    no_error error;
    bool result = no_runtime_shutdown(runtime, deadline(6500), &error);
    if (!result) ++failed;
    return result;
}

/* Polls the relay like the service does, until `want` bytes or the deadline. */
static size_t relay_collect(no_runtime *runtime, no_id lease, no_ticket ticket, char *buffer, size_t want,
                            bool *eof) {
    size_t total = 0;
    uint64_t limit = now() + 3000000000ULL;
    *eof = false;
    while (total < want && !*eof && now() < limit) {
        size_t length = 0;
        no_error error;
        if (!owner_relay_read(runtime, lease, ticket, (uint8_t *)buffer + total, want - total, &length, eof, &error))
            break;
        total += length;
        if (!length) owner_pause();
    }
    return total;
}

/* Application bytes through the relay: echo, a partial write at the buffer bound,
 * EOF after the helper exits, refusal for a foreign lease, after the worker
 * finishes, and after the lease closes. */
static void relay_case(const char *path) {
    no_runtime *runtime = fixture_runtime(2); no_ticket ticket, held; no_error error; no_id lease;
    if (!runtime || fixture_submit(runtime, 1, path, FIXTURE_RELAY, &ticket, &error) != NO_ACCEPTED ||
        !fixture_relay_lease(runtime, ticket, &lease)) exit(105);
    char reply[16];
    bool eof;
    size_t accepted;
    bool echoed = owner_relay_write(runtime, lease, ticket, (const uint8_t *)"alpha\n", 6, &accepted, &error) &&
        accepted == 6 && relay_collect(runtime, lease, ticket, reply, 6, &eof) == 6 && !memcmp(reply, "alpha\n", 6);
    no_id foreign = {lease.high ^ 1, lease.low};
    bool refused_foreign = !owner_relay_write(runtime, foreign, ticket, (const uint8_t *)"x\n", 2, &accepted, &error) &&
        error.kind == NO_ERROR_UNKNOWN_TICKET && accepted == 0;
    bool goodbye = owner_relay_write(runtime, lease, ticket, (const uint8_t *)"exit\n", 5, &accepted, &error) &&
        relay_collect(runtime, lease, ticket, reply, sizeof(reply), &eof) == 4 && !memcmp(reply, "bye\n", 4);
    fixture_snapshot done = wait_state(runtime, ticket, 0);
    relay_collect(runtime, lease, ticket, reply, sizeof(reply), &eof);
    bool finished = eof && !owner_relay_write(runtime, lease, ticket, (const uint8_t *)"x\n", 2, &accepted, &error) &&
        error.kind == NO_ERROR_ADMISSION_CLOSED;
    static uint8_t oversized[2 * NO_RELAY_BYTES];
    memset(oversized, 'x', sizeof(oversized));
    if (fixture_submit(runtime, 2, path, FIXTURE_RELAY | FIXTURE_CHILD_HOLD, &held, &error) != NO_ACCEPTED) exit(106);
    bool bounded = owner_relay_write(runtime, lease, held, oversized, sizeof(oversized), &accepted, &error) &&
        accepted == NO_RELAY_BYTES;
    no_revoke_lease(runtime, lease);
    size_t length;
    bool closed = !owner_relay_read(runtime, lease, held, (uint8_t *)reply, sizeof(reply), &length, &eof, &error) &&
        error.kind == NO_ERROR_ADMISSION_CLOSED && length == 0;
    no_revoke(runtime, held);
    fixture_snapshot released = wait_state(runtime, held, 0);
    bool passed = echoed && refused_foreign && goodbye && finished && bounded && closed &&
        done.wait.kind == NO_WAIT_EXITED && done.wait.value == 37 && done.owned_count == 0 &&
        released.owned_count == 0 && released.direct_fixture_complete;
    emit("relay_round_trip_and_fences", passed, done, no_observe(runtime, ticket, deadline(10)));
    printf("{\"evidence\":\"relay\",\"echoed\":%d,\"refused_foreign\":%d,\"goodbye\":%d,\"finished\":%d,"
           "\"bounded\":%d,\"closed_lease\":%d}\n", echoed, refused_foreign, goodbye, finished, bounded, closed);
    shutdown_ok(&runtime);
}

static void simple_case(const char *name, const char *path, unsigned flags, bool ignored, bool cancel) {
    struct sigaction action = {.sa_handler = ignored ? SIG_IGN : SIG_DFL}, previous;
    sigemptyset(&action.sa_mask); sigaction(SIGCHLD, &action, &previous);
    no_runtime *runtime = fixture_runtime(4); no_ticket ticket; no_error error;
    if (!runtime || fixture_submit(runtime, 1, path, flags, &ticket, &error) != NO_ACCEPTED) exit(90);
    fixture_snapshot early = {0};
    if (flags & FIXTURE_HOLD_BEFORE) early = wait_state(runtime, ticket, 1);
    if (flags & FIXTURE_HOLD_AFTER) early = wait_state(runtime, ticket, 2);
    uint64_t revoked_at = now();
    if (cancel) no_revoke(runtime, ticket);
    no_report pending = no_observe(runtime, ticket, deadline(20));
    fixture_release(runtime, ticket);
    fixture_snapshot done = wait_state(runtime, ticket, 0);
    no_report report = no_observe(runtime, ticket, deadline(20));
    bool passed = done.joined && done.direct_fixture_complete && done.owned_count == 0 &&
        report.kind != NO_REPORT_RETIRED && pending.kind != NO_REPORT_RETIRED;
    if (flags & FIXTURE_HOLD_BEFORE) passed &= early.before_call && done.launch_attempts == 0 && done.no_child;
    if (flags & FIXTURE_HOLD_AFTER) passed &= early.after_success && done.child_dead;
    if (flags & FIXTURE_FAIL_THREAD) passed &= done.no_child && done.launch_attempts == 0;
    if (ignored && done.child_dead) passed &= done.wait.kind == NO_WAIT_STATUS_UNAVAILABLE;
    if (!strcmp(name, "normal_exit") || !strcmp(name, "closed_stdin_exec"))
        passed &= done.wait.kind == NO_WAIT_EXITED && done.wait.value == 37;
    if (!strcmp(name, "exec_failure")) passed &= done.start.kind == NO_START_EXEC_FAILED &&
        done.start.failure.system_errno == ENOENT && done.wait.kind == NO_WAIT_EXITED && done.wait.value == 127;
    uint64_t revoke_elapsed = now() - revoked_at;
    if (cancel && done.child_dead) passed &= done.wait.kind == NO_WAIT_SIGNALLED && done.wait.value == SIGKILL &&
        revoke_elapsed < 2000000000ULL;
    if (flags & FIXTURE_NESTED_BOOTSTRAP) passed &= done.delivery_wiped &&
        (cancel ? !done.nested_delivered : done.nested_delivered && done.wait.kind == NO_WAIT_EXITED &&
         done.wait.value == 37);
    if (flags & FIXTURE_FAIL_CHILD_SETUP) passed &= done.start.kind == NO_START_EXEC_FAILED &&
        done.start.failure.system_errno == EBADF;
    emit(name, passed, done, report);
    if (cancel && done.child_dead)
        printf("{\"evidence\":\"cancel_deadline\",\"case\":\"%s\",\"elapsed_ns\":%llu,"
            "\"limit_ns\":2000000000,\"emergency_owner_deadline_ns\":4000000000}\n",
            name, (unsigned long long)revoke_elapsed);
    shutdown_ok(&runtime);
    sigaction(SIGCHLD, &previous, NULL);
}

static void independent_case(const char *path) {
    no_runtime *runtime = fixture_runtime(4); no_ticket held, other; no_error error;
    if (fixture_submit(runtime, 1, path, FIXTURE_HOLD_BEFORE, &held, &error) != NO_ACCEPTED) exit(91);
    fixture_snapshot before = wait_state(runtime, held, 1);
    if (fixture_submit(runtime, 2, path, FIXTURE_CHILD_HOLD, &other, &error) != NO_ACCEPTED) exit(92);
    wait_state(runtime, other, 2); uint64_t revoked_at = now(); no_revoke(runtime, other);
    fixture_snapshot done = wait_state(runtime, other, 0), still;
    fixture_inspect(runtime, held, &still);
    bool passed = before.before_call && !still.worker_finished && !still.joined && done.direct_fixture_complete &&
        done.wait.kind == NO_WAIT_SIGNALLED && done.wait.value == SIGKILL && now() - revoked_at < 2000000000ULL;
    emit("held_record_stays_pending", before.before_call && !still.joined && !still.worker_finished,
        still, no_observe(runtime, held, deadline(10)));
    emit("independent_record_retirement", passed, done, no_observe(runtime, other, deadline(10)));
    no_revoke(runtime, held); fixture_release(runtime, held); wait_state(runtime, held, 0);
    shutdown_ok(&runtime);
}

typedef struct {
    no_runtime *runtime;
    const char *path;
    no_ticket ticket;
    no_submit_result result;
    unsigned flags;
    atomic_bool returned;
} creator_args;
static void *creator(void *raw) {
    creator_args *args = raw; no_error error;
    args->result = fixture_submit(args->runtime, 1, args->path, args->flags, &args->ticket, &error);
    atomic_store(&args->returned, true);
    return NULL;
}

static void start_publication_case(const char *path) {
    no_runtime *runtime = fixture_runtime(2);
    creator_args args = {.runtime = runtime, .path = path, .flags = FIXTURE_HOLD_START};
    atomic_init(&args.returned, false);
    pthread_t thread; if (pthread_create(&thread, NULL, creator, &args)) exit(93);
    no_ticket ticket = {{135, 1}, {0, 1}};
    fixture_snapshot done = wait_state(runtime, ticket, 3);
    bool pending = done.creation_returned && done.worker_finished && !done.started_published && !done.joined;
    no_report before = no_observe(runtime, ticket, deadline(20));
    emit("creator_before_started_publication", pending && done.successful_joins == 0, done, before);
    fixture_release(runtime, ticket); pthread_join(thread, NULL);
    done = wait_state(runtime, ticket, 0);
    emit("creator_publication_join_fence", pending && args.result == NO_ACCEPTED &&
        before.kind != NO_REPORT_RETIRED && done.direct_fixture_complete, done,
        no_observe(runtime, ticket, deadline(20)));
    shutdown_ok(&runtime);
}

static void retry_case(const char *path) {
    no_runtime *runtime = fixture_runtime(2); no_ticket ticket, repeat; no_error error;
    if (fixture_submit(runtime, 1, path, FIXTURE_HOLD_AFTER | FIXTURE_CHILD_HOLD, &ticket, &error) != NO_ACCEPTED) exit(94);
    wait_state(runtime, ticket, 2);
    no_submit_result duplicate = fixture_submit(runtime, 1, path, 0, &repeat, &error);
    uint64_t revoked_at = now();
    no_revoke_lease(runtime, (no_id){0, 1}); fixture_release(runtime, ticket);
    fixture_snapshot done = wait_state(runtime, ticket, 0);
    bool once = no_revoke(runtime, ticket); unsigned closed = done.close_attempts;
    wait_state(runtime, ticket, 0); fixture_inspect(runtime, ticket, &done);
    emit("lost_ack_lease_loss_repeat_close", duplicate == NO_EXISTING && once &&
        ticket.record.low == repeat.record.low && done.launch_attempts == 1 &&
        closed == done.close_attempts && done.direct_fixture_complete &&
        done.wait.kind == NO_WAIT_SIGNALLED && done.wait.value == SIGKILL &&
        now() - revoked_at < 2000000000ULL, done,
        no_observe(runtime, ticket, deadline(10)));
    printf("{\"evidence\":\"lease_cancel_deadline\",\"elapsed_ns\":%llu,\"limit_ns\":2000000000}\n",
        (unsigned long long)(now() - revoked_at));
    shutdown_ok(&runtime);
}

static void sticky_case(const char *path) {
    no_runtime *runtime = fixture_runtime(1); no_ticket ticket; no_error error;
    if (fixture_submit(runtime, 1, path, FIXTURE_FAIL_CLOSE | FIXTURE_CHILD_HOLD, &ticket, &error) != NO_ACCEPTED) exit(95);
    wait_state(runtime, ticket, 2); no_revoke(runtime, ticket);
    fixture_snapshot done = wait_state(runtime, ticket, 0); unsigned closed = done.close_attempts;
    int sentinels[32], sentinel = -1; size_t count = 0;
    while (count < 32 && sentinel != done.closed_pidfd) {
        sentinel = open("/dev/null", O_RDONLY | O_CLOEXEC);
        if (sentinel < 0) break;
        sentinels[count++] = sentinel;
    }
    no_revoke(runtime, ticket); no_runtime_maintain(runtime, deadline(10));
    fixture_inspect(runtime, ticket, &done);
    no_report report = no_observe(runtime, ticket, deadline(10));
    emit("sticky_close_consumed_once", done.joined && done.sticky && !done.direct_fixture_complete &&
        done.owned_count == 0 && closed == done.close_attempts && report.kind == NO_REPORT_STICKY_UNKNOWN &&
        sentinel == done.closed_pidfd && fcntl(sentinel, F_GETFD) != -1,
        done, report);
    printf("{\"evidence\":\"sticky_close_sentinel\",\"closed_pidfd\":%d,\"sentinel\":%d,"
        "\"sentinel_valid\":%d}\n", done.closed_pidfd, sentinel, fcntl(sentinel, F_GETFD) != -1);
    while (count) close(sentinels[--count]);
    bool released = no_runtime_shutdown(&runtime, deadline(10), &error);
    if (released || !runtime) ++failed;
}

static void revoke_before_submit_case(const char *path) {
    no_runtime *runtime = fixture_runtime(2); no_ticket ticket; no_error error;
    no_revoke_lease(runtime, (no_id){0, 1});
    no_submit_result result = fixture_submit(runtime, 1, path, 0, &ticket, &error);
    bool passed = result == NO_REJECTED && error.kind == NO_ERROR_ADMISSION_CLOSED;
    printf("{\"case\":\"revoke_before_submit\",\"expected\":\"pass\",\"observed\":\"%s\","
        "\"submit_result\":%d,\"error_kind\":%d,\"launch_attempts\":0,\"production_receipt\":0}\n",
        passed ? "pass" : "fail", result, error.kind);
    failed += !passed;
    shutdown_ok(&runtime);
}

static void failed_scratch_case(const char *path) {
    no_runtime *runtime = fixture_runtime(2); no_ticket ticket; no_error error;
    if (fixture_submit(runtime, 1, path, FIXTURE_ADMISSION_PROBE, &ticket, &error) != NO_ACCEPTED) exit(96);
    fixture_snapshot held = wait_state(runtime, ticket, 4);
    int sentinel = open("/dev/null", O_RDONLY | O_CLOEXEC);
    bool reused = sentinel >= 0 && sentinel == held.scratch_diagnostic;
    no_revoke(runtime, ticket); fixture_release(runtime, ticket);
    fixture_snapshot done = wait_state(runtime, ticket, 0);
    int flags = fcntl(sentinel, F_GETFD);
    bool passed = held.failed_call && reused && flags != -1 && done.no_child && done.direct_fixture_complete &&
        done.start.failure.system_errno == EACCES;
    emit("failed_clone_scratch_reuse", passed, done, no_observe(runtime, ticket, deadline(10)));
    printf("{\"evidence\":\"failed_clone_sentinel\",\"scratch\":%d,\"sentinel\":%d,"
        "\"reused\":%d,\"sentinel_valid\":%d}\n", held.scratch_diagnostic, sentinel, reused, flags != -1);
    if (sentinel >= 0) close(sentinel);
    shutdown_ok(&runtime);
}

typedef struct { no_runtime *runtime; atomic_bool stop; } maintenance_args;
static void *maintainer(void *raw) {
    maintenance_args *args = raw;
    while (!atomic_load(&args->stop)) {
        no_runtime_maintain(args->runtime, deadline(2)); pause_once();
    }
    return NULL;
}

static void concurrent_maintenance_case(const char *path) {
    no_runtime *runtime = fixture_runtime(2); no_ticket ticket; no_error error;
    maintenance_args args = {.runtime = runtime}; atomic_init(&args.stop, false);
    pthread_t threads[4];
    for (size_t i = 0; i < 4; ++i) if (pthread_create(&threads[i], NULL, maintainer, &args)) exit(97);
    if (fixture_submit(runtime, 1, path, FIXTURE_HOLD_AFTER | FIXTURE_CHILD_HOLD, &ticket, &error) != NO_ACCEPTED) exit(98);
    wait_state(runtime, ticket, 2); no_revoke(runtime, ticket); fixture_release(runtime, ticket);
    fixture_snapshot done = wait_state(runtime, ticket, 0);
    atomic_store(&args.stop, true);
    for (size_t i = 0; i < 4; ++i) pthread_join(threads[i], NULL);
    emit("concurrent_maintainers_one_join", done.direct_fixture_complete && done.successful_joins == 1,
        done, no_observe(runtime, ticket, deadline(10)));
    shutdown_ok(&runtime);
}

static void allocation_cases(void) {
    for (unsigned point = 1; point <= 2; ++point) {
        no_error error; bool passed = fixture_allocation_failure(point, &error);
        printf("{\"case\":\"allocation_failure_%u\",\"expected\":\"pass\",\"observed\":\"%s\","
            "\"error_kind\":%d,\"launch_attempts\":0,\"owned_slots\":0,\"production_receipt\":0}\n",
            point, passed ? "pass" : "fail", error.kind);
        failed += !passed;
    }
}

static void closed_stdin_case(const char *path) {
    int saved = fcntl(0, F_DUPFD_CLOEXEC, 10);
    if (saved < 0) exit(99);
    close(0);
    simple_case("closed_stdin_exec", path, 0, false, false);
    if (dup2(saved, 0) != 0) exit(100);
    close(saved);
}

typedef struct {
    no_runtime *runtime;
    no_ticket ticket;
    atomic_bool entered, release;
} report_holder_args;

static void *report_holder(void *raw) {
    report_holder_args *args = raw;
    fixture_hold_report(args->runtime, args->ticket, &args->entered, &args->release);
    return NULL;
}

static void failed_create_observer_case(const char *path) {
    no_runtime *runtime = fixture_runtime(2);
    creator_args args = {.runtime = runtime, .path = path, .flags = FIXTURE_HOLD_START | FIXTURE_FAIL_THREAD};
    atomic_init(&args.returned, false);
    pthread_t creating, observing;
    if (pthread_create(&creating, NULL, creator, &args)) exit(101);
    no_ticket ticket = {{135, 1}, {0, 1}};
    wait_state(runtime, ticket, 5);
    report_holder_args holder = {.runtime = runtime, .ticket = ticket};
    atomic_init(&holder.entered, false); atomic_init(&holder.release, false);
    if (pthread_create(&observing, NULL, report_holder, &holder)) exit(102);
    uint64_t expiry = now() + 1000000000ULL;
    while (!atomic_load(&holder.entered) && now() < expiry) pause_once();
    bool locked = atomic_load(&holder.entered);
    fixture_release(runtime, ticket);
    expiry = now() + 1000000000ULL;
    while (!fixture_failure_write_attempted(runtime, ticket) && now() < expiry) pause_once();
    bool attempted = fixture_failure_write_attempted(runtime, ticket);
    expiry = now() + 50000000ULL;
    while (!atomic_load(&args.returned) && now() < expiry) pause_once();
    bool blocked = !atomic_load(&args.returned);
    atomic_store(&holder.release, true);
    pthread_join(observing, NULL); pthread_join(creating, NULL);
    fixture_snapshot done = wait_state(runtime, ticket, 0);
    emit("failed_create_report_lock", locked && attempted && blocked && done.direct_fixture_complete &&
        done.no_child && done.launch_attempts == 0 && done.start.failure.kind == NO_ERROR_THREAD_START,
        done, no_observe(runtime, ticket, deadline(10)));
    printf("{\"evidence\":\"failed_create_observer_overlap\",\"observer_held_report_lock\":%d,"
        "\"creator_attempted_report_write\":%d,\"creator_blocked_until_release\":%d}\n", locked, attempted, blocked);
    shutdown_ok(&runtime);
}

static void adoption_after_revoke_case(const char *path) {
    no_runtime *runtime = fixture_runtime(2); no_ticket ticket; no_error error;
    if (fixture_submit(runtime, 1, path, FIXTURE_HOLD_ADOPTION | FIXTURE_CHILD_HOLD, &ticket, &error) != NO_ACCEPTED)
        exit(103);
    fixture_snapshot before = wait_state(runtime, ticket, 6);
    no_revoke(runtime, ticket);
    fixture_inspect(runtime, ticket, &before);
    no_report pending = no_observe(runtime, ticket, deadline(10));
    bool held = before.native_success && !before.pidfd_adopted && !before.worker_finished && before.revoked &&
        before.owned_count == 4 && pending.kind == NO_REPORT_PENDING;
    emit("revoked_before_pidfd_slot_adoption", held, before, pending);
    uint64_t released_at = now(); fixture_release(runtime, ticket);
    fixture_snapshot done = wait_state(runtime, ticket, 0);
    emit("late_success_adopted_then_retired", held && done.pidfd_adopted && done.direct_fixture_complete &&
        done.wait.kind == NO_WAIT_SIGNALLED && done.wait.value == SIGKILL &&
        now() - released_at < 2000000000ULL, done, no_observe(runtime, ticket, deadline(10)));
    shutdown_ok(&runtime);
}

/* The launcher's stream and signal policy, observed from inside the child: the
 * parent ignores SIGPIPE and blocks SIGUSR2 before any launch. */
static bool sink_stream(int number) {
    struct stat status;
    return fstat(number, &status) == 0 && S_ISCHR(status.st_mode) && status.st_rdev == makedev(1, 3);
}

static int child_policy_violation(int first_closed, bool relayed) {
    struct sigaction pipe_action;
    sigset_t mask;
    if ((!relayed && !sink_stream(1)) || !sink_stream(2)) return 41;
    if (sigaction(SIGPIPE, NULL, &pipe_action) != 0 || pipe_action.sa_handler != SIG_DFL) return 42;
    if (sigprocmask(SIG_SETMASK, NULL, &mask) != 0 || sigismember(&mask, SIGUSR2)) return 43;
    for (int number = first_closed; number < 64; ++number) if (fcntl(number, F_GETFD) != -1) return 44;
    return 0;
}

/* Exactly one frame, then EOF; the fd is the child's own and not close-on-exec. */
static bool nested_frame_received(void) {
    owner_nested_bootstrap frame;
    size_t received = 0;
    if (fcntl(NO_BOOTSTRAP_FD, F_GETFD) != 0) return false;
    while (received < sizeof(frame)) {
        ssize_t count = read(NO_BOOTSTRAP_FD, (char *)&frame + received, sizeof(frame) - received);
        if (count <= 0) return false;
        received += (size_t)count;
    }
    char extra;
    if (read(NO_BOOTSTRAP_FD, &extra, 1) != 0) return false;
    if (frame.magic != NO_BOOTSTRAP_MAGIC || frame.version != NO_BOOTSTRAP_VERSION || frame.parent.record.low == 0)
        return false;
    for (size_t i = 0; i < NO_CAPABILITY_BYTES; ++i) if (frame.capability[i] != (uint8_t)(7 * i + 1)) return false;
    return true;
}

/* Relayed application traffic: every line read on fd 0 comes back on fd 1;
 * "exit" answers "bye" and ends the helper. Both descriptors block. */
static int echo_lines(void) {
    if (fcntl(0, F_GETFL) & O_NONBLOCK || fcntl(1, F_GETFL) & O_NONBLOCK) return 46;
    char line[256];
    size_t length = 0;
    for (;;) {
        ssize_t count = read(0, line + length, 1);
        if (count <= 0) return count == 0 ? 38 : 47;
        if (line[length] != '\n' && ++length < sizeof(line) - 1) continue;
        if (line[length] != '\n') return 48;
        bool last = length == 4 && !memcmp(line, "exit", 4);
        const char *answer = last ? "bye\n" : line;
        size_t size = last ? 4 : length + 1;
        if (write(1, answer, size) != (ssize_t)size) return 49;
        if (last) return 37;
        length = 0;
    }
}

/* The JSON-lines helper protocol, minimally: answer {"id": ..., "result": "pong"},
 * stay silent for "hang", and exit 37 for "exit". Lines come from Python's json.dumps. */
/* A descendant that does everything a process can to leave its helper: a new
 * session, a second fork, no descriptors, SIGTERM and SIGHUP ignored. Only the cgroup
 * still holds it. Returns its PID to the caller, or -1. */
static pid_t escape_descendant(void) {
    int report[2];
    if (pipe(report) != 0) return -1;
    pid_t child = fork();
    if (child == 0) {
        if (setsid() < 0) _exit(1);
        pid_t grandchild = fork();
        if (grandchild == 0) {
            signal(SIGTERM, SIG_IGN);
            signal(SIGHUP, SIG_IGN);
            pid_t self = getpid();
            if (write(report[1], &self, sizeof(self)) != sizeof(self)) _exit(1);
            syscall(SYS_close_range, 0U, ~0U, 0);
            for (;;) pause();
        }
        _exit(grandchild > 0 ? 0 : 1);
    }
    close(report[1]);
    pid_t escaped = -1;
    if (child < 0 || read(report[0], &escaped, sizeof(escaped)) != sizeof(escaped)) escaped = -1;
    close(report[0]);
    if (child > 0) waitpid(child, NULL, 0);
    return escaped;
}

/* Forks up to 64 idle children, counts how many the kernel allowed, then reaps them. */
static int spawn_children(void) {
    pid_t children[64];
    int count = 0;
    for (; count < 64; ++count) {
        pid_t child = fork();
        if (child == 0) { pause(); _exit(0); }
        if (child < 0) break;
        children[count] = child;
    }
    for (int i = 0; i < count; ++i) { kill(children[i], SIGKILL); waitpid(children[i], NULL, 0); }
    return count;
}

static int rpc_lines(void) {
    char line[4096];
    size_t length = 0;
    for (;;) {
        ssize_t count = read(0, line + length, 1);
        if (count <= 0) return count == 0 ? 38 : 47;
        if (line[length] != '\n' && ++length < sizeof(line) - 1) continue;
        line[length] = 0;
        length = 0;
        const char *id = strstr(line, "\"id\": \"");
        if (!id) continue;
        id += 7;
        const char *end = strchr(id, '"');
        if (!end || end - id > 64) return 50;
        if (strstr(line, "\"operation\": \"exit\"")) return 37;
        if (strstr(line, "\"operation\": \"hang\"")) continue;
        char reply[128], result[32] = "\"pong\"";
        if (strstr(line, "\"operation\": \"escape\"")) snprintf(result, sizeof(result), "%d", (int)escape_descendant());
        if (strstr(line, "\"operation\": \"spawn\"")) snprintf(result, sizeof(result), "%d", spawn_children());
        int size = snprintf(reply, sizeof(reply), "{\"id\": \"%.*s\", \"result\": %s}\n", (int)(end - id), id, result);
        if (size <= 0 || write(1, reply, (size_t)size) != size) return 49;
    }
}

static int owned_child(const char *mode) {
    if (fcntl(0, F_GETFD) == -1) return 40;
    bool bootstrap = !strcmp(mode, "bootstrap"), relayed = !strcmp(mode, "echo") || !strcmp(mode, "rpc");
    int violation = child_policy_violation(bootstrap ? NO_BOOTSTRAP_FD + 1 : NO_BOOTSTRAP_FD, relayed);
    if (violation) return violation;
    if (bootstrap) return nested_frame_received() ? 37 : 45;
    if (relayed) return strcmp(mode, "rpc") ? echo_lines() : rpc_lines();
    if (!strcmp(mode, "exit")) return 37;
    struct pollfd lifetime = {.fd = 0, .events = POLLIN};
    int result = poll(&lifetime, 1, 10000);
    return result > 0 ? 37 : 39;
}

int main(int argc, char **argv) {
    if (argc == 3 && !strcmp(argv[1], "--owned-child")) return owned_child(argv[2]);
    if (argc != 2) return 64;
    if (!strcmp(argv[1], "--suite=contained")) {
        puts("{\"suite\":\"contained\",\"status\":\"unavailable\",\"reason\":\"authenticated_protected_fixture_not_provisioned\",\"production_verified\":false}");
        return 77;
    }
    signal(SIGPIPE, SIG_IGN);
    sigset_t blocked;
    sigemptyset(&blocked); sigaddset(&blocked, SIGUSR2);
    if (sigprocmask(SIG_BLOCK, &blocked, NULL) != 0) return 66;
    bool cancellation_only = !strcmp(argv[1], "--suite=cancel");
    if (!cancellation_only && strcmp(argv[1], "--suite=lifecycle")) return 64;
    char path[4096]; ssize_t length = readlink("/proc/self/exe", path, sizeof(path) - 1);
    if (length < 0) return 65;
    path[length] = 0;
    if (cancellation_only) {
        simple_case("late_completion_revoke", path, FIXTURE_HOLD_AFTER | FIXTURE_CHILD_HOLD, false, true);
    } else {
    allocation_cases();
    simple_case("normal_exit", path, 0, false, false);
    simple_case("nested_bootstrap_delivery", path, FIXTURE_NESTED_BOOTSTRAP, false, false);
    relay_case(path);
    simple_case("nested_bootstrap_prelaunch_revoke", path, FIXTURE_NESTED_BOOTSTRAP | FIXTURE_HOLD_BEFORE, false, true);
    simple_case("autoreap", path, 0, true, false);
    simple_case("exec_failure", "/does-not-exist-owned-fixture", 0, false, false);
    simple_case("prelaunch_revoke", path, FIXTURE_HOLD_BEFORE, false, true);
    simple_case("late_completion_revoke", path, FIXTURE_HOLD_AFTER | FIXTURE_CHILD_HOLD, false, true);
    simple_case("pthread_failure", path, FIXTURE_FAIL_THREAD, false, false);
    simple_case("child_setup_error_identity", path, FIXTURE_FAIL_CHILD_SETUP, false, false);
    closed_stdin_case(path);
    independent_case(path);
    start_publication_case(path);
    failed_create_observer_case(path);
    adoption_after_revoke_case(path);
    retry_case(path);
    revoke_before_submit_case(path);
    failed_scratch_case(path);
    concurrent_maintenance_case(path);
    sticky_case(path);
    }
    printf("{\"summary\":\"%s\",\"failures\":%d,\"production_verified\":false,"
        "\"contained_suite\":\"not_implemented_requires_protected_fixture\"}\n", failed ? "fail" : "pass", failed);
    return failed ? 1 : 0;
}
