#define _GNU_SOURCE
/* Manifest validation for the owner service: accounts, payload ranges, child policies and
 * every limit. A manifest that fails here never starts a service. */
#include "native_service.h"
#include <string.h>
#include <unistd.h>

/* Guardian, clients and payloads are disjoint accounts: a payload that matched a
 * client principal could open top-level leases outside its parent's fence. */
static bool client_account(const service_policy *policy, uint32_t uid) {
    for (size_t i = 0; i < policy->client_count; ++i) if (policy->clients[i].uid == uid) return true;
    return false;
}

static bool in_range(uint32_t id, uint32_t base) { return id >= base && id - base < SERVICE_PAYLOAD_IDS; }

/* No payload ID is the guardian's, a client's or this service's, and no payload group is
 * root's, a client's, the socket's or this service's: a shared group would give payloads
 * the client's files, and the service's own account would let a payload write the
 * epoch's cgroup.procs. The ranges never wrap and never reach -1, "unchanged". */
static bool payload_accounts_valid(const service_policy *policy, const service_launch_policy *entry) {
    uint32_t uid = entry->payload_uid, gid = entry->payload_gid;
    if (uid > UINT32_MAX - SERVICE_PAYLOAD_IDS || gid > UINT32_MAX - SERVICE_PAYLOAD_IDS || !uid || !gid) return false;
    if (in_range(policy->guardian.uid, uid) || in_range((uint32_t)geteuid(), uid) || in_range(0, gid) ||
        in_range(policy->guardian.gid, gid) || in_range((uint32_t)getegid(), gid) ||
        (policy->socket_gid && in_range(policy->socket_gid, gid))) return false;
    for (size_t i = 0; i < policy->client_count; ++i)
        if (in_range(policy->clients[i].uid, uid) || in_range(policy->clients[i].gid, gid)) return false;
    return true;
}

/* Two policies' payload ranges are the same range or share no ID, so one lease position
 * never maps two live helpers to one account. */
static bool ranges_valid(const service_policy *policy) {
    for (size_t i = 0; i < policy->policy_count; ++i)
        for (size_t j = 0; j < i; ++j) {
            const service_launch_policy *a = &policy->policies[i], *b = &policy->policies[j];
            bool same_uid = a->payload_uid == b->payload_uid, same_gid = a->payload_gid == b->payload_gid;
            bool apart_uid = a->payload_uid >= b->payload_uid + SERVICE_PAYLOAD_IDS ||
                b->payload_uid >= a->payload_uid + SERVICE_PAYLOAD_IDS;
            bool apart_gid = a->payload_gid >= b->payload_gid + SERVICE_PAYLOAD_IDS ||
                b->payload_gid >= a->payload_gid + SERVICE_PAYLOAD_IDS;
            if (!(same_uid || apart_uid) || !(same_gid || apart_gid)) return false;
        }
    return true;
}

static bool launch_policy_valid(const service_policy *policy, const service_launch_policy *entry) {
    return entry->id < 32 && entry->executable && entry->executable[0] == '/' && entry->cwd &&
        entry->cwd[0] == '/' && entry->fixed_argc && entry->fixed_argv &&
        entry->fixed_argc + entry->max_client_arguments <= NO_ARGUMENT_LIMIT &&
        entry->envc <= NO_ARGUMENT_LIMIT && (!entry->envc || entry->env) &&
        (!entry->max_client_arguments || (entry->argument_alphabet && entry->argument_alphabet[0])) &&
        payload_accounts_valid(policy, entry);
}

static const service_launch_policy *policy_by_id(const service_policy *policy, uint32_t id) {
    for (size_t i = 0; i < policy->policy_count; ++i) if (policy->policies[i].id == id) return &policy->policies[i];
    return NULL;
}

/* Every child a policy may start exists, is nested-only, and draws from the parent's own
 * payload range: a nested child never reaches a range its parent did not have. */
static bool children_valid(const service_policy *policy, const service_launch_policy *parent) {
    for (uint32_t id = 0; id < 32; ++id) {
        if (!(parent->child_policies & (UINT32_C(1) << id))) continue;
        const service_launch_policy *child = policy_by_id(policy, id);
        if (!child || !child->nested || child->payload_uid != parent->payload_uid ||
            child->payload_gid != parent->payload_gid) return false;
    }
    return true;
}

bool service_policy_valid(const service_policy *policy) {
    if (!policy || !policy->policies || !policy->policy_count || !policy->lease_lifetime_ns ||
        !policy->record_capacity || policy->record_capacity > NO_RECORD_LIMIT ||
        policy->client_count > SERVICE_CLIENT_LIMIT || client_account(policy, policy->guardian.uid) ||
        !policy->client_lease_quota || policy->client_lease_quota > SERVICE_LEASE_LIMIT ||
        !policy->nested_lease_quota || policy->nested_lease_quota > SERVICE_LEASE_LIMIT ||
        policy->lease_max_age_ns < policy->lease_lifetime_ns ||
        policy->record_pids_max < SERVICE_MIN_PIDS || policy->record_memory_max < SERVICE_MIN_MEMORY ||
        !policy->connections_per_account || policy->connections_per_account > SERVICE_CONNECTION_LIMIT / 2 ||
        /* Payload accounts are shared by policy, so one client per service until each client
         * has its own payload accounts. */
        policy->client_count != 1) return false;
    for (size_t i = 0; i < policy->policy_count; ++i) {
        if (!launch_policy_valid(policy, &policy->policies[i])) return false;
        for (size_t j = 0; j < i; ++j) if (policy->policies[j].id == policy->policies[i].id) return false;
    }
    for (size_t i = 0; i < policy->policy_count; ++i)
        if (!children_valid(policy, &policy->policies[i])) return false;
    return ranges_valid(policy);
}

/* The manifest grammar: a non-empty word over the policy alphabet that cannot be
 * read as an option. Anything richer needs its own reviewed policy. */
static bool argument_allowed(const char *argument, size_t length, const service_launch_policy *policy) {
    return length && argument[0] != '-' && strspn(argument, policy->argument_alphabet) == length;
}

bool service_client_arguments(const service_request *request, const service_launch_policy *policy,
                             const char **argv, size_t *argc) {
    if (request->argc > policy->max_client_arguments) return false;
    for (size_t i = 0; i < policy->fixed_argc; ++i) argv[i] = policy->fixed_argv[i];
    size_t offset = 0;
    for (size_t i = 0; i < request->argc; ++i) {
        size_t length = strnlen(request->arguments + offset, SERVICE_ARGUMENT_BYTES - offset);
        if (offset + length == SERVICE_ARGUMENT_BYTES ||
            !argument_allowed(request->arguments + offset, length, policy)) return false;
        argv[policy->fixed_argc + i] = request->arguments + offset;
        offset += length + 1;
    }
    for (size_t i = offset; i < SERVICE_ARGUMENT_BYTES; ++i) if (request->arguments[i]) return false;
    *argc = policy->fixed_argc + request->argc;
    argv[*argc] = NULL;
    return true;
}

/* Only a policy that permits children carries a capability at all. */
bool service_fresh_capability(const service_launch_policy *policy, uint8_t *capability, bool *wanted) {
    *wanted = policy->child_policies != 0;
    return !*wanted || service_random(capability, SERVICE_CAPABILITY_BYTES);
}
