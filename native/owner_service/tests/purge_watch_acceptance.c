#define _GNU_SOURCE
/* Unprivileged acceptance of the purge stall watch: a purge child that stops making progress
 * is killed and its slice purged again; one that keeps beating is never cut short; one a kill
 * does not end is handed to the main loop (or, with no pidfd to watch, its slice tainted);
 * and the watch still works without the shared heartbeat or without pidfd_open. The real
 * purge is replaced by fakes; the guardian's own code runs unchanged, with short allowances. */
#define PURGE_STALL_NS (1ULL * 1000000000ULL)
#define PURGE_CHECK_MS 100
#define PURGE_UNWATCHED_NS (2ULL * 1000000000ULL)
#include <stdarg.h>
#include <stdio.h>
#include <sys/syscall.h>

static long test_syscall(long number, ...);
#define syscall test_syscall
#include "../src/guardian_epoch_linux.c"
#undef syscall
long syscall(long number, ...);

static bool kill_disabled, pidfd_open_disabled;

/* The guardian's raw calls pass through here: a kill can be made to do nothing (a child in a
 * call no signal ends), and pidfd_open made to fail. */
static long test_syscall(long number, ...) {
    va_list arguments;
    va_start(arguments, number);
    long a = va_arg(arguments, long), b = va_arg(arguments, long), c = va_arg(arguments, long);
    long d = va_arg(arguments, long), e = va_arg(arguments, long), f = va_arg(arguments, long);
    va_end(arguments);
    if (kill_disabled && (number == SYS_pidfd_send_signal || number == SYS_kill)) return 0;
    if (pidfd_open_disabled && number == SYS_pidfd_open) { errno = ENOSYS; return -1; }
    return syscall(number, a, b, c, d, e, f);
}

/* The fake purge: stall without a beat, or beat for three seconds and finish clean. */
static int fake_beats;
uint64_t *guardian_purge_heartbeat;
bool guardian_purge_unshare(void) { return true; }
guardian_purge_outcome guardian_purge_payloads(const guardian_manifest *manifest, int slice) {
    (void)manifest;
    (void)slice;
    if (!fake_beats) for (;;) pause();
    for (int i = 0; i < fake_beats; ++i) {
        if (guardian_purge_heartbeat) __atomic_fetch_add(guardian_purge_heartbeat, 1, __ATOMIC_RELAXED);
        usleep(100000);
    }
    return PURGE_CLEAN;
}

static int failures;
#define CHECK(name, condition) \
    do { if (!(condition)) { fprintf(stderr, "%s: %s\n", name, #condition); ++failures; } } while (0)

static guardian_manifest manifest;

static void fresh(guardian_state *state, bool heartbeat) {
    *state = (guardian_state){.manifest = &manifest};
    for (int s = 0; s < SERVICE_PAYLOAD_SLICES; ++s) state->purging[s] = -1;
    if (heartbeat) {
        void *beats = mmap(NULL, sizeof(uint64_t) * SERVICE_PAYLOAD_SLICES, PROT_READ | PROT_WRITE,
                           MAP_SHARED | MAP_ANONYMOUS, -1, 0);
        state->heartbeat = beats == MAP_FAILED ? NULL : beats;
    }
}

static double seconds(uint64_t from) { return (double)(now_ns() - from) / 1e9; }

int main(void) {
    guardian_state state;

    /* A stalled child is killed and its slice purged again, never tainted. */
    fresh(&state, true);
    fake_beats = 0;
    uint64_t started = now_ns();
    purge(&state, 0);
    CHECK("stalled", state.repurge[0] && !state.tainted[0] && state.purging[0] < 0 && state.stall_round[0] == 1);
    CHECK("stalled_promptly", seconds(started) < 5);

    /* A child that keeps beating for longer than the allowance is never cut short. */
    fresh(&state, true);
    fake_beats = 30;
    started = now_ns();
    purge(&state, 1);
    CHECK("beating", !state.repurge[1] && !state.tainted[1] && state.stall_round[1] == 0);
    CHECK("beating_ran_through", seconds(started) >= 2.9);

    /* A kill that does not end the child: handed to the main loop, reaped when it ends. */
    fresh(&state, true);
    fake_beats = 0;
    kill_disabled = true;
    purge(&state, 2);
    kill_disabled = false;
    CHECK("handed_over", state.purging[2] >= 0 && state.stalled[2] && !state.repurge[2]);
    if (state.purging[2] >= 0) {
        syscall(SYS_pidfd_send_signal, state.purging[2], SIGKILL, NULL, 0);
        guardian_purge_reap(&state, 2);
        CHECK("reaped_after_hand_over", state.purging[2] < 0 && state.repurge[2] && !state.tainted[2]);
    }

    /* No shared heartbeat: the longest allowance, then killed all the same. */
    fresh(&state, false);
    fake_beats = 0;
    started = now_ns();
    purge(&state, 3);
    CHECK("unwatched", state.repurge[3] && !state.tainted[3] && seconds(started) >= 1.9);

    /* The same after one stall in a row: twice as long. */
    unsigned round = state.stall_round[3];
    fresh(&state, false);
    state.stall_round[3] = round;
    fake_beats = 0;
    started = now_ns();
    purge(&state, 3);
    CHECK("unwatched_doubles", round == 1 && state.repurge[3] && seconds(started) >= 3.9);

    /* A child the guardian cannot wait for (SIGCHLD ignored: reaped behind its back) is not
     * taken for a clean purge: its slice is tainted. */
    fresh(&state, true);
    fake_beats = 3;
    pidfd_open_disabled = true;
    signal(SIGCHLD, SIG_IGN);
    purge(&state, 2);
    signal(SIGCHLD, SIG_DFL);
    pidfd_open_disabled = false;
    CHECK("unknown_end_taints", state.tainted[2] && !state.repurge[2]);

    /* No pidfd: watched by its pid, killed by its pid. */
    fresh(&state, true);
    fake_beats = 0;
    pidfd_open_disabled = true;
    purge(&state, 0);
    CHECK("no_pidfd", state.repurge[0] && !state.tainted[0] && state.purging[0] < 0);

    /* No pidfd and a kill that does nothing: nothing can tell when it ends, so the slice is
     * tainted and the guardian goes on. */
    fresh(&state, true);
    fake_beats = 0;
    kill_disabled = true;
    pid_t before = getpid();
    purge(&state, 1);
    kill_disabled = false;
    pidfd_open_disabled = false;
    CHECK("no_pidfd_unkillable", state.tainted[1] && state.purging[1] < 0 && getpid() == before);
    /* Its child is still there: end exactly this process's children, and reap them. */
    char path[64];
    snprintf(path, sizeof(path), "/proc/self/task/%d/children", (int)before);
    FILE *children = fopen(path, "re");
    int child;
    while (children && fscanf(children, "%d", &child) == 1) kill(child, SIGKILL);
    if (children) fclose(children);
    for (int round = 0; round < 50 && waitpid(-1, NULL, WNOHANG) >= 0; ++round) usleep(20000);
    /* Anything still there has PR_SET_PDEATHSIG and ends with this process. */

    printf("{\"failures\": %d}\n", failures);
    return failures ? 1 : 0;
}
