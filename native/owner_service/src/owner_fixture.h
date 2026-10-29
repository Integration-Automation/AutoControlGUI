#ifndef OWNER_FIXTURE_H
#define OWNER_FIXTURE_H
#ifndef NO_ACCEPTANCE_BUILD
#error Fixture access is not a production interface
#endif
#include "native_owner.h"
#include <stdatomic.h>

typedef struct fixture_snapshot {
    bool before_call, after_success, revoked, joined, direct_fixture_complete, sticky;
    bool child_dead, no_child, io_settled;
    bool creation_returned, worker_finished, started_published;
    bool failed_call;
    bool native_success, pidfd_adopted;
    bool nested_delivered, delivery_wiped;
    unsigned launch_attempts, owned_count, close_attempts;
    int scratch_diagnostic;
    int closed_pidfd;
    unsigned successful_joins;
    uint64_t request_id;
    no_wait_status wait;
    no_start_outcome start;
} fixture_snapshot;

no_runtime *fixture_runtime(size_t capacity);
bool fixture_allocation_failure(unsigned allocation, no_error *error);
no_submit_result fixture_submit(no_runtime *, unsigned key, const char *executable,
                                unsigned flags, no_ticket *, no_error *);
bool fixture_inspect(no_runtime *, no_ticket, fixture_snapshot *);
void fixture_release(no_runtime *, no_ticket);
void fixture_hold_report(no_runtime *, no_ticket, atomic_bool *entered, atomic_bool *release);
bool fixture_failure_write_attempted(no_runtime *, no_ticket);
bool fixture_relay_lease(no_runtime *, no_ticket, no_id *lease);

enum {
    FIXTURE_HOLD_BEFORE = 1,
    FIXTURE_HOLD_AFTER = 2,
    FIXTURE_FAIL_THREAD = 4,
    FIXTURE_FAIL_CLOSE = 8,
    FIXTURE_HOLD_START = 16,
    FIXTURE_ADMISSION_PROBE = 32,
    FIXTURE_CHILD_HOLD = 64,
    FIXTURE_FAIL_CHILD_SETUP = 128,
    FIXTURE_HOLD_ADOPTION = 256,
    FIXTURE_NESTED_BOOTSTRAP = 512, /* The child receives a fixed capability frame on fd 4. */
    FIXTURE_RELAY = 1024 /* fd 0 and fd 1 carry relayed application bytes. */
};
#endif
