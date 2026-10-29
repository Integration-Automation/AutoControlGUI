#define _GNU_SOURCE
/* The guardian's own judgement of the compiled manifest, before it builds the identity
 * filter or starts anything: the service would refuse it later, but by then the filter
 * built from it already runs. */
#include "guardian.h"
#include <errno.h>
#include <grp.h>
#include <pwd.h>

#define PAYLOAD_ID_FLOOR 1000u /* Below it: system accounts and groups, such as disk or adm. */

/* No ID of the range is known to the host's databases: an allocated one could be a system
 * group (disk is root-equivalent) or a real user whose files the purge would remove. */
static bool unallocated(uint32_t uid_base, uint32_t gid_base) {
    if (uid_base < PAYLOAD_ID_FLOOR || gid_base < PAYLOAD_ID_FLOOR) return false;
    for (uint32_t k = 0; k < SERVICE_PAYLOAD_IDS; ++k) {
        /* NULL with errno set is a database error (an LDAP or sssd outage): refused too. */
        errno = 0;
        if (getpwuid(uid_base + k) || errno) return false;
        errno = 0;
        if (getgrgid(gid_base + k) || errno) return false;
    }
    return true;
}

static bool in_any_range(const service_policy *service, uint32_t uid, uint32_t gid) {
    for (size_t i = 0; i < service->policy_count; ++i) {
        const service_launch_policy *entry = &service->policies[i];
        if ((uid >= entry->payload_uid && uid - entry->payload_uid < SERVICE_PAYLOAD_IDS) ||
            (gid >= entry->payload_gid && gid - entry->payload_gid < SERVICE_PAYLOAD_IDS)) return true;
    }
    return false;
}

/* A client entry is one account, or exactly one policy's payload range. */
static bool client_valid(const service_policy *service, const guardian_client *client) {
    if (client->id_count <= 1) return true;
    if (client->id_count != SERVICE_PAYLOAD_IDS) return false;
    for (size_t i = 0; i < service->policy_count; ++i)
        if (service->policies[i].payload_uid == client->uid && service->policies[i].payload_gid == client->gid)
            return true;
    return false;
}

bool guardian_manifest_valid(const guardian_manifest *manifest) {
    const service_policy *service = manifest->service;
    if (!service || !service_policy_valid(service) || manifest->client_count > GUARDIAN_CLIENT_LIMIT ||
        (service->socket_gid && manifest->listener_gid != service->socket_gid) ||
        in_any_range(service, manifest->service_uid, manifest->service_gid)) return false;
    for (size_t i = 0; i < manifest->client_count; ++i)
        if (!client_valid(service, &manifest->clients[i])) return false;
    for (size_t i = 0; i < service->policy_count; ++i)
        if (!unallocated(service->policies[i].payload_uid, service->policies[i].payload_gid)) return false;
    return true;
}
