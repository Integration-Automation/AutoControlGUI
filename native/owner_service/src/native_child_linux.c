#define _GNU_SOURCE
/* What a cloned helper runs before exec: wait to be released into its cgroup, arrange its
 * descriptors, reset signals, start its own session, drop to its payload IDs, then exec.
 * Raw system calls only: the child of a multi-threaded process may call nothing else. */
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
    /* Whatever the helper creates is its own: another helper's ID cannot read it. */
    syscall(SYS_umask, 077);
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

/* A protected child runs nothing of its own until the parent has moved it into its
 * payload cgroup and released it; EOF instead of the release byte means stop. */
static int child_await_release(owner_record *record) {
    char byte;
    long count;
    do { count = syscall(SYS_read, record->release_read.number, &byte, 1); } while (count < 0 && errno == EINTR);
    return count == 1 ? 0 : ECANCELED;
}

void owner_child_exec(owner_record *record) {
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
