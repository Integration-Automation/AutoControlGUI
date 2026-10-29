#define _GNU_SOURCE
#include "owner_internal.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/sched.h>
#include <linux/capability.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <string.h>
#include <poll.h>
#include <signal.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <stdio.h>
#include <unistd.h>

static void own(owner_record *record, owned_fd *slot, int number) {
    slot->number = number;
    slot->state = FD_OWNED;
    atomic_fetch_add(&record->owned_count, 1);
}

static int make_pipe(owner_record *record, owned_fd *read_end, owned_fd *write_end) {
    int pair[2];
    if (pipe2(pair, O_CLOEXEC | O_NONBLOCK) == -1) return errno;
    own(record, read_end, pair[0]); own(record, write_end, pair[1]);
    return 0;
}

/* exec keeps ignored dispositions and the mask; the child gets neither. Raw
 * kernel sigaction: an all-zero action is SIG_DFL with no flags and no mask. */
static int child_reset_signals(void) {
    unsigned long action[4] = {0, 0, 0, 0};
    for (int number = 1; number <= 64; ++number) {
        if (number == SIGKILL || number == SIGSTOP) continue;
        if (syscall(SYS_rt_sigaction, number, action, NULL, sizeof(uint64_t)) == -1 && errno != EINVAL)
            return errno;
    }
    uint64_t empty = 0;
    return syscall(SYS_rt_sigprocmask, SIG_SETMASK, &empty, NULL, sizeof(empty)) == -1 ? errno : 0;
}

/* Standard streams: 0 is the lifetime pipe (also the relayed request stream), 1 the
 * relayed reply pipe or the sink, 2 the sink, 3 the exec-error
 * pipe, and 4 the nested bootstrap pipe only for a nested-capable record;
 * everything above is closed, so no listener, guardian channel, cgroup or other
 * record descriptor reaches the payload whatever number it holds. Sources move
 * above 4 first, so no target dup2 can overwrite a source not yet placed. */
static int child_descriptors(owner_record *record, int *error_fd) {
    bool bootstrap = record->bootstrap_read.state == FD_OWNED;
    long lifetime = syscall(SYS_fcntl, record->lifetime_read.number, F_DUPFD_CLOEXEC, 5);
    long failure = syscall(SYS_fcntl, *error_fd, F_DUPFD_CLOEXEC, 5);
    long sink = syscall(SYS_fcntl, record->output_sink.number, F_DUPFD_CLOEXEC, 5);
    long nested = bootstrap ? syscall(SYS_fcntl, record->bootstrap_read.number, F_DUPFD_CLOEXEC, 5) : 0;
    long output = record->relay_enabled ? syscall(SYS_fcntl, record->reply_write.number, F_DUPFD_CLOEXEC, 5) : sink;
    if (lifetime < 0 || failure < 0 || sink < 0 || nested < 0 || output < 0) return errno;
    if (syscall(SYS_dup2, failure, 3) == -1) return errno;
    *error_fd = 3;
    if (syscall(SYS_fcntl, 3, F_SETFD, FD_CLOEXEC) == -1) return errno;
    if (syscall(SYS_dup2, lifetime, 0) == -1 || syscall(SYS_dup2, output, 1) == -1 ||
        syscall(SYS_dup2, sink, 2) == -1) return errno;
    if (bootstrap && syscall(SYS_dup2, nested, NO_BOOTSTRAP_FD) == -1) return errno;
    if (syscall(SYS_close_range, bootstrap ? NO_BOOTSTRAP_FD + 1U : NO_BOOTSTRAP_FD, ~0U, 0) == -1) return errno;
    return 0;
}

/* Bounding set first, while the service may still hold CAP_SETPCAP; a set it
 * cannot drop fails startup. Then ambient, IDs, the remaining capabilities. */
