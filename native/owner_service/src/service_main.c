#define _GNU_SOURCE
/* The installed owner service. Its only inputs are the guardian endpoint on
 * SERVICE_GUARDIAN_FD and the manifest policy compiled in from service_manifest.c:
 * no argument, environment value or path can stand in for either. */
#include "native_service.h"
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>

enum {
    EXIT_DRAINED = 0,
    EXIT_POLICY = 64,          /* The compiled manifest is invalid; nothing was taken. */
    EXIT_REFUSED = 65,         /* No usable guardian endpoint; nothing was taken. */
    EXIT_CLEAN_FAILURE = 66,   /* Bootstrap failed and closed everything it received. */
    EXIT_UNRESOLVED = 70,      /* Bootstrap left owned state; the guardian must recover. */
    EXIT_STICKY = 71,          /* Drain could not prove every descriptor closed. */
};

#define SERVICE_BOOTSTRAP_NS 5000000000ULL
#define SERVICE_DRAIN_STEP_NS 1000000000ULL
#define SERVICE_DRAIN_LIMIT_NS 30000000000ULL /* Records settle in milliseconds; 30 s is stuck. */

extern const service_policy service_manifest;

/* Diagnostics go to the guardian's journal on stderr; payloads never inherit it. */
static int report(const char *stage, no_error error, int code) {
    fprintf(stderr, "autocontrol-owner-service: %s kind %d errno %d operation %u\n", stage, (int)error.kind,
            error.system_errno, error.operation_code);
    return code;
}

/* Drain retries while records still borrow scopes: pending keeps ownership in this
 * process, it never frees what a worker still uses. Only a proven-clean drain frees the
 * service. Past the limit the process exits without freeing: the kernel drops its
 * descriptors, and the guardian, seeing it gone, kills and removes the whole epoch,
 * stuck helpers included, then grants the next one. */
static int drain(service_state *service) {
    uint64_t limit = owner_now() + SERVICE_DRAIN_LIMIT_NS;
    for (;;) {
        service_result result = service_drain(service, (no_deadline){owner_now() + SERVICE_DRAIN_STEP_NS});
        if (result == SERVICE_CLEAN) return service_free(&service) ? EXIT_DRAINED : EXIT_STICKY;
        if (result == SERVICE_STICKY) return report("drain", service->first_error, EXIT_STICKY);
        if (owner_now() >= limit) return report("drain deadline", service->first_error, EXIT_STICKY);
    }
}

int main(void) {
    /* Workers write to pipes whose reader may have died; that must be EPIPE, not death. */
    signal(SIGPIPE, SIG_IGN);
    no_error error;
    service_state *service = service_allocate(&service_manifest, &error);
    if (!service) return report("policy", error, EXIT_POLICY);
    bootstrap_result booted = service_bootstrap(service, SERVICE_GUARDIAN_FD,
                                                (no_deadline){owner_now() + SERVICE_BOOTSTRAP_NS}, &error);
    if (booted == BOOTSTRAP_REFUSED) {
        service_free(&service);
        return report("refused", error, EXIT_REFUSED);
    }
    if (booted == BOOTSTRAP_CLEAN_FAILURE) {
        service_free(&service);
        return report("bootstrap", error, EXIT_CLEAN_FAILURE);
    }
    if (booted == BOOTSTRAP_OWNED_UNRESOLVED) return report("bootstrap", error, EXIT_UNRESOLVED);
    while (service_run_one(service, 100) == SERVICE_RUNNING) continue;
    return drain(service);
}
