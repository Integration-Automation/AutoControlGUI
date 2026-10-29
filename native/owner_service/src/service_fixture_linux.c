#define _GNU_SOURCE
/* Acceptance-only seams of the owner service; empty in every installed build. */
#include "native_service.h"
#include <fcntl.h>
#include <sys/stat.h>

#ifdef NO_ACCEPTANCE_BUILD
/* Real listener, peers and leases over a non-protected anchor. Never linked into
 * the installed service; its scopes can reach no_submit only to meet the gate. */
bool fixture_service_guardian(service_state *service, int channel) {
    no_error error;
    service->guardian = (owned_fd){FD_OWNED, channel};
    service->generation = 1;
    return peer_identity_from_connection(&service->guardian_peer, channel, &error) &&
        peer_enable_credentials(channel, &error);
}

bool fixture_service_peer_only(service_state *service, int listener, int anchor, no_id epoch) {
    struct stat status;
    no_error error;
    service->listener = (owned_fd){FD_OWNED, listener};
    service->epoch_anchor = (owned_fd){FD_OWNED, anchor};
    if (fstat(anchor, &status) == -1 || !peer_enable_credentials(listener, &error)) return false;
    int flags = fcntl(listener, F_GETFL);
    if (flags == -1 || fcntl(listener, F_SETFL, flags | O_NONBLOCK) == -1) return false;
    service->epoch_device = (uint64_t)status.st_dev;
    service->epoch = epoch;
    no_boot_policy policy = {.capacity = service->policy->record_capacity, .epoch = epoch};
    service->runtime = no_runtime_create(&policy, &error);
    if (!service->runtime) return false;
    service->phase = BOOT_PEER_EVIDENCE_ONLY;
    return true;
}
#endif