static int child_protected_credentials(owner_record *record) {
    struct __user_cap_header_struct header = {_LINUX_CAPABILITY_VERSION_3, 0};
    struct __user_cap_data_struct capabilities[2] = {{0}, {0}};
    /* No supplementary group: a nested-capable payload reaches the guardian through the
     * listener's ACL, and the identity filter allows only an empty list anyway. */
    if (syscall(SYS_setgroups, 0, NULL) == -1) return errno;
    for (unsigned long capability = 0;; ++capability) {
        long present = syscall(SYS_prctl, PR_CAPBSET_READ, capability, 0, 0, 0);
        if (present < 0) { if (errno == EINVAL) break; return errno; }
        if (present && syscall(SYS_prctl, PR_CAPBSET_DROP, capability, 0, 0, 0) == -1) return errno;
    }
    if (syscall(SYS_prctl, PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) == -1 ||
        syscall(SYS_setresgid, record->spec->gid, record->spec->gid, record->spec->gid) == -1 ||
        syscall(SYS_setresuid, record->spec->uid, record->spec->uid, record->spec->uid) == -1 ||
        syscall(SYS_capset, &header, capabilities) == -1 ||
        syscall(SYS_prctl, PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == -1 ||
        syscall(SYS_chdir, record->spec->cwd) == -1) return errno;
    return 0;
}

/* The child's end blocks, so a helper simply reads until the frame or EOF; the
 * worker's end never blocks, and one frame is far below PIPE_BUF. */
static int make_bootstrap_pipe(owner_record *record) {
    int pair[2];
    if (pipe2(pair, O_CLOEXEC) == -1) return errno;
    own(record, &record->bootstrap_read, pair[0]); own(record, &record->bootstrap_write, pair[1]);
    return fcntl(pair[1], F_SETFL, O_NONBLOCK) == -1 ? errno : 0;
}

/* Once, to this record's own child only, after its payload identity is
 * published. Anything else closes the pipe empty: the helper reads EOF and cannot
 * nest. The delivery copy is wiped either way. */
static void deliver_nested(owner_record *record, bool published) {
    if (record->bootstrap_write.state == FD_OWNED && published) {
        owner_nested_bootstrap frame = {NO_BOOTSTRAP_MAGIC, NO_BOOTSTRAP_VERSION, record->ticket, {0}};
        memcpy(frame.capability, record->delivery.capability, NO_CAPABILITY_BYTES);
        ssize_t written;
        do { written = write(record->bootstrap_write.number, &frame, sizeof(frame)); }
        while (written < 0 && errno == EINTR);
        atomic_store(&record->nested_delivered, written == (ssize_t)sizeof(frame));
        explicit_bzero(&frame, sizeof(frame));
    }
    explicit_bzero(record->delivery.capability, NO_CAPABILITY_BYTES);
    owner_close_slot(record, &record->bootstrap_write);
}

/* The child's ends block, so an ordinary helper reads stdin and writes stdout as
 * usual; the worker's ends stay non-blocking. */
static int make_relay_pipes(owner_record *record) {
    int error = make_pipe(record, &record->reply_read, &record->reply_write);
    if (!error && (fcntl(record->lifetime_read.number, F_SETFL, 0) == -1 ||
                   fcntl(record->reply_write.number, F_SETFL, 0) == -1)) error = errno;
    return error;
}

/* A protected child runs nothing of its own until the parent has moved it into its
 * payload cgroup and released it; EOF instead of the release byte means stop. */
static int child_await_release(owner_record *record) {
    char byte;
    long count;
    do { count = syscall(SYS_read, record->release_read.number, &byte, 1); } while (count < 0 && errno == EINTR);
    return count == 1 ? 0 : ECANCELED;
}

static void child_exec(owner_record *record) {
    int error = record->options.fail_child_setup ? EBADF : 0;
    if (!error && record->profile == PROFILE_PROTECTED) error = child_await_release(record);
    int error_fd = record->exec_write.number;
    if (!error) error = child_descriptors(record, &error_fd);
    if (!error) error = child_reset_signals();
    if (!error && syscall(SYS_setsid) == -1) error = errno;
    if (!error && record->profile == PROFILE_PROTECTED) {
        error = child_protected_credentials(record);
        if (!error) {
            syscall(SYS_execve, record->spec->executable, record->spec->argv, record->spec->env);
            error = errno;
        }
    }
    if (!error) {
        const char *mode = record->options.child_hold ? "hold" : record->options.rpc ? "rpc" :
            record->relay_enabled ? "echo" :
            record->delivery.wanted ? "bootstrap" : "exit";
        char *argv[] = {record->executable, "--owned-child", (char *)mode, NULL};
        char *env[] = {NULL};
        syscall(SYS_execve, record->executable, argv, env);
        error = errno;
    }
    syscall(SYS_write, error_fd, &error, sizeof(error));
    syscall(SYS_exit, 127);
    __builtin_unreachable();
}

static void fixture_hold(atomic_bool *released) {
    uint64_t deadline = owner_now() + 5000000000ULL;
    while (!atomic_load(released) && owner_now() < deadline) owner_pause();
}

static void set_start(owner_record *record, no_start_kind kind, int error) {
    pthread_mutex_lock(&record->report_lock);
    record->report.start = (no_start_outcome){kind,
        {error ? NO_ERROR_NATIVE_CONTRACT : NO_ERROR_NONE, error, 0}};
    pthread_mutex_unlock(&record->report_lock);
}

/* The identity filter answers clone3 with ENOSYS, so a protected child is created with
 * clone and then moved: a blocking pipe holds it until it sits in its payload cgroup. */
static int make_release_pipe(owner_record *record) {
    int pair[2];
    if (pipe2(pair, O_CLOEXEC) == -1) return errno;
    own(record, &record->release_read, pair[0]);
    own(record, &record->release_write, pair[1]);
    return 0;
}

static int move_into_payload(owner_record *record, pid_t child) {
    int procs;
    do {
        procs = openat(record->scope.payload.descriptor.number, "cgroup.procs", O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
    } while (procs < 0 && errno == EINTR);
    if (procs < 0) return errno;
    char text[24];
    int length = snprintf(text, sizeof(text), "%d", (int)child);
    int error = write(procs, text, (size_t)length) == length ? 0 : errno;
    close(procs);
    return error;
}

/* Moves, then checks revocation, then releases: a revoke before the check is seen here,
 * and one after it finds the child already inside the container its kill covers. */
static void release_protected(owner_record *record, pid_t child) {
    owner_close_slot(record, &record->release_read);
    int error = move_into_payload(record, child);
    if (!error && atomic_load(&record->revoked)) error = ECANCELED;
    if (!error && write(record->release_write.number, "g", 1) != 1) error = errno;
    if (error) owner_set_error(record, NO_ERROR_NATIVE_CONTRACT, error);
    owner_close_slot(record, &record->release_write); /* Unreleased, the child reads EOF and stops. */
}

static long clone_child(owner_record *record, int *pidfd) {
    if (record->profile == PROFILE_PROTECTED && !record->options.admission_probe)
        return syscall(SYS_clone, CLONE_PIDFD | SIGCHLD, 0, pidfd, 0, 0);
    struct clone_args args = {.flags = CLONE_PIDFD, .pidfd = (uintptr_t)pidfd, .exit_signal = SIGCHLD};
    if (record->options.admission_probe) {
        args.flags |= CLONE_INTO_CGROUP;
        args.cgroup = (uint64_t)record->cgroup_probe.number;
    }
    return syscall(SYS_clone3, &args, sizeof(args));
}

int owner_launch(owner_record *record) {
    int error = make_pipe(record, &record->lifetime_read, &record->lifetime_write);
    if (!error) error = make_pipe(record, &record->exec_read, &record->exec_write);
    if (!error && record->delivery.wanted) error = make_bootstrap_pipe(record);
    if (!error && record->relay_enabled) error = make_relay_pipes(record);
    if (!error && record->profile == PROFILE_PROTECTED) error = make_release_pipe(record);
    if (!error) {
        int sink = open("/dev/null", O_WRONLY | O_CLOEXEC);
        if (sink == -1) error = errno;
        else own(record, &record->output_sink, sink);
    }
    if (!error && record->options.admission_probe) {
        int fd = open("/sys/fs/cgroup", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (fd == -1) error = errno;
        else own(record, &record->cgroup_probe, fd);
    }
    if (error) { set_start(record, NO_START_FAILED_WITHOUT_CHILD, error); return error; }
    atomic_store(&record->before_call, true);
    fixture_hold(&record->release_before);
    if (atomic_load(&record->revoked)) { set_start(record, NO_START_FAILED_WITHOUT_CHILD, ECANCELED); return ECANCELED; }
    struct { int output; } scratch = {.output = -1};
    atomic_fetch_add(&record->launch_attempts, 1);
    long result = clone_child(record, &scratch.output);
    error = result < 0 ? errno : 0;
    if (result == 0) child_exec(record);
    if (result > 0 && record->release_write.state == FD_OWNED) release_protected(record, (pid_t)result);
    if (result < 0) {
        owner_close_slot(record, &record->release_read);
        owner_close_slot(record, &record->release_write);
        atomic_store(&record->scratch_diagnostic, scratch.output);
        atomic_store(&record->failed_call, true);
        fixture_hold(&record->release_failure);
        set_start(record, NO_START_FAILED_WITHOUT_CHILD, error);
        return error;
    }
    /* A failed clone keeps the sink until worker cleanup, after the scratch hold. */
    owner_close_slot(record, &record->output_sink);
#ifdef NO_ACCEPTANCE_BUILD
    atomic_store(&record->native_success, true);
    if (record->options.hold_adoption) fixture_hold(&record->release_adoption);
#endif
    own(record, &record->pidfd, scratch.output);
    atomic_store(&record->pidfd_adopted, true);
    atomic_store(&record->after_success, true);
    fixture_hold(&record->release_after);
    owner_close_slot(record, &record->lifetime_read);
    owner_close_slot(record, &record->bootstrap_read);
    owner_close_slot(record, &record->reply_write);
    owner_close_slot(record, &record->exec_write);
    set_start(record, NO_START_CHILD_CREATED, 0);
    return 0;
}

#ifdef NO_ACCEPTANCE_BUILD
static ssize_t (*io_read_override)(int, void *, size_t);
static int (*io_wait_override)(idtype_t, id_t, siginfo_t *, int);
static ssize_t (*control_write_override)(int, const void *, size_t, off_t);
static ssize_t (*control_read_override)(int, void *, size_t, off_t);
#endif

static ssize_t exec_read(int fd, void *buffer, size_t size) {
#ifdef NO_ACCEPTANCE_BUILD
    if (io_read_override) return io_read_override(fd, buffer, size);
#endif
    return read(fd, buffer, size);
}

static int child_wait(idtype_t type, id_t id, siginfo_t *status, int options) {
#ifdef NO_ACCEPTANCE_BUILD
    if (io_wait_override) return io_wait_override(type, id, status, options);
#endif
    return waitid(type, id, status, options);
}

static void read_exec_error(owner_record *record) {
    int error = 0;
    size_t received = 0;
    for (;;) {
        ssize_t count = exec_read(record->exec_read.number, (char *)&error + received, sizeof(error) - received);
        if (count < 0) {
            if (errno == EINTR || errno == EAGAIN) { owner_pause(); continue; }
            owner_set_error(record, NO_ERROR_NATIVE_CONTRACT, errno);
            return;
        }
        if (count == 0) {
            if (received) owner_set_error(record, NO_ERROR_NATIVE_CONTRACT, EPROTO);
            return;
        }
        received += (size_t)count;
        if (received == sizeof(error)) {
            if (error <= 0) owner_set_error(record, NO_ERROR_NATIVE_CONTRACT, EPROTO);
            else set_start(record, NO_START_EXEC_FAILED, error);
            return;
        }
    }
}

static void observe_status(owner_record *record) {
    for (;;) {
        siginfo_t status = {0};
        int rc = child_wait(P_PIDFD, (id_t)record->pidfd.number, &status, WEXITED | WNOHANG);
        if (rc == -1 && errno == EINTR) { owner_pause(); continue; }
        if (rc == -1 && errno == ECHILD) {
            record->proof.wait = (no_wait_status){NO_WAIT_STATUS_UNAVAILABLE, 0};
            return;
        }
        if (rc == 0 && status.si_code == 0) { owner_pause(); continue; }
        if (rc == 0 && status.si_code == CLD_EXITED)
            record->proof.wait = (no_wait_status){NO_WAIT_EXITED, status.si_status};
        else if (rc == 0 && (status.si_code == CLD_KILLED || status.si_code == CLD_DUMPED))
            record->proof.wait = (no_wait_status){NO_WAIT_SIGNALLED, status.si_status};
        else owner_set_error(record, NO_ERROR_NATIVE_CONTRACT, rc ? errno : EPROTO);
        return;
    }
}

void owner_retire_child(owner_record *record) {
    uint64_t expiry = owner_now() + 4000000000ULL;
    bool signalled = false;
    while (!record->proof.child_dead) {
        owner_relay_pump(record);
        bool stop = atomic_load(&record->revoked) || owner_now() >= expiry;
        if (stop && !signalled) {
            int rc = syscall(SYS_pidfd_send_signal, record->pidfd.number, SIGKILL, NULL, 0);
            if (rc == 0 || errno == ESRCH) signalled = true;
            else owner_set_error(record, NO_ERROR_CLEANUP, errno);
        }
        struct pollfd event = {.fd = record->pidfd.number, .events = POLLIN};
        int rc = poll(&event, 1, 10);
        if (rc > 0 && (event.revents & POLLIN)) record->proof.child_dead = true;
        else if (rc < 0 && errno != EINTR) owner_set_error(record, NO_ERROR_CLEANUP, errno);
        if (!record->proof.child_dead) continue;
        owner_relay_drain(record);
        read_exec_error(record);
        observe_status(record);
    }
}

void *owner_worker(void *raw) {
    owner_record *record = raw;
    pthread_setcancelstate(PTHREAD_CANCEL_DISABLE, NULL);
    int error = owner_launch(record);
    if (error) {
        record->proof.no_child = true;
        record->proof.wait.kind = NO_WAIT_NOT_APPLICABLE;
    } else {
        deliver_nested(record, true); /* Fixture records have no payload to publish. */
        owner_publish(record, NO_PENDING_CHILD, NO_CHILD_LIVE);
        owner_retire_child(record);
    }
    owner_close_slot(record, &record->lifetime_read);
    owner_close_slot(record, &record->lifetime_write);
    owner_close_slot(record, &record->exec_write);
    owner_close_slot(record, &record->exec_read);
    owner_close_slot(record, &record->pidfd);
    owner_close_slot(record, &record->output_sink);
    owner_close_slot(record, &record->bootstrap_read);
    deliver_nested(record, false);
    owner_relay_close(record);
    owner_close_slot(record, &record->reply_read);
    owner_close_slot(record, &record->reply_write);
    owner_close_slot(record, &record->cgroup_probe);
    record->proof.kind = PROOF_DIRECT_FIXTURE;
    record->proof.io_settled = atomic_load(&record->owned_count) == 0;
    owner_publish(record, NO_PENDING_JOIN, record->proof.no_child ? NO_CHILD_NEVER_CREATED : NO_CHILD_DEAD);
    atomic_store_explicit(&record->finished, true, memory_order_release);
    return NULL;
}

static bool scope_acquire(owner_record *record, int parent, const char *component,
                          int flags, owned_fd *slot) {
    int number;
    do { number = openat(parent, component, flags | O_CLOEXEC | O_NOFOLLOW); } while (number < 0 && errno == EINTR);
    if (number < 0) return false;
    own(record, slot, number);
    return true;
}

static int scope_create_directory(owner_record *record, int parent, owned_directory *directory) {
    if (atomic_load(&record->revoked)) return ECANCELED;
    int rc;
    do { rc = mkdirat(parent, directory->component, 0700); } while (rc < 0 && errno == EINTR);
    if (rc < 0) return errno;
    directory->state = DIR_CREATED_UNOPENED;
    if (!scope_acquire(record, parent, directory->component, O_RDONLY | O_DIRECTORY, &directory->descriptor))
        return errno;
    directory->state = DIR_OPENED;
    return 0;
}

static bool scope_write(int directory, const char *name, const char *value) {
    int number;
    do { number = openat(directory, name, O_WRONLY | O_NOFOLLOW | O_CLOEXEC); } while (number < 0 && errno == EINTR);
    if (number < 0) return false;
    size_t length = strlen(value);
    bool written = write(number, value, length) == (ssize_t)length;
    int saved = errno;
    close(number);
    errno = saved;
    return written;
}

/* Limits sit on the container, which only this service can write, so they bound the
 * payload and every nested child inside it. Swap is closed where the host accounts it. */
static int scope_limit(owner_record *record) {
    const immutable_spec_arena *spec = record->spec;
    int container = record->scope.container.descriptor.number;
    char value[24];
    if (spec->pids_max) {
        snprintf(value, sizeof(value), "%llu", (unsigned long long)spec->pids_max);
        if (!scope_write(container, "pids.max", value)) return errno;
    }
    if (spec->memory_max) {
        snprintf(value, sizeof(value), "%llu", (unsigned long long)spec->memory_max);
        if (!scope_write(container, "memory.max", value)) return errno;
        if (!scope_write(container, "memory.swap.max", "0") && errno != ENOENT) return errno;
    }
    if ((spec->pids_max || spec->memory_max) && !scope_write(container, "cgroup.subtree_control", "+pids +memory"))
        return errno;
    return 0;
}

static int scope_prepare(owner_record *record) {
    no_runtime *runtime = record->runtime;
    pthread_mutex_lock(&runtime->registry);
    int borrowed = -1;
    if (record->parent_is_epoch) {
        owned_fd *anchor = &record->retained_scope.slot->epoch_anchor;
        if (anchor->state == FD_OWNED) borrowed = anchor->number;
    } else {
        owner_record *parent = &runtime->records[record->parent_slot];
        uint32_t bit;
        if (owner_child_bit((size_t)(record - runtime->records), &bit) &&
            (parent->unsettled_children & bit) && parent->anchor.state == ANCHOR_READY)
            borrowed = parent->anchor.borrowed_directory;
    }
    pthread_mutex_unlock(&runtime->registry);
    if (borrowed < 0) return EBADF;
    int number;
    do { number = fcntl(borrowed, F_DUPFD_CLOEXEC, 4); } while (number < 0 && errno == EINTR);
    if (number < 0) return errno;
    own(record, &record->scope.parent_anchor, number);
    int error = scope_create_directory(record, number, &record->scope.container);
    if (error) return error;
    error = scope_limit(record);
    if (error) return error;
    pthread_mutex_lock(&runtime->registry);
    owner_publish_anchor_locked(record);
    pthread_mutex_unlock(&runtime->registry);
    error = scope_create_directory(record, record->scope.container.descriptor.number, &record->scope.payload);
    if (error) return error;
    if (atomic_load(&record->revoked)) return ECANCELED;
    if (!scope_acquire(record, record->scope.container.descriptor.number, "cgroup.events", O_RDONLY,
                       &record->scope.events)) return errno;
    if (atomic_load(&record->revoked)) return ECANCELED;
    if (!scope_acquire(record, record->scope.container.descriptor.number, "cgroup.kill", O_WRONLY,
                       &record->scope.kill)) return errno;
    return 0;
}

typedef enum { OBSERVE_POPULATED, OBSERVE_EMPTY, OBSERVE_RETRY, OBSERVE_INVALID } population_result;

static population_result scope_population(owner_record *record) {
    char buffer[256];
    ssize_t count;
#ifdef NO_ACCEPTANCE_BUILD
    if (control_read_override)
        count = control_read_override(record->scope.events.number, buffer, sizeof(buffer) - 1, 0);
    else
#endif
        count = pread(record->scope.events.number, buffer, sizeof(buffer) - 1, 0);
    if (count < 0) return errno == EBADF ? OBSERVE_INVALID : OBSERVE_RETRY;
    if (count == 0 || count == (ssize_t)sizeof(buffer) - 1) return OBSERVE_INVALID;
    buffer[count] = 0;
    char *line = buffer;
    while (*line) {
        char *end = strchr(line, '\n');
        if (!end) return OBSERVE_INVALID;
        *end = 0;
        if (!strcmp(line, "populated 0")) return OBSERVE_EMPTY;
        if (!strcmp(line, "populated 1")) return OBSERVE_POPULATED;
        line = end + 1;
    }
    return OBSERVE_INVALID;
}

static bool scope_recover_observation(owner_record *record) {
    worker_scope *scope = &record->scope;
    while (scope->container.state == DIR_CREATED_UNOPENED) {
        if (scope_acquire(record, scope->parent_anchor.number, scope->container.component,
                          O_RDONLY | O_DIRECTORY, &scope->container.descriptor)) {
            scope->container.state = DIR_OPENED;
            break;
        }
        if (errno == ENOENT || errno == ENOTDIR || errno == ELOOP || errno == EBADF) {
            scope->container.state = DIR_IDENTITY_UNCERTAIN;
            owner_set_error(record, NO_ERROR_CLEANUP, errno);
            return false;
        }
        owner_pause();
    }
    while (scope->events.state == FD_EMPTY) {
        if (scope_acquire(record, scope->container.descriptor.number, "cgroup.events", O_RDONLY, &scope->events)) break;
        if (errno == EBADF || errno == ENOENT || errno == ELOOP) {
            scope->container.state = DIR_IDENTITY_UNCERTAIN;
            owner_set_error(record, NO_ERROR_CLEANUP, errno);
            return false;
        }
        owner_pause();
    }
    return true;
}

static bool scope_remove(owner_record *record, int parent, owned_directory *directory) {
    if (directory->state == DIR_PLANNED || directory->state == DIR_REMOVED) return true;
    if (directory->state == DIR_IDENTITY_UNCERTAIN) return false;
    for (;;) {
        if (unlinkat(parent, directory->component, AT_REMOVEDIR) == 0) {
            directory->state = DIR_REMOVED;
            return true;
        }
        int error = errno;
        if (error == ENOENT || error == ENOTDIR || error == ELOOP || error == EBADF) {
            directory->state = DIR_IDENTITY_UNCERTAIN;
            owner_set_error(record, NO_ERROR_CLEANUP, error);
            return false;
        }
        owner_pause();
    }
}

typedef enum { KILL_NOT_REQUIRED, KILL_COMPLETED, KILL_RETRY_PENDING, KILL_AUTHORITY_INVALID } kill_result;

static kill_result scope_kill(owner_record *record) {
    if (record->scope.kill.state == FD_EMPTY) return KILL_NOT_REQUIRED;
    if (record->scope.kill.state != FD_OWNED) {
        owner_set_error(record, NO_ERROR_NATIVE_CONTRACT, EBADF);
        return KILL_AUTHORITY_INVALID;
    }
    ssize_t count;
#ifdef NO_ACCEPTANCE_BUILD
    if (control_write_override)
        count = control_write_override(record->scope.kill.number, "1", 1, 0);
    else
#endif
        count = pwrite(record->scope.kill.number, "1", 1, 0);
    if (count == 1) return KILL_COMPLETED;
    if (count >= 0 || errno == EBADF || errno == EOPNOTSUPP) {
        owner_set_error(record, NO_ERROR_NATIVE_CONTRACT, count < 0 ? errno : EIO);
        return KILL_AUTHORITY_INVALID;
    }
    return KILL_RETRY_PENDING;
}

static namespace_result namespace_evidence(directory_state state) {
    if (state == DIR_PLANNED) return CLEAN_NEVER_CREATED;
    if (state == DIR_REMOVED) return CLEAN_EXACT_REMOVAL;
    return CLEAN_UNRESOLVED;
}

static void scope_retire(owner_record *record) {
    worker_scope *scope = &record->scope;
    pthread_mutex_lock(&record->runtime->registry);
    owner_fence_locked(record);
    pthread_mutex_unlock(&record->runtime->registry);
    bool observation = scope->container.state != DIR_PLANNED && scope_recover_observation(record);
    for (;;) {
        kill_result kill = scope_kill(record);
        pthread_mutex_lock(&record->runtime->registry);
        bool children_settled = record->unsettled_children == 0;
        pthread_mutex_unlock(&record->runtime->registry);
        if (!children_settled) { owner_pause(); continue; }
        if (observation) {
            population_result population = scope_population(record);
            if (population == OBSERVE_RETRY || population == OBSERVE_POPULATED) { owner_pause(); continue; }
            if (population == OBSERVE_INVALID) {
                owner_set_error(record, NO_ERROR_NATIVE_CONTRACT, EPROTO);
                scope->container.state = DIR_IDENTITY_UNCERTAIN;
                observation = false;
            }
        }
        if (kill == KILL_RETRY_PENDING) { owner_pause(); continue; }
        break;
    }
    if (observation) {
        record->proof.detail.contained.emptiness = EMPTY_POPULATION_OBSERVED;
        bool payload_removed = scope_remove(record, scope->container.descriptor.number, &scope->payload);
        if (payload_removed) scope_remove(record, scope->parent_anchor.number, &scope->container);
    }
    pthread_mutex_lock(&record->runtime->registry);
    bool invalidated = owner_invalidate_anchor_locked(record);
    pthread_mutex_unlock(&record->runtime->registry);
    if (!invalidated) __builtin_trap();
    owner_close_slot(record, &scope->payload.descriptor);
    owner_close_slot(record, &scope->events);
    owner_close_slot(record, &scope->kill);
    owner_close_slot(record, &scope->container.descriptor);
    owner_close_slot(record, &scope->parent_anchor);
}

static void worker_build_finished_evidence(owner_record *record) {
    record->proof.io_settled = atomic_load(&record->owned_count) == 0;
    pthread_mutex_lock(&record->runtime->registry);
    bool fenced = record->admission == ADMISSION_FENCED;
    bool children_settled = record->unsettled_children == 0;
    pthread_mutex_unlock(&record->runtime->registry);
    bool ready = fenced && children_settled && record->proof.io_settled &&
        (record->proof.no_child || record->proof.child_dead);
    if (ready && record->proof.no_child && record->scope.container.state == DIR_PLANNED &&
        record->scope.payload.state == DIR_PLANNED && !record->proof.error.kind) {
        record->proof.kind = PROOF_WITHOUT_SCOPE;
        record->proof.detail.without_scope.execution = WORKER_JOIN_REQUIRED;
    } else {
        empty_evidence_kind emptiness = record->proof.detail.contained.emptiness;
        record->proof.detail.contained = (contained_evidence){
            .container = namespace_evidence(record->scope.container.state),
            .payload = namespace_evidence(record->scope.payload.state), .emptiness = emptiness,
            .protected_tree = record->planned_protected_tree, .admission_fenced = fenced,
            .children_settled = children_settled, .launch_resolved = ready,
            .descriptors_clean = record->proof.io_settled && !record->proof.error.kind};
        record->proof.kind = ready && !record->proof.error.kind &&
            record->scope.container.state == DIR_REMOVED && emptiness == EMPTY_POPULATION_OBSERVED ?
            PROOF_CONTAINED : PROOF_UNRESOLVED;
    }
}

void owner_publish_payload(owner_record *record) {
    struct stat status;
    if (record->scope.payload.descriptor.state != FD_OWNED ||
        fstat(record->scope.payload.descriptor.number, &status) == -1 || !S_ISDIR(status.st_mode)) return;
    pthread_mutex_lock(&record->runtime->registry);
    if (record->admission == ADMISSION_OPEN && !record->published_payload.published)
        record->published_payload = (payload_identity){true, (uint64_t)status.st_dev, (uint64_t)status.st_ino,
            record->spec->uid, record->spec->gid};
    pthread_mutex_unlock(&record->runtime->registry);
}

void *owner_protected_worker(void *raw) {
    owner_record *record = raw;
    pthread_setcancelstate(PTHREAD_CANCEL_DISABLE, NULL);
    int error = scope_prepare(record);
    if (!error) error = owner_launch(record);
    else set_start(record, NO_START_FAILED_WITHOUT_CHILD, error);
    if (error) {
        record->proof.no_child = true;
        record->proof.wait = (no_wait_status){NO_WAIT_NOT_APPLICABLE, 0};
        pthread_mutex_lock(&record->runtime->registry);
        owner_fence_locked(record);
        pthread_mutex_unlock(&record->runtime->registry);
    } else {
        owner_publish_payload(record);
        deliver_nested(record, record->published_payload.published);
        owner_publish(record, NO_PENDING_CHILD, NO_CHILD_LIVE);
        while (!record->proof.child_dead) {
            owner_relay_pump(record);
            if (atomic_load(&record->revoked)) scope_kill(record);
            struct pollfd event = {.fd = record->pidfd.number, .events = POLLIN};
            int rc = poll(&event, 1, 10);
            if (rc > 0 && (event.revents & POLLIN)) {
                record->proof.child_dead = true;
                pthread_mutex_lock(&record->runtime->registry);
                owner_fence_locked(record);
                pthread_mutex_unlock(&record->runtime->registry);
                owner_relay_drain(record);
                read_exec_error(record); observe_status(record);
            }
        }
    }
    owner_close_slot(record, &record->lifetime_read);
    owner_close_slot(record, &record->lifetime_write);
    owner_close_slot(record, &record->exec_write);
    owner_close_slot(record, &record->exec_read);
    owner_close_slot(record, &record->pidfd);
    owner_close_slot(record, &record->output_sink);
    owner_close_slot(record, &record->bootstrap_read);
    deliver_nested(record, false);
    owner_relay_close(record);
    owner_close_slot(record, &record->reply_read);
    owner_close_slot(record, &record->reply_write);
    scope_retire(record);
    worker_build_finished_evidence(record);
    owner_publish(record, NO_PENDING_JOIN, record->proof.no_child ? NO_CHILD_NEVER_CREATED : NO_CHILD_DEAD);
    atomic_store_explicit(&record->finished, true, memory_order_release);
    return NULL;
}

#ifdef NO_ACCEPTANCE_BUILD
static unsigned io_test_step;
static ssize_t interrupted_exec_read(int fd, void *buffer, size_t size) {
    (void)fd;
    int value = EACCES;
    unsigned step = io_test_step++;
    if (step == 0) { errno = EINTR; return -1; }
    if (step == 1) { errno = EAGAIN; return -1; }
    size_t offset = step == 2 ? 0 : 1;
    size_t count = step == 2 ? 1 : sizeof(value) - 1;
    if (count > size) return -1;
    memcpy(buffer, (char *)&value + offset, count);
    return (ssize_t)count;
}

static ssize_t truncated_exec_read(int fd, void *buffer, size_t size) {
    (void)fd; (void)size;
    if (io_test_step++ == 0) { *(char *)buffer = 1; return 1; }
    return 0;
}

static int interrupted_wait(idtype_t type, id_t id, siginfo_t *status, int options) {
    (void)type; (void)id; (void)options;
    unsigned step = io_test_step++;
    if (step == 0) { errno = EINTR; return -1; }
    if (step == 1) return 0;
    status->si_code = CLD_EXITED; status->si_status = 42;
    return 0;
}

static ssize_t transient_kill_write(int fd, const void *buffer, size_t size, off_t offset) {
    (void)buffer; (void)size; (void)offset;
    if (fcntl(fd, F_GETFD) < 0) return 0;
    unsigned step = io_test_step++;
    if (step < 2) { errno = step ? EAGAIN : EINTR; return -1; }
    return 1;
}

static ssize_t invalid_population_read(int fd, void *buffer, size_t size, off_t offset) {
    (void)fd; (void)size; (void)offset;
    memcpy(buffer, "invalid\n", 8);
    return 8;
}

static bool retry_kill_after_invalid_observation(void) {
    owner_record record = {0};
    no_runtime runtime = {.records = &record, .count = 1, .capacity = 1};
    record.runtime = &runtime;
    record.parent_is_epoch = true;
    record.scope.container.state = DIR_OPENED;
    atomic_init(&record.revoked, false);
    atomic_init(&record.owned_count, 0);
    atomic_init(&record.close_attempts, 0);
    if (pthread_mutex_init(&runtime.registry, NULL)) return false;
    owned_fd *slots[] = {&record.scope.kill, &record.scope.events,
        &record.scope.container.descriptor, &record.scope.parent_anchor};
    bool good = true;
    for (size_t i = 0; i < sizeof(slots) / sizeof(slots[0]); ++i) {
        int fd = open("/dev/null", O_RDONLY | O_CLOEXEC);
        if (fd < 0) { good = false; break; }
        own(&record, slots[i], fd);
    }
    if (good) {
        io_test_step = 0;
        control_write_override = transient_kill_write;
        control_read_override = invalid_population_read;
        scope_retire(&record);
        good = io_test_step == 3 && record.proof.error.kind == NO_ERROR_NATIVE_CONTRACT &&
            record.proof.error.system_errno == EPROTO && atomic_load(&record.owned_count) == 0 &&
            record.scope.kill.state == FD_CLOSED && record.scope.container.state == DIR_IDENTITY_UNCERTAIN;
        control_write_override = NULL; control_read_override = NULL;
    }
    for (size_t i = 0; i < sizeof(slots) / sizeof(slots[0]); ++i) owner_close_slot(&record, slots[i]);
    pthread_mutex_destroy(&runtime.registry);
    return good;
}

bool owner_io_contract_cases(void) {
    owner_record record = {0};
    if (pthread_mutex_init(&record.report_lock, NULL)) return false;
    io_test_step = 0; io_read_override = interrupted_exec_read;
    read_exec_error(&record);
    bool good = io_test_step == 4 && record.report.start.kind == NO_START_EXEC_FAILED &&
        record.report.start.failure.system_errno == EACCES && !record.proof.error.kind;
    io_test_step = 0; io_read_override = truncated_exec_read;
    read_exec_error(&record);
    good &= record.proof.error.kind == NO_ERROR_NATIVE_CONTRACT && record.proof.error.system_errno == EPROTO;
    record.proof.error = (no_error){0};
    io_test_step = 0; io_wait_override = interrupted_wait;
    observe_status(&record);
    good &= io_test_step == 3 && record.proof.wait.kind == NO_WAIT_EXITED &&
        record.proof.wait.value == 42 && !record.proof.error.kind;
    io_read_override = NULL; io_wait_override = NULL;
    pthread_mutex_destroy(&record.report_lock);
    return good && retry_kill_after_invalid_observation();
}
#endif
