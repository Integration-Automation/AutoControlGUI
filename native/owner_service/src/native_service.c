#define _GNU_SOURCE
#include "native_service.h"
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

/* One thread owns everything here: connections, leases, scope slots and drain.
 * Record workers keep their own resources; the core registry stays the admission
 * ledger. No resource syscall runs under the core registry lock. */

static bool same_id(no_id a, no_id b) { return a.high == b.high && a.low == b.low; }
static bool zero_id(no_id a) { return a.high == 0 && a.low == 0; }
static bool same_ticket(no_ticket a, no_ticket b) {
    return same_id(a.service_epoch, b.service_epoch) && same_id(a.record, b.record);
}

static void note_close(service_state *service, owned_fd *slot) {
    if (!service_close_fd(slot)) service->close_uncertain = true;
}

/* Guardian, clients and payloads are disjoint accounts: a payload that matched a
 * client principal could open top-level leases outside its parent's fence. */
static bool client_account(const service_policy *policy, uint32_t uid) {
    for (size_t i = 0; i < policy->client_count; ++i) if (policy->clients[i].uid == uid) return true;
    return false;
}

static bool client_group(const service_policy *policy, uint32_t gid) {
    for (size_t i = 0; i < policy->client_count; ++i) if (policy->clients[i].gid == gid) return true;
    return false;
}

/* A payload shares no account or group with the guardian, a client or this service:
 * a shared group would give payloads the client's files, and the service's own account
 * would let a payload write the epoch's cgroup.procs. */
