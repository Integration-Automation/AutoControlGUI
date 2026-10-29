#define _GNU_SOURCE
/* End-to-end harness for the Python client. Runs a peer-evidence service whose START
 * admits direct-fixture relay records running the core acceptance binary in "rpc"
 * mode. Prints the listener path, serves until stdin closes, then reports what the
 * service and the core saw. Not containment evidence: the gate stays closed. */
#include "native_owner.c"
/* The shared acceptance helpers include client-side functions this harness does not call. */
#pragma GCC diagnostic ignored "-Wunused-function"
#include "service_test_support.h"

static const char *close_reason_name(close_reason reason) {
    static const char *const names[] = {"none", "requested", "disconnect", "peer_death", "expired", "reply_lost",
                                        "sender_mismatch", "shutdown", "failed_issue"};
    return reason < sizeof(names) / sizeof(names[0]) ? names[reason] : "unknown";
}

static void report(service_state *service) {
    printf("{\"leases\": [");
    for (size_t i = 0; i < service->lease_count; ++i) {
        const service_lease *lease = &service->leases[i];
        printf("%s{\"open\": %s, \"reason\": \"%s\"}", i ? ", " : "", lease->phase == LEASE_OPEN ? "true" : "false",
               close_reason_name(lease->reason));
    }
    printf("], \"records\": [");
    for (size_t i = 0; i < service->runtime->count; ++i) {
        owner_record *record = &service->runtime->records[i];
        fixture_snapshot snapshot;
        fixture_inspect(service->runtime, record->ticket, &snapshot);
        printf("%s{\"child_dead\": %s, \"revoked\": %s, \"wait_kind\": %d, \"wait_value\": %d, \"owned\": %u}",
               i ? ", " : "", snapshot.child_dead ? "true" : "false", snapshot.revoked ? "true" : "false",
               snapshot.wait.kind, snapshot.wait.value, snapshot.owned_count);
    }
    printf("]}\n");
    fflush(stdout);
}

int main(int argc, char **argv) {
    if (argc != 2 || argv[1][0] != '/') return 64;
    fixture_setup("service-e2e");
    service_state *service = peer_service((no_id){142, 1});
    service->fixture_executable = argv[1];
    printf("%s\n", listener_path);
    fflush(stdout);
    for (;;) {
        REQUIRE(service_run_one(service, 10) == SERVICE_RUNNING);
        struct pollfd input = {.fd = 0, .events = POLLIN};
        if (poll(&input, 1, 0) > 0) {
            char byte;
            if (read(0, &byte, 1) <= 0) break;
        }
    }
    /* Let fixture workers finish what the closed leases revoked before reporting. */
    uint64_t limit = owner_now() + 5000000000ULL;
    bool settled = false;
    while (!settled && owner_now() < limit) {
        service_run_one(service, 10);
        settled = true;
        for (size_t i = 0; i < service->runtime->count; ++i) {
            fixture_snapshot snapshot;
            fixture_inspect(service->runtime, service->runtime->records[i].ticket, &snapshot);
            settled &= snapshot.joined;
        }
    }
    report(service);
    service_result drained = service_drain(service, (no_deadline){owner_now() + 5000000000ULL});
    bool freed = drained == SERVICE_CLEAN && service_free(&service);
    fixture_teardown();
    return freed ? 0 : 3;
}