static bool payload_accounts_valid(const service_policy *policy, const service_launch_policy *entry) {
    return entry->payload_uid != policy->guardian.uid && entry->payload_uid != geteuid() &&
        !client_account(policy, entry->payload_uid) && entry->payload_gid != 0 &&
        entry->payload_gid != policy->guardian.gid && entry->payload_gid != getegid() &&
        !client_group(policy, entry->payload_gid) && entry->payload_gid != policy->socket_gid;
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

/* Every child a policy may start exists, is nested-only, and runs as the parent's own
 * payload account: a nested child never reaches an account its parent did not have. */
static bool children_valid(const service_policy *policy, const service_launch_policy *parent) {
    for (uint32_t id = 0; id < 32; ++id) {
        if (!(parent->child_policies & (UINT32_C(1) << id))) continue;
        const service_launch_policy *child = policy_by_id(policy, id);
        if (!child || !child->nested || child->payload_uid != parent->payload_uid ||
            child->payload_gid != parent->payload_gid) return false;
    }
    return true;
}

static bool policy_valid(const service_policy *policy) {
    if (!policy || !policy->policies || !policy->policy_count || !policy->lease_lifetime_ns ||
        !policy->record_capacity || policy->record_capacity > NO_RECORD_LIMIT ||
        policy->client_count > SERVICE_CLIENT_LIMIT || client_account(policy, policy->guardian.uid) ||
        !policy->client_lease_quota || policy->client_lease_quota > SERVICE_LEASE_LIMIT ||
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
    return true;
}

service_state *service_allocate(const service_policy *policy, no_error *error) {
    *error = (no_error){0};
    if (!policy_valid(policy)) { error->kind = NO_ERROR_ARGUMENT; return NULL; }
    service_state *service = calloc(1, sizeof(*service));
    if (!service) { error->kind = NO_ERROR_ALLOCATION; return NULL; }
    service->policy = policy;
    service->phase = BOOT_EMPTY;
    for (size_t i = 0; i < SERVICE_LEASE_LIMIT; ++i) {
        atomic_init(&service->scopes.slots[i].borrowers, 0);
        atomic_init(&service->scopes.slots[i].issuance_closed, true);
    }
    return service;
}

static bool admitting(const service_state *service) {
#ifdef NO_ACCEPTANCE_BUILD
    if (service->phase == BOOT_PEER_EVIDENCE_ONLY) return true;
#endif
    return service->phase == BOOT_ACTIVE;
}

static const service_launch_policy *find_policy(const service_state *service, uint32_t id) {
    for (size_t i = 0; i < service->policy->policy_count; ++i)
        if (service->policy->policies[i].id == id) return &service->policy->policies[i];
    return NULL;
}

/* The guardian verified this connector's namespaces before handing the connection over. */
static bool top_level_principal(const service_state *service, const peer_identity *connector) {
    for (size_t i = 0; i < service->policy->client_count; ++i) {
        const service_principal *principal = &service->policy->clients[i];
        if (principal->uid == connector->credentials.uid && principal->gid == connector->credentials.gid)
            return true;
    }
    return false;
}

static service_lease *find_lease(service_state *service, no_id id) {
    if (zero_id(id)) return NULL;
    for (size_t i = 0; i < service->lease_count; ++i)
        if (service->leases[i].phase != LEASE_UNUSED && same_id(service->leases[i].id, id)) return &service->leases[i];
    return NULL;
}

/* A nonce names one OPEN on one connection: a lease never moves between them. */
static service_lease *find_replay(service_state *service, size_t index, no_id nonce) {
    const service_connection *connection = &service->connections[index];
    for (size_t i = 0; i < service->lease_count; ++i) {
        const service_lease *lease = &service->leases[i];
        if (lease->connection == index && lease->connection_generation == connection->generation &&
            lease->holder_inode == connection->connector.inode && same_id(lease->open_nonce, nonce))
            return &service->leases[i];
    }
    return NULL;
}

static service_reply reply_for(const service_request *request, service_status status, no_error error) {
    service_reply reply;
    memset(&reply, 0, sizeof(reply));
    reply.magic = SERVICE_MAGIC; reply.version = SERVICE_VERSION; reply.opcode = request->opcode;
    reply.status = status; reply.error = error; reply.nonce = request->nonce;
    return reply;
}

static bool transmit(service_connection *connection, const service_reply *reply) {
    ssize_t sent;
    do {
        sent = send(connection->socket.number, reply, sizeof(*reply), MSG_NOSIGNAL | MSG_DONTWAIT);
    } while (sent < 0 && errno == EINTR);
    return sent == (ssize_t)sizeof(*reply);
}

static bool send_reply(service_connection *connection, const service_request *request, service_status status,
                       no_error error, const service_lease *lease, no_ticket ticket) {
    service_reply reply = reply_for(request, status, error);
    reply.ticket = ticket;
    if (lease && (status == STATUS_OK || status == STATUS_EXISTING)) {
        reply.lease = lease->id;
        reply.lease_deadline_ns = lease->expires_ns;
    }
    return transmit(connection, &reply);
}

/* Monotone and idempotent: every closure path converges here. Issuance closes
 * first, the core fences the registered ID, then the issuer reference goes. */
void service_close_lease(service_state *service, service_lease *lease, close_reason reason) {
    if (lease->phase != LEASE_OPEN) return;
    authenticated_scope_slot *slot = lease->scope.reference.slot;
    atomic_store_explicit(&slot->issuance_closed, true, memory_order_release);
    if (service->runtime) no_revoke_lease(service->runtime, lease->id);
    scope_release(&lease->scope.reference);
    lease->phase = LEASE_CLOSED;
    lease->reason = reason;
}

static bool duplicate_into(owned_fd *destination, const owned_fd *source) {
    if (source->state != FD_OWNED) return false;
    int number;
    do { number = fcntl(source->number, F_DUPFD_CLOEXEC, 3); } while (number < 0 && errno == EINTR);
    if (number < 0) return false;
    destination->number = number;
    destination->state = FD_OWNED;
    return true;
}

/* Generated into a local: the reserved entry is already visible to find_lease. */
static bool fresh_lease_id(service_state *service, no_id *id) {
    for (unsigned attempt = 0; attempt < 4; ++attempt) {
        no_id candidate;
        if (!service_random(&candidate, sizeof(candidate))) return false;
        if (!zero_id(candidate) && !find_lease(service, candidate)) { *id = candidate; return true; }
    }
    return false;
}

static service_status status_for(no_error_kind kind) {
    switch (kind) {
    case NO_ERROR_CAPACITY: return STATUS_CAPACITY;
    case NO_ERROR_ADMISSION_CLOSED: return STATUS_CLOSED;
    case NO_ERROR_KEY_CONFLICT: return STATUS_CONFLICT;
    case NO_ERROR_UNAVAILABLE: return STATUS_UNAVAILABLE;
    default: return STATUS_REJECTED;
    }
}

/* Positions never return within an epoch, so the quota counts open and spent leases:
 * one account cannot exhaust the epoch for every other client. */
static size_t positions_used(const service_state *service, uint32_t uid) {
    size_t used = 0;
    for (size_t i = 0; i < service->lease_count; ++i) used += service->leases[i].holder_uid == uid;
    return used;
}

/* Reserve, build unpublished, register last. A failure leaves a closed tombstone
 * with zero borrowers, so the single owner scan closes whatever was acquired. */
static service_status issue_lease(service_state *service, size_t index, const service_request *request,
                                  const no_ticket *parent, service_lease **out, no_error *error) {
    service_connection *connection = &service->connections[index];
    service_lease *replay = find_replay(service, index, request->nonce);
    if (replay) {
        if (replay->nested != (parent != NULL) || replay->policy != request->policy ||
            (parent && !same_ticket(replay->parent, *parent))) return STATUS_CONFLICT;
        *out = replay;
        return replay->phase == LEASE_OPEN ? STATUS_EXISTING : STATUS_CLOSED;
    }
    if (service->lease_count == SERVICE_LEASE_LIMIT || positions_used(service, connection->connector.credentials.uid) >=
        service->policy->client_lease_quota) {
        error->kind = NO_ERROR_CAPACITY;
        return STATUS_CAPACITY;
    }
    size_t position = service->lease_count++;
    service->scopes.count = service->lease_count;
    service_lease *lease = &service->leases[position];
    authenticated_scope_slot *slot = &service->scopes.slots[position];
    *lease = (service_lease){.phase = LEASE_RESERVED, .open_nonce = request->nonce, .connection = index,
        .connection_generation = connection->generation, .holder_inode = connection->connector.inode,
        .holder_uid = connection->connector.credentials.uid,
        .nested = parent != NULL, .policy = request->policy};
    if (parent) lease->parent = *parent;
    bool built = fresh_lease_id(service, &lease->id) &&
        service_random(&slot->identity.identity, sizeof(slot->identity.identity)) &&
        duplicate_into(&slot->peer, &connection->connector.pidfd) &&
        (parent || duplicate_into(&slot->epoch_anchor, &service->epoch_anchor));
    if (!built && !error->kind) *error = (no_error){NO_ERROR_UNAVAILABLE, errno, 10};
    slot->identity.epoch = service->epoch;
    slot->identity.lease = lease->id;
    slot->identity.parent_is_epoch = parent == NULL;
    if (parent) slot->identity.permitted_parent = *parent;
    if (built) built = owner_register_lease(service->runtime, lease->id, parent, error);
    if (!built) {
        lease->phase = LEASE_CLOSED;
        lease->reason = CLOSE_FAILED_ISSUE;
        return status_for(error->kind);
    }
    lease->opened_ns = owner_now();
    lease->expires_ns = lease->opened_ns + service->policy->lease_lifetime_ns;
    lease->scope.reference.slot = slot;
    atomic_store_explicit(&slot->borrowers, 1, memory_order_relaxed);
    atomic_store_explicit(&slot->issuance_closed, false, memory_order_release);
    lease->phase = LEASE_OPEN;
    *out = lease;
    return STATUS_OK;
}

static void open_top(service_state *service, size_t index, const service_request *request) {
    service_connection *connection = &service->connections[index];
    service_lease *lease = NULL;
    no_error error = {0};
    const service_launch_policy *policy = find_policy(service, request->policy);
    service_status status;
    if (!admitting(service)) status = STATUS_UNAVAILABLE;
    else if (!policy || policy->nested) status = STATUS_REJECTED;
    else if (!top_level_principal(service, &connection->connector)) status = STATUS_UNAUTHENTICATED;
    else status = issue_lease(service, index, request, NULL, &lease, &error);
    if (!send_reply(connection, request, status, error, lease, (no_ticket){0}) && lease && status == STATUS_OK)
        service_close_lease(service, lease, CLOSE_REPLY_LOST);
}

static bool capability_matches(const uint8_t *a, const uint8_t *b) {
    uint8_t difference = 0;
    for (size_t i = 0; i < SERVICE_CAPABILITY_BYTES; ++i) difference |= a[i] ^ b[i];
    return difference == 0;
}

static const nested_grant *grant_for(const service_state *service, no_ticket parent) {
    if (!same_id(parent.service_epoch, service->epoch) || parent.record.high ||
        parent.record.low == 0 || parent.record.low > NO_RECORD_LIMIT) return NULL;
    const nested_grant *grant = &service->grants[parent.record.low - 1];
    return grant->issued ? grant : NULL;
}

/* The connector, already proven to be this packet's sender, must be the payload
 * principal and live inside the exact published payload of an eligible parent.
 * Rechecked on every START: migration out of the payload ends nested authority. */
static service_status nested_member(service_state *service, no_ticket parent, const peer_identity *connector) {
    parent_payload_identity snapshot;
    if (!owner_parent_snapshot(service->runtime, parent, &snapshot)) return STATUS_CLOSED;
    if (connector->credentials.uid != snapshot.payload.uid || connector->credentials.gid != snapshot.payload.gid ||
        snapshot.payload.device != service->epoch_device || !peer_in_cgroup(connector, snapshot.payload.inode))
        return STATUS_UNAUTHENTICATED;
    return STATUS_OK;
}

/* A copied capability names what to check; it never authorizes by itself. */
static service_status nested_policy(service_state *service, const service_request *request,
                                    const peer_identity *connector) {
    const service_launch_policy *policy = find_policy(service, request->policy);
    const nested_grant *grant = grant_for(service, request->parent);
    if (!policy || !policy->nested || !grant || !capability_matches(grant->capability, request->capability))
        return STATUS_REJECTED;
    const service_launch_policy *parent_policy = find_policy(service, grant->policy);
    if (!parent_policy || !(parent_policy->child_policies & (UINT32_C(1) << policy->id))) return STATUS_REJECTED;
    return nested_member(service, request->parent, connector);
}

static void open_child(service_state *service, size_t index, const service_request *request) {
    service_lease *lease = NULL;
    no_error error = {0};
    const peer_identity *connector = &service->connections[index].connector;
    service_status status = admitting(service) ? nested_policy(service, request, connector) : STATUS_UNAVAILABLE;
    if (status == STATUS_OK) status = issue_lease(service, index, request, &request->parent, &lease, &error);
    if (!send_reply(&service->connections[index], request, status, error, lease, (no_ticket){0}) &&
        lease && status == STATUS_OK) service_close_lease(service, lease, CLOSE_REPLY_LOST);
}

/* The lease must be held by this connection's original connector, which the
 * packet sender has already been proven to be. */
static service_lease *held_lease(service_state *service, size_t index, no_id id) {
    service_lease *lease = find_lease(service, id);
    service_connection *connection = &service->connections[index];
    if (!lease || lease->connection != index || lease->connection_generation != connection->generation ||
        lease->holder_inode != connection->connector.inode) return NULL;
    return lease;
}

/* The manifest grammar: a non-empty word over the policy alphabet that cannot be
 * read as an option. Anything richer needs its own reviewed policy. */
static bool argument_allowed(const char *argument, size_t length, const service_launch_policy *policy) {
    return length && argument[0] != '-' && strspn(argument, policy->argument_alphabet) == length;
}

static bool client_arguments(const service_request *request, const service_launch_policy *policy,
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

/* Recorded only for a newly admitted record, with the bytes the core will deliver
 * to that record's child once its payload is published. A replayed START keeps the
 * first record and its capability; the fresh bytes of the retry are discarded. */
static void issue_nested_grant(service_state *service, const service_launch_policy *policy, no_ticket ticket,
                               const uint8_t *capability) {
    if (!capability || ticket.record.high || ticket.record.low == 0 || ticket.record.low > NO_RECORD_LIMIT) return;
    nested_grant *grant = &service->grants[ticket.record.low - 1];
    if (grant->issued) return;
    grant->policy = policy->id;
    memcpy(grant->capability, capability, sizeof(grant->capability));
    grant->issued = true;
}

/* Only a policy that permits children carries a capability at all. */
static bool fresh_capability(const service_launch_policy *policy, uint8_t *capability, bool *wanted) {
    *wanted = policy->child_policies != 0;
    return !*wanted || service_random(capability, SERVICE_CAPABILITY_BYTES);
}

/* Everything START checks before the core sees the request. */
static service_status start_admissible(service_state *service, size_t index, const service_request *request,
                                       const service_lease *lease, const char **argv, size_t *argc) {
    const service_launch_policy *policy = lease ? find_policy(service, lease->policy) : NULL;
    if (!admitting(service)) return STATUS_UNAVAILABLE;
    if (!lease) return STATUS_REJECTED;
    if (lease->phase != LEASE_OPEN) return STATUS_CLOSED;
    if (!policy || !client_arguments(request, policy, argv, argc)) return STATUS_MALFORMED;
    if (lease->nested) return nested_member(service, lease->parent, &service->connections[index].connector);
    return STATUS_OK;
}

static no_submit_result submit(service_state *service, service_lease *lease, const service_request *request,
                               const no_validated_spec *spec, no_ticket *ticket, no_error *error) {
    no_request_key key = {lease->id, request->request};
#ifdef NO_ACCEPTANCE_BUILD
    /* Acceptance only: a direct-fixture relay record stands in for the gated protected
     * launch, so a real client drives socket, lease, relay and close end to end. It is
     * not containment, and its record never reports retirement. */
    if (service->phase == BOOT_PEER_EVIDENCE_ONLY && service->fixture_executable)
        return owner_fixture_submit(service->runtime, key, service->fixture_executable,
                                    (fixture_options){.relay = true, .rpc = true}, ticket, error);
#endif
    return no_submit(service->runtime, &lease->scope, key, spec, ticket, error);
}

static void start(service_state *service, size_t index, const service_request *request) {
    service_lease *lease = held_lease(service, index, request->lease);
    no_error error = {0};
    no_ticket ticket = {0};
    if (lease && lease->phase != LEASE_OPEN && lease->started && same_id(lease->start_request, request->request)) {
        /* The admitted START's reply may have been lost and the lease closed for it: the
         * holder's replay still learns the ticket, so it can observe the record settle. */
        send_reply(&service->connections[index], request, STATUS_EXISTING, error, NULL, lease->ticket);
        return;
    }
    const char *argv[NO_ARGUMENT_LIMIT + 1];
    size_t argc = 0;
    if (lease && lease->phase == LEASE_OPEN && owner_now() >= lease->expires_ns)
        service_close_lease(service, lease, CLOSE_EXPIRED);
    service_status status = start_admissible(service, index, request, lease, argv, &argc);
    const service_launch_policy *policy = status == STATUS_OK ? find_policy(service, lease->policy) : NULL;
    uint8_t capability[SERVICE_CAPABILITY_BYTES];
    bool nested = false;
    if (policy && !fresh_capability(policy, capability, &nested)) {
        status = STATUS_UNAVAILABLE;
        error = (no_error){NO_ERROR_UNAVAILABLE, errno, 11};
    } else if (policy) {
        no_validated_spec spec = {policy->executable, policy->cwd, argv, policy->env, argc, policy->envc,
            policy->payload_uid, policy->payload_gid, nested ? capability : NULL,
            nested ? service->policy->socket_gid : 0, service->policy->record_pids_max,
            service->policy->record_memory_max};
        no_submit_result result = submit(service, lease, request, &spec, &ticket, &error);
        status = result == NO_ACCEPTED ? STATUS_OK : result == NO_EXISTING ? STATUS_EXISTING : status_for(error.kind);
        if (result == NO_ACCEPTED || result == NO_EXISTING)
            lease->started = true, lease->start_request = request->request, lease->ticket = ticket;
        if (result == NO_ACCEPTED) issue_nested_grant(service, policy, ticket, nested ? capability : NULL);
    }
    explicit_bzero(capability, sizeof(capability));
    /* A lost START reply closes the lease; an admitted record stays core-owned. */
    if (!send_reply(&service->connections[index], request, status, error, NULL, ticket) &&
        lease && lease->phase == LEASE_OPEN) service_close_lease(service, lease, CLOSE_REPLY_LOST);
}

/* Relay frames move application bytes for a record admitted under the caller's
 * own open lease; the core checks that ownership. A reply that cannot be sent
 * loses bytes the client would never see again, so it closes the lease. */
static service_status relay_admissible(service_state *service, const service_lease *lease,
                                       const service_request *request) {
    if (!admitting(service)) return STATUS_UNAVAILABLE;
    if (!lease) return STATUS_REJECTED;
    if (lease->phase != LEASE_OPEN || owner_now() >= lease->expires_ns) return STATUS_CLOSED;
    return request->data_length > SERVICE_DATA_BYTES ? STATUS_MALFORMED : STATUS_OK;
}

static void relay(service_state *service, size_t index, const service_request *request) {
    service_lease *lease = held_lease(service, index, request->lease);
    no_error error = {0};
    service_status status = relay_admissible(service, lease, request);
    size_t length = 0;
    bool eof = false;
    service_reply reply = reply_for(request, status, error);
    if (status == STATUS_OK) {
        bool done = request->opcode == OP_WRITE ?
            owner_relay_write(service->runtime, lease->id, request->ticket, request->data, request->data_length,
                              &length, &error) :
            owner_relay_read(service->runtime, lease->id, request->ticket, reply.data, sizeof(reply.data),
                             &length, &eof, &error);
        reply.status = done ? STATUS_OK : status_for(error.kind);
        reply.error = error;
        reply.data_length = (uint32_t)length;
        reply.flags = eof ? REPLY_EOF : 0;
        reply.ticket = request->ticket;
    }
    if (!transmit(&service->connections[index], &reply) && lease && lease->phase == LEASE_OPEN)
        service_close_lease(service, lease, CLOSE_REPLY_LOST);
    explicit_bzero(reply.data, sizeof(reply.data));
}

/* Held by this connection in any phase: a client proves retirement after closing. */
static void observe(service_state *service, size_t index, const service_request *request) {
    service_lease *lease = held_lease(service, index, request->lease);
    no_error error = {0};
    no_report report = {0};
    service_reply reply = reply_for(request, STATUS_REJECTED, error);
    if (lease && owner_observe_for_lease(service->runtime, lease->id, request->ticket, &report, &error)) {
        reply.status = STATUS_OK;
        reply.ticket = request->ticket;
        reply.report_kind = report.kind;
        reply.start_kind = report.start.kind;
        if (report.kind == NO_REPORT_RETIRED) {
            reply.wait_kind = report.detail.retired.wait.kind;
            reply.wait_value = report.detail.retired.wait.value;
        }
    }
    reply.error = error;
    transmit(&service->connections[index], &reply);
}

/* Extends a held, open, unexpired lease by one lifetime, never past its maximum age. */
static void renew(service_state *service, size_t index, const service_request *request) {
    service_lease *lease = held_lease(service, index, request->lease);
    uint64_t now = owner_now();
    if (lease && lease->phase == LEASE_OPEN && now >= lease->expires_ns)
        service_close_lease(service, lease, CLOSE_EXPIRED);
    service_status status = !admitting(service) ? STATUS_UNAVAILABLE : !lease ? STATUS_REJECTED :
        lease->phase != LEASE_OPEN ? STATUS_CLOSED : STATUS_OK;
    if (status == STATUS_OK) {
        uint64_t limit = lease->opened_ns + service->policy->lease_max_age_ns;
        uint64_t wanted = now + service->policy->lease_lifetime_ns;
        lease->expires_ns = wanted < limit ? wanted : limit;
    }
    if (!send_reply(&service->connections[index], request, status, (no_error){0}, lease, (no_ticket){0}) &&
        lease && lease->phase == LEASE_OPEN) service_close_lease(service, lease, CLOSE_REPLY_LOST);
}

static void close_requested(service_state *service, size_t index, const service_request *request) {
    service_lease *lease = held_lease(service, index, request->lease);
    service_status status = !lease ? STATUS_REJECTED : lease->phase == LEASE_OPEN ? STATUS_OK : STATUS_CLOSED;
    if (lease) service_close_lease(service, lease, CLOSE_REQUESTED);
    send_reply(&service->connections[index], request, status, (no_error){0}, NULL, (no_ticket){0});
}

static void close_connection(service_state *service, size_t index, close_reason reason) {
    service_connection *connection = &service->connections[index];
    if (connection->phase != CONNECTION_OPEN) return;
    for (size_t i = 0; i < service->lease_count; ++i) {
        service_lease *lease = &service->leases[i];
        if (lease->connection == index && lease->connection_generation == connection->generation)
            service_close_lease(service, lease, reason);
    }
    bool clean = service_close_fd(&connection->socket);
    clean &= service_close_fd(&connection->connector.pidfd);
    if (!clean) service->close_uncertain = true;
    /* A slot whose close failed is never reused: its descriptor state stays sticky. */
    connection->phase = clean ? CONNECTION_EMPTY : CONNECTION_CLOSED;
}

static void dispatch(service_state *service, size_t index) {
    service_connection *connection = &service->connections[index];
    service_request request;
    received_packet packet;
    no_error error = {0};
    memset(&request, 0, sizeof(request));
    if (!packet_receive(connection->socket.number, &request, sizeof(request), MSG_DONTWAIT, &packet, &error)) {
        if (error.system_errno != EAGAIN && error.system_errno != EWOULDBLOCK)
            close_connection(service, index, CLOSE_DISCONNECT);
        return;
    }
    if (packet.bytes == 0) {
        if (!packet_release(&packet)) service->close_uncertain = true;
        close_connection(service, index, CLOSE_DISCONNECT);
        return;
    }
    if (!packet_authenticated(&packet, &connection->connector, 0)) {
        send_reply(connection, &request, STATUS_UNAUTHENTICATED, (no_error){0}, NULL, (no_ticket){0});
        if (!packet_release(&packet)) service->close_uncertain = true;
        close_connection(service, index, CLOSE_SENDER_MISMATCH);
        return;
    }
    if (packet.bytes != (ssize_t)sizeof(request) || request.magic != SERVICE_MAGIC ||
        request.version != SERVICE_VERSION) {
        send_reply(connection, &request, STATUS_MALFORMED, (no_error){0}, NULL, (no_ticket){0});
    } else if (request.opcode == OP_OPEN_TOP) open_top(service, index, &request);
    else if (request.opcode == OP_OPEN_CHILD) open_child(service, index, &request);
    else if (request.opcode == OP_START) start(service, index, &request);
    else if (request.opcode == OP_CLOSE) close_requested(service, index, &request);
    else if (request.opcode == OP_RENEW) renew(service, index, &request);
    else if (request.opcode == OP_WRITE || request.opcode == OP_READ) relay(service, index, &request);
    else if (request.opcode == OP_OBSERVE) observe(service, index, &request);
    else send_reply(connection, &request, STATUS_MALFORMED, (no_error){0}, NULL, (no_ticket){0});
    if (!packet_release(&packet)) service->close_uncertain = true;
}

static size_t account_connections(const service_state *service, size_t except, uint32_t uid) {
    size_t count = 0;
    for (size_t i = 0; i < SERVICE_CONNECTION_LIMIT; ++i)
        if (i != except && service->connections[i].phase == CONNECTION_OPEN &&
            service->connections[i].connector.credentials.uid == uid) ++count;
    return count;
}

/* Owns `number` from here on: a full table, an account over its share, or a socket of
 * the wrong kind closes it. */
static void adopt_connection(service_state *service, int number) {
    int type = 0;
    socklen_t length = sizeof(type);
    int flags = fcntl(number, F_GETFL);
    if (getsockopt(number, SOL_SOCKET, SO_TYPE, &type, &length) != 0 || type != SOCK_SEQPACKET || flags == -1 ||
        fcntl(number, F_SETFL, flags | O_NONBLOCK) != 0) {
        owned_fd refused = {FD_OWNED, number};
        note_close(service, &refused);
        return;
    }
    size_t index = SERVICE_CONNECTION_LIMIT;
    for (size_t i = 0; i < SERVICE_CONNECTION_LIMIT && index == SERVICE_CONNECTION_LIMIT; ++i)
        if (service->connections[i].phase == CONNECTION_EMPTY) index = i;
    if (index == SERVICE_CONNECTION_LIMIT) {
        owned_fd refused = {FD_OWNED, number};
        note_close(service, &refused);
        return;
    }
    service_connection *connection = &service->connections[index];
    uint64_t generation = connection->generation + 1;
    *connection = (service_connection){.phase = CONNECTION_OPEN, .generation = generation,
        .socket = {FD_OWNED, number}};
    no_error error = {0};
    if (!peer_identity_from_connection(&connection->connector, number, &error) ||
        !peer_enable_credentials(number, &error)) close_connection(service, index, CLOSE_FAILED_ISSUE);
    else if (account_connections(service, index, connection->connector.credentials.uid) >=
             service->policy->connections_per_account)
        close_connection(service, index, CLOSE_ACCOUNT_LIMIT);
}

/* One frame from the guardian channel: a verified client connection, from the guardian
 * process itself, for this epoch. Anything else, EOF included, is guardian loss. */
static bool guardian_message(service_state *service) {
    guardian_grant frame;
    received_packet packet;
    no_error error = {0};
    memset(&frame, 0, sizeof(frame));
    if (!packet_receive(service->guardian.number, &frame, sizeof(frame), MSG_DONTWAIT, &packet, &error))
        return error.system_errno == EAGAIN || error.system_errno == EWOULDBLOCK;
    bool authentic = packet.bytes == (ssize_t)sizeof(frame) && packet_authenticated(&packet, &service->guardian_peer, 1) &&
        frame.magic == SERVICE_MAGIC && frame.version == SERVICE_VERSION && frame.kind == GRANT_CONNECTION &&
        same_id(frame.epoch, service->epoch) && frame.generation == service->generation;
    if (authentic) {
        int number = packet.rights[0].number;
        packet.right_count = 0;
        adopt_connection(service, number);
    }
    if (!packet_release(&packet)) service->close_uncertain = true;
    return authentic;
}

#ifdef NO_ACCEPTANCE_BUILD
/* Acceptance only: the peer-evidence fixture listens itself instead of a guardian. */
static void accept_connection(service_state *service) {
    int number;
    do {
        number = accept4(service->listener.number, NULL, NULL, SOCK_CLOEXEC | SOCK_NONBLOCK);
    } while (number < 0 && errno == EINTR);
    if (number >= 0) adopt_connection(service, number);
}
#endif

/* Admission ends when the core closed it, the guardian died, or every lease
 * position of the epoch is spent with none open. The caller then drains and the
 * guardian grants a fresh epoch to a fresh service. */
/* No new START can succeed: every record slot is used, every lease position is spent,
 * or the client has spent its quota. */
static bool epoch_spent(service_state *service) {
    if (service->lease_count == SERVICE_LEASE_LIMIT || (service->runtime && owner_records_full(service->runtime)))
        return true;
    return positions_used(service, service->policy->clients[0].uid) >= service->policy->client_lease_quota;
}

static bool admission_ended(service_state *service) {
    bool guardian_gone = service->guardian_peer.pidfd.state == FD_OWNED && !peer_alive(&service->guardian_peer);
    if (guardian_gone || (service->runtime && !owner_admission_open(service->runtime))) return true;
    if (!epoch_spent(service)) return false;
    /* Spent and idle: drain so the guardian grants a fresh epoch. An open lease keeps it, and
     * so does an open connection, which may still be observing its helper settle. */
    for (size_t i = 0; i < service->lease_count; ++i) if (service->leases[i].phase == LEASE_OPEN) return false;
    for (size_t i = 0; i < SERVICE_CONNECTION_LIMIT; ++i)
        if (service->connections[i].phase == CONNECTION_OPEN) return false;
    return true;
}

/* Poll wakeups are hints. Deadlines, connector death and record settlement are
 * rescanned every turn so a lost notification cannot strand a lease. */
void service_settle(service_state *service) {
    uint64_t now = owner_now();
    for (size_t i = 0; i < service->lease_count; ++i)
        if (service->leases[i].phase == LEASE_OPEN && now >= service->leases[i].expires_ns)
            service_close_lease(service, &service->leases[i], CLOSE_EXPIRED);
    for (size_t i = 0; i < SERVICE_CONNECTION_LIMIT; ++i)
        if (service->connections[i].phase == CONNECTION_OPEN && !peer_alive(&service->connections[i].connector))
            close_connection(service, i, CLOSE_PEER_DEATH);
    if (service->runtime) no_runtime_maintain(service->runtime, (no_deadline){owner_now() + 1000000});
    authentication_owner_scan(&service->scopes);
    if (admitting(service) && admission_ended(service)) service->phase = BOOT_DRAINING;
}

#define SERVICE_FIXED_EVENTS 3 /* Listener, guardian channel, guardian pidfd. */

static int owned_or_ignored(const owned_fd *slot) { return slot->state == FD_OWNED ? slot->number : -1; }

service_result service_run_one(service_state *service, int timeout_ms) {
    if (!admitting(service)) return service->phase == BOOT_STICKY ? SERVICE_STICKY : SERVICE_PENDING;
    struct pollfd events[SERVICE_FIXED_EVENTS + 2 * SERVICE_CONNECTION_LIMIT];
    size_t owners[2 * SERVICE_CONNECTION_LIMIT];
    size_t count = 0;
    events[count++] = (struct pollfd){.fd = owned_or_ignored(&service->listener), .events = POLLIN};
    events[count++] = (struct pollfd){.fd = owned_or_ignored(&service->guardian), .events = POLLIN};
    events[count++] = (struct pollfd){.fd = owned_or_ignored(&service->guardian_peer.pidfd), .events = POLLIN};
    for (size_t i = 0; i < SERVICE_CONNECTION_LIMIT; ++i) {
        if (service->connections[i].phase != CONNECTION_OPEN) continue;
        owners[count - SERVICE_FIXED_EVENTS] = i;
        events[count++] = (struct pollfd){.fd = service->connections[i].socket.number, .events = POLLIN};
        owners[count - SERVICE_FIXED_EVENTS] = i;
        events[count++] = (struct pollfd){.fd = service->connections[i].connector.pidfd.number, .events = POLLIN};
    }
    int ready;
    do { ready = poll(events, count, timeout_ms); } while (ready < 0 && errno == EINTR);
    bool guardian_lost = ready > 0 && (events[2].revents ||
        (events[1].revents & POLLIN ? !guardian_message(service) : events[1].revents != 0));
    if (guardian_lost) {
        /* Guardian loss, by channel, by process exit or by a frame it did not send,
         * closes admission at once; the caller then drains. */
        service->phase = BOOT_DRAINING;
        return SERVICE_PENDING;
    }
    if (ready > 0) {
        for (size_t i = SERVICE_FIXED_EVENTS; i < count; i += 2) {
            size_t index = owners[i - SERVICE_FIXED_EVENTS];
            if (service->connections[index].phase != CONNECTION_OPEN) continue;
            if (events[i + 1].revents & POLLIN) close_connection(service, index, CLOSE_PEER_DEATH);
            else if (events[i].revents & POLLIN) dispatch(service, index);
            else if (events[i].revents & (POLLHUP | POLLERR | POLLNVAL))
                close_connection(service, index, CLOSE_DISCONNECT);
        }
#ifdef NO_ACCEPTANCE_BUILD
        if (events[0].revents & POLLIN) accept_connection(service);
#endif
    }
    service_settle(service);
    return SERVICE_RUNNING;
}

static bool scopes_quiescent(service_state *service) {
    for (size_t i = 0; i < service->lease_count; ++i) {
        authenticated_scope_slot *slot = &service->scopes.slots[i];
        if (atomic_load(&slot->borrowers) || !atomic_load(&slot->issuance_closed) || !slot->resources_settled)
            return false;
    }
    return true;
}

/* Stops admission, closes every lease, lets records settle and only then frees
 * core memory and the epoch descriptors. Pending keeps every owned resource. */
service_result service_drain(service_state *service, no_deadline deadline) {
    if (service->phase == BOOT_QUIESCENT) return SERVICE_CLEAN;
    if (service->phase != BOOT_STICKY) service->phase = BOOT_DRAINING;
    note_close(service, &service->listener);
    for (size_t i = 0; i < SERVICE_CONNECTION_LIMIT; ++i) close_connection(service, i, CLOSE_SHUTDOWN);
    for (size_t i = 0; i < service->lease_count; ++i) service_close_lease(service, &service->leases[i], CLOSE_SHUTDOWN);
    if (service->runtime) {
        no_error error;
        if (!no_runtime_shutdown(&service->runtime, deadline, &error)) {
            if (!service->first_error.kind) service->first_error = error;
            return SERVICE_PENDING;
        }
    }
    authentication_owner_scan(&service->scopes);
    if (!scopes_quiescent(service)) {
        service->phase = BOOT_STICKY;
        return SERVICE_STICKY;
    }
    note_close(service, &service->epoch_anchor);
    note_close(service, &service->guardian);
    note_close(service, &service->guardian_peer.pidfd);
    service->phase = service->close_uncertain ? BOOT_STICKY : BOOT_QUIESCENT;
    return service->close_uncertain ? SERVICE_STICKY : SERVICE_CLEAN;
}

/* Frees only a service that owns nothing: never bootstrapped or fully drained. */
bool service_free(service_state **address) {
    service_state *service = *address;
    if (!service || (service->phase != BOOT_QUIESCENT && service->phase != BOOT_EMPTY) || service->runtime ||
        service->guardian.state == FD_OWNED || service->listener.state == FD_OWNED ||
        service->epoch_anchor.state == FD_OWNED || service->guardian_peer.pidfd.state == FD_OWNED) return false;
    free(service);
    *address = NULL;
    return true;
}

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
