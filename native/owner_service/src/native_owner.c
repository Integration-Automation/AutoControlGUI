#define _GNU_SOURCE
#ifdef NO_ACCEPTANCE_BUILD
#include "owner_fixture.h"
#endif
#include "owner_internal.h"
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <limits.h>
#include <stdio.h>

static unsigned allocation_to_fail;
static void *owner_allocate(size_t count, size_t size) {
    if (allocation_to_fail && --allocation_to_fail == 0) return NULL;
    return calloc(count, size);
}

uint64_t owner_now(void) {
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    return (uint64_t)value.tv_sec * 1000000000ULL + (uint64_t)value.tv_nsec;
}

void owner_pause(void) {
    struct timespec delay = { .tv_nsec = 1000000 };
    nanosleep(&delay, NULL);
}

static bool same_id(no_id a, no_id b) { return a.high == b.high && a.low == b.low; }

bool scope_retain(scope_reference existing, scope_reference *copy) {
    if (!existing.slot) return false;
    unsigned count = atomic_load_explicit(&existing.slot->borrowers, memory_order_relaxed);
    while (count && count != UINT_MAX) {
        if (atomic_compare_exchange_weak_explicit(&existing.slot->borrowers, &count, count + 1,
                memory_order_relaxed, memory_order_relaxed)) {
            copy->slot = existing.slot;
            return true;
        }
    }
    return false;
}

void scope_release(scope_reference *reference) {
    authenticated_scope_slot *slot = reference->slot;
    reference->slot = NULL;
    if (slot) atomic_fetch_sub_explicit(&slot->borrowers, 1, memory_order_release);
}

void authentication_owner_scan(scope_owner *owner) {
    if (owner->count > NO_RECORD_LIMIT) return;
    for (size_t i = 0; i < owner->count; ++i) {
        authenticated_scope_slot *slot = &owner->slots[i];
        if (!atomic_load_explicit(&slot->issuance_closed, memory_order_acquire) ||
            atomic_load_explicit(&slot->borrowers, memory_order_acquire)) continue;
        owned_fd *resources[] = {&slot->peer, &slot->epoch_anchor};
        bool clean = true;
        for (size_t j = 0; j < sizeof(resources) / sizeof(resources[0]); ++j) {
            owned_fd *resource = resources[j];
            if (resource->state == FD_OWNED) {
                int number = resource->number;
                resource->number = -1;
                resource->state = close(number) == 0 ? FD_CLOSED : FD_CLOSE_ERROR;
            }
            if (resource->state == FD_CLOSE_ERROR) clean = false;
        }
        slot->resources_settled = clean;
    }
}

bool owner_child_bit(size_t slot, uint32_t *bit) {
    if (slot >= NO_RECORD_LIMIT) return false;
    *bit = UINT32_C(1) << slot;
    return true;
}

void owner_fence_locked(owner_record *record) {
    no_runtime *runtime = record->runtime;
    size_t root = (size_t)(record - runtime->records);
    for (size_t i = root; i < runtime->count; ++i) {
        size_t ancestor = i;
        for (size_t depth = 0; depth < NO_RECORD_LIMIT; ++depth) {
            if (ancestor == root) {
                runtime->records[i].admission = ADMISSION_FENCED;
                atomic_store(&runtime->records[i].revoked, true);
                break;
            }
            owner_record *current = &runtime->records[ancestor];
            if (current->parent_is_epoch || current->parent_slot >= ancestor) break;
            ancestor = current->parent_slot;
        }
    }
}

void owner_publish_anchor_locked(owner_record *record) {
    if (record->admission == ADMISSION_OPEN && record->anchor.state == ANCHOR_UNPUBLISHED &&
        record->scope.container.descriptor.state == FD_OWNED) {
        record->anchor.borrowed_directory = record->scope.container.descriptor.number;
        record->anchor.state = ANCHOR_READY;
    }
}

bool owner_invalidate_anchor_locked(owner_record *record) {
    if (record->admission != ADMISSION_FENCED || record->unsettled_children) return false;
    record->anchor.state = ANCHOR_INVALIDATED;
    record->anchor.borrowed_directory = -1;
    return true;
}

owner_record *owner_find_record(no_runtime *runtime, no_ticket ticket) {
    if (!same_id(ticket.service_epoch, runtime->epoch) || ticket.record.high != 0 ||
        ticket.record.low == 0 || ticket.record.low > runtime->count) return NULL;
    return &runtime->records[ticket.record.low - 1];
}

no_runtime *no_runtime_create(const no_boot_policy *policy, no_error *error) {
    *error = (no_error){0};
    if (!policy || policy->capacity == 0 || policy->capacity > NO_RECORD_LIMIT) {
        error->kind = NO_ERROR_ARGUMENT;
        return NULL;
    }
    no_runtime *runtime = owner_allocate(1, sizeof(*runtime));
    if (!runtime) { error->kind = NO_ERROR_ALLOCATION; return NULL; }
    runtime->records = owner_allocate(policy->capacity, sizeof(*runtime->records));
    if (!runtime->records) { free(runtime); error->kind = NO_ERROR_ALLOCATION; return NULL; }
    int rc = pthread_mutex_init(&runtime->registry, NULL);
    if (rc) {
        free(runtime->records); free(runtime);
        error->kind = NO_ERROR_ALLOCATION; error->system_errno = rc; return NULL;
    }
    runtime->capacity = policy->capacity;
    runtime->epoch = policy->epoch;
    for (size_t i = 0; i < runtime->capacity; ++i) {
        rc = pthread_mutex_init(&runtime->records[i].report_lock, NULL);
        if (!rc) {
            rc = pthread_mutex_init(&runtime->records[i].relay.lock, NULL);
            if (!rc) continue;
            pthread_mutex_destroy(&runtime->records[i].report_lock);
        }
        while (i) {
            pthread_mutex_destroy(&runtime->records[--i].report_lock);
            pthread_mutex_destroy(&runtime->records[i].relay.lock);
        }
        pthread_mutex_destroy(&runtime->registry);
        free(runtime->records); free(runtime);
        error->kind = NO_ERROR_ALLOCATION; error->system_errno = rc;
        return NULL;
    }
    return runtime;
}

void owner_set_error(owner_record *record, no_error_kind kind, int error) {
    if (record->proof.error.kind == NO_ERROR_NONE)
        record->proof.error = (no_error){ .kind = kind, .system_errno = error };
}

void owner_close_slot(owner_record *record, owned_fd *slot) {
    if (slot->state != FD_OWNED) return;
    int number = slot->number;
    if (slot == &record->pidfd) atomic_store(&record->closed_pidfd, number);
    slot->number = -1;
    slot->state = FD_CLOSED;
    atomic_fetch_sub(&record->owned_count, 1);
    atomic_fetch_add(&record->close_attempts, 1);
    int rc = close(number);
    int error = errno;
    if (record->options.fail_close && slot == &record->pidfd) { rc = -1; error = EINTR; }
    if (rc == -1) {
        slot->state = FD_CLOSE_ERROR;
        owner_set_error(record, NO_ERROR_CLEANUP, error);
    }
}

void owner_publish(owner_record *record, no_pending_reason reason, no_child_state child) {
    pthread_mutex_lock(&record->report_lock);
    record->report.kind = NO_REPORT_PENDING;
    record->report.detail.pending = (no_pending){ .reason = reason, .child = child,
        .wait = record->proof.wait, .revoked = atomic_load(&record->revoked) };
    pthread_mutex_unlock(&record->report_lock);
}

bool owner_lease_closed(no_runtime *runtime, no_id lease) {
    for (size_t i = 0; i < runtime->revoked_lease_count; ++i)
        if (same_id(runtime->revoked_leases[i], lease)) return true;
    return false;
}

bool owner_lease_registered(no_runtime *runtime, no_id lease) {
    for (size_t i = 0; i < runtime->registered_lease_count; ++i)
        if (same_id(runtime->registered_leases[i], lease)) return true;
    return false;
}

#ifdef NO_ACCEPTANCE_BUILD
static no_submit_result existing(no_runtime *runtime, no_request_key key, const char *executable,
                                 no_ticket *ticket, no_error *error) {
    for (size_t i = 0; i < runtime->count; ++i) {
        owner_record *record = &runtime->records[i];
        if (!same_id(record->key.lease, key.lease) || !same_id(record->key.request, key.request)) continue;
        if (strcmp(executable, record->executable)) {
            error->kind = NO_ERROR_KEY_CONFLICT; return NO_REJECTED;
        }
        *ticket = record->ticket;
        return NO_EXISTING;
    }
    return NO_ACCEPTED;
}
#endif

static void record_init(owner_record *record, no_runtime *runtime, no_request_key key,
                        const char *executable, fixture_options options) {
    record->runtime = runtime;
    record->key = key;
    record->options = options;
    record->relay_enabled = options.relay;
    record->parent_is_epoch = true;
    record->ticket = (no_ticket){runtime->epoch, {0, runtime->count + 1}};
    memcpy(record->executable, executable, strlen(executable) + 1);
    record->registered = true;
    record->proof.wait.kind = NO_WAIT_PENDING;
    atomic_init(&record->revoked, false); atomic_init(&record->finished, false);
    atomic_init(&record->before_call, false); atomic_init(&record->after_success, false);
    atomic_init(&record->release_before, !options.hold_before_call);
    atomic_init(&record->release_after, !options.hold_after_success);
    atomic_init(&record->launch_attempts, 0); atomic_init(&record->owned_count, 0);
    atomic_init(&record->close_attempts, 0); atomic_init(&record->scratch_diagnostic, -1);
    atomic_init(&record->creation_returned, false);
    atomic_init(&record->release_start, !options.hold_start_publication);
    atomic_init(&record->failed_call, false); atomic_init(&record->release_failure, !options.admission_probe);
    atomic_init(&record->closed_pidfd, -1); atomic_init(&record->successful_joins, 0);
    atomic_init(&record->native_success, false); atomic_init(&record->pidfd_adopted, false);
    atomic_init(&record->release_adoption, !options.hold_adoption);
    atomic_init(&record->failure_write_attempt, false);
    atomic_init(&record->nested_delivered, false);
    record->start = THREAD_STARTING;
    record->report.kind = NO_REPORT_PENDING;
    record->report.detail.pending.reason = NO_PENDING_LAUNCH;
}

#ifdef NO_ACCEPTANCE_BUILD
no_submit_result owner_fixture_submit(no_runtime *runtime, no_request_key key, const char *executable,
                                      fixture_options options, no_ticket *ticket, no_error *error) {
    *error = (no_error){0};
    if (!executable || strnlen(executable, NO_PATH_LIMIT) >= NO_PATH_LIMIT || executable[0] != '/') {
        error->kind = NO_ERROR_ARGUMENT; return NO_REJECTED;
    }
    pthread_mutex_lock(&runtime->registry);
    no_submit_result result = existing(runtime, key, executable, ticket, error);
    if (result != NO_ACCEPTED) { pthread_mutex_unlock(&runtime->registry); return result; }
    if (runtime->admission_closed || !owner_lease_registered(runtime, key.lease) || owner_lease_closed(runtime, key.lease))
        error->kind = NO_ERROR_ADMISSION_CLOSED;
    else if (runtime->count == runtime->capacity) error->kind = NO_ERROR_CAPACITY;
    if (error->kind) { pthread_mutex_unlock(&runtime->registry); return NO_REJECTED; }
    owner_record *record = &runtime->records[runtime->count];
    record_init(record, runtime, key, executable, options);
    if (options.nested_bootstrap) {
        record->delivery.wanted = true;
        for (size_t i = 0; i < NO_CAPABILITY_BYTES; ++i) record->delivery.capability[i] = (uint8_t)(7 * i + 1);
    }
    ++runtime->count;
    *ticket = record->ticket;
    pthread_mutex_unlock(&runtime->registry);
    pthread_t created_thread;
    int rc = options.fail_thread ? EAGAIN : pthread_create(&created_thread, NULL, owner_worker, record);
    atomic_store(&record->creation_returned, true);
    uint64_t hold_deadline = owner_now() + 5000000000ULL;
    while (!atomic_load(&record->release_start) && owner_now() < hold_deadline) owner_pause();
    pthread_mutex_lock(&runtime->registry);
    record->thread_created = rc == 0;
    if (rc == 0) record->thread = created_thread;
    record->start = rc == 0 ? THREAD_STARTED : THREAD_NO_THREAD;
    record->join = JOIN_ELIGIBLE;
    if (rc) {
        owner_fence_locked(record);
        record->proof = (finished_proof){ .kind = PROOF_DIRECT_FIXTURE, .no_child = true,
            .io_settled = true, .wait = {NO_WAIT_NOT_APPLICABLE, 0} };
        atomic_store(&record->failure_write_attempt, true);
        pthread_mutex_lock(&record->report_lock);
        record->report.start = (no_start_outcome){NO_START_FAILED_WITHOUT_CHILD,
            {NO_ERROR_THREAD_START, rc, 0}};
        pthread_mutex_unlock(&record->report_lock);
        atomic_store_explicit(&record->finished, true, memory_order_release);
    }
    pthread_mutex_unlock(&runtime->registry);
    return NO_ACCEPTED;
}
#endif

static bool same_scope(scope_identity a, scope_identity b) {
    return same_id(a.identity, b.identity) && same_id(a.epoch, b.epoch) &&
        same_id(a.lease, b.lease) && a.parent_is_epoch == b.parent_is_epoch &&
        same_id(a.permitted_parent.service_epoch, b.permitted_parent.service_epoch) &&
        same_id(a.permitted_parent.record, b.permitted_parent.record);
}

static immutable_spec_arena *copy_spec(const no_validated_spec *input, no_error *error) {
    if (!input || !input->executable || !input->cwd || input->executable[0] != '/' ||
        input->cwd[0] != '/' || strnlen(input->executable, NO_PATH_LIMIT) == NO_PATH_LIMIT ||
        strnlen(input->cwd, NO_PATH_LIMIT) == NO_PATH_LIMIT || !input->argc ||
        input->argc > NO_ARGUMENT_LIMIT || input->envc > NO_ARGUMENT_LIMIT ||
        !input->argv || (input->envc && !input->env)) {
        error->kind = NO_ERROR_ARGUMENT; return NULL;
    }
    immutable_spec_arena *copy = owner_allocate(1, sizeof(*copy));
    if (!copy) { error->kind = NO_ERROR_ALLOCATION; return NULL; }
    strcpy(copy->executable, input->executable); strcpy(copy->cwd, input->cwd);
    copy->argc = input->argc; copy->envc = input->envc;
    copy->uid = input->uid; copy->gid = input->gid; copy->socket_gid = input->socket_gid;
    if (input->nested_capability) {
        copy->delivery.wanted = true;
        memcpy(copy->delivery.capability, input->nested_capability, NO_CAPABILITY_BYTES);
    }
    for (size_t i = 0; i < input->argc + input->envc; ++i) {
        const char *source = i < input->argc ? input->argv[i] : input->env[i - input->argc];
        size_t available = NO_SPEC_BYTES - copy->bytes;
        size_t length = source ? strnlen(source, available) : available;
        if (length == available) { free(copy); error->kind = NO_ERROR_ARGUMENT; return NULL; }
        char *destination = copy->storage + copy->bytes;
        memcpy(destination, source, length + 1);
        if (i < input->argc) copy->argv[i] = destination;
        else copy->env[i - input->argc] = destination;
        copy->bytes += length + 1;
    }
    return copy;
}

static bool same_spec(const immutable_spec_arena *a, const immutable_spec_arena *b) {
    if (!a || !b || a->argc != b->argc || a->envc != b->envc || a->bytes != b->bytes ||
        a->uid != b->uid || a->gid != b->gid || a->socket_gid != b->socket_gid ||
        a->delivery.wanted != b->delivery.wanted ||
        strcmp(a->executable, b->executable) ||
        strcmp(a->cwd, b->cwd)) return false;
    return memcmp(a->storage, b->storage, a->bytes) == 0;
}

static no_submit_result admit_protected_locked(no_runtime *runtime, scope_reference *scope,
        no_request_key key, immutable_spec_arena **spec, owner_record **accepted,
        no_ticket *ticket, no_error *error) {
    scope_identity identity = scope->slot->identity;
    for (size_t i = 0; i < runtime->count; ++i) {
        owner_record *record = &runtime->records[i];
        if (!same_id(record->key.lease, key.lease) || !same_id(record->key.request, key.request)) continue;
        if (record->profile != PROFILE_PROTECTED || !same_scope(record->immutable_scope_identity, identity) ||
            !same_spec(record->spec, *spec)) {
            error->kind = NO_ERROR_KEY_CONFLICT; return NO_REJECTED;
        }
        *ticket = record->ticket; return NO_EXISTING;
    }
    if (!same_id(identity.epoch, runtime->epoch) || !same_id(identity.lease, key.lease))
        error->kind = NO_ERROR_ARGUMENT;
    else if (runtime->admission_closed || owner_lease_closed(runtime, key.lease) ||
             !owner_lease_registered(runtime, key.lease) || atomic_load(&scope->slot->issuance_closed))
        error->kind = NO_ERROR_ADMISSION_CLOSED;
    else if (runtime->count == runtime->capacity) error->kind = NO_ERROR_CAPACITY;
    owner_record *parent = NULL;
    if (!error->kind && !identity.parent_is_epoch) {
        parent = owner_find_record(runtime, identity.permitted_parent);
        if (!parent || parent->profile != PROFILE_PROTECTED) error->kind = NO_ERROR_ARGUMENT;
        else {
            owner_record *ancestor = parent;
            for (size_t depth = 0; depth < NO_RECORD_LIMIT; ++depth) {
                if (ancestor->admission != ADMISSION_OPEN) { error->kind = NO_ERROR_ADMISSION_CLOSED; break; }
                if (ancestor->parent_is_epoch) break;
                size_t index = (size_t)(ancestor - runtime->records);
                if (ancestor->parent_slot >= index) { error->kind = NO_ERROR_NATIVE_CONTRACT; break; }
                ancestor = &runtime->records[ancestor->parent_slot];
            }
            if (!error->kind && parent->anchor.state != ANCHOR_READY) error->kind = NO_ERROR_UNAVAILABLE;
        }
    }
    if (error->kind) return NO_REJECTED;
    owner_record *record = &runtime->records[runtime->count];
    char component[NO_COMPONENT_LIMIT];
    int length = snprintf(component, sizeof(component), "r-%016llx-%016llx-%02zu",
        (unsigned long long)runtime->epoch.high, (unsigned long long)runtime->epoch.low, runtime->count);
    if (length < 0 || (size_t)length >= sizeof(component)) {
        error->kind = NO_ERROR_ARGUMENT; return NO_REJECTED;
    }
    uint32_t bit;
    if (!owner_child_bit(runtime->count, &bit)) { error->kind = NO_ERROR_CAPACITY; return NO_REJECTED; }
    record_init(record, runtime, key, (*spec)->executable, (fixture_options){0});
    record->profile = PROFILE_PROTECTED;
    record->relay_enabled = true;
    record->parent_is_epoch = identity.parent_is_epoch;
    if (parent) record->parent_slot = (size_t)(parent - runtime->records);
    record->immutable_scope_identity = identity;
    record->retained_scope = *scope; scope->slot = NULL;
    record->spec = *spec; *spec = NULL;
    record->delivery = record->spec->delivery;
    memset(record->spec->delivery.capability, 0, NO_CAPABILITY_BYTES);
    record->planned_protected_tree = (no_id){runtime->epoch.high ^ runtime->epoch.low, runtime->count + 1};
    strcpy(record->scope.container.component, component);
    strcpy(record->scope.payload.component, "payload");
    if (parent) parent->unsettled_children |= bit;
    ++runtime->count;
    *ticket = record->ticket; *accepted = record;
    return NO_ACCEPTED;
}

/* The production gate. Only the protected acceptance build, run against an epoch a
 * provisioned guardian granted, opens it; every other build refuses protected submits. */
static bool authenticated_bootstrap_unimplemented(void) {
#ifdef NO_PROTECTED_ACCEPTANCE
    return false;
#else
    return true;
#endif
}

static no_submit_result owner_protected_submit(no_runtime *runtime, const no_authenticated_scope *scope,
        no_request_key key, const no_validated_spec *spec, no_ticket *ticket, no_error *error) {
    *error = (no_error){0};
    if (!runtime || !scope || !ticket || authenticated_bootstrap_unimplemented()) {
        error->kind = NO_ERROR_UNAVAILABLE; return NO_REJECTED;
    }
    scope_reference prepared = {0};
    if (!scope_retain(scope->reference, &prepared)) { error->kind = NO_ERROR_ARGUMENT; return NO_REJECTED; }
    immutable_spec_arena *copy = copy_spec(spec, error);
    if (!copy) { scope_release(&prepared); return NO_REJECTED; }
    owner_record *record = NULL;
    pthread_mutex_lock(&runtime->registry);
    no_submit_result result = admit_protected_locked(runtime, &prepared, key, &copy, &record, ticket, error);
    pthread_mutex_unlock(&runtime->registry);
    scope_release(&prepared); free(copy);
    if (result != NO_ACCEPTED) return result;
    pthread_t thread;
    int rc = pthread_create(&thread, NULL, owner_protected_worker, record);
    pthread_mutex_lock(&runtime->registry);
    record->thread_created = rc == 0;
    if (!rc) record->thread = thread;
    record->start = rc ? THREAD_NO_THREAD : THREAD_STARTED;
    record->join = JOIN_ELIGIBLE;
    if (rc) {
        owner_fence_locked(record);
        record->proof = (finished_proof){.kind = PROOF_WITHOUT_SCOPE, .no_child = true,
            .io_settled = true, .wait = {NO_WAIT_NOT_APPLICABLE, 0},
            .detail.without_scope = {NO_WORKER_CREATED}};
        pthread_mutex_lock(&record->report_lock);
        record->report.start = (no_start_outcome){NO_START_FAILED_WITHOUT_CHILD, {NO_ERROR_THREAD_START, rc, 0}};
        pthread_mutex_unlock(&record->report_lock);
        atomic_store_explicit(&record->finished, true, memory_order_release);
    }
    pthread_mutex_unlock(&runtime->registry);
    return result;
}

no_submit_result no_submit(no_runtime *runtime, const no_authenticated_scope *scope,
                           no_request_key key, const no_validated_spec *spec,
                           no_ticket *ticket, no_error *error) {
    return owner_protected_submit(runtime, scope, key, spec, ticket, error);
}

bool no_revoke(no_runtime *runtime, no_ticket ticket) {
    pthread_mutex_lock(&runtime->registry);
    owner_record *record = owner_find_record(runtime, ticket);
    if (record) owner_fence_locked(record);
    pthread_mutex_unlock(&runtime->registry);
    return record != NULL;
}

void no_revoke_lease(no_runtime *runtime, no_id lease) {
    pthread_mutex_lock(&runtime->registry);
    if (!owner_lease_registered(runtime, lease)) { pthread_mutex_unlock(&runtime->registry); return; }
    if (!owner_lease_closed(runtime, lease)) {
        if (runtime->revoked_lease_count == NO_RECORD_LIMIT) runtime->admission_closed = true;
        else runtime->revoked_leases[runtime->revoked_lease_count++] = lease;
    }
    for (size_t i = 0; i < runtime->count; ++i)
        if (same_id(runtime->records[i].key.lease, lease)) owner_fence_locked(&runtime->records[i]);
    pthread_mutex_unlock(&runtime->registry);
}

no_report no_observe(no_runtime *runtime, no_ticket ticket, no_deadline deadline) {
    no_report report = {.kind = NO_REPORT_PENDING,
        .detail.pending = {.reason = NO_PENDING_SNAPSHOT}};
    do {
        if (pthread_mutex_trylock(&runtime->registry) != 0) { owner_pause(); continue; }
        owner_record *record = owner_find_record(runtime, ticket);
        pthread_mutex_unlock(&runtime->registry);
        if (!record) return (no_report){.kind = NO_REPORT_UNKNOWN_TICKET};
        if (pthread_mutex_trylock(&record->report_lock) == 0) {
            report = record->report;
            pthread_mutex_unlock(&record->report_lock);
            return report;
        }
        owner_pause();
    } while (owner_now() < deadline.monotonic_ns);
    return report;
}

static bool maintenance_build_final_report(const owner_record *record, no_report *report) {
    const finished_proof *proof = &record->proof;
    if (record->join != JOIN_DONE || record->start == THREAD_STARTING || proof->error.kind ||
        !proof->io_settled || atomic_load(&record->owned_count) ||
        proof->child_dead == proof->no_child) return false;
    if (proof->no_child && (proof->wait.kind != NO_WAIT_NOT_APPLICABLE ||
        report->start.kind != NO_START_FAILED_WITHOUT_CHILD)) return false;
    if (proof->child_dead &&
        (proof->wait.kind != NO_WAIT_EXITED && proof->wait.kind != NO_WAIT_SIGNALLED &&
         proof->wait.kind != NO_WAIT_STATUS_UNAVAILABLE)) return false;
    if (proof->child_dead && report->start.kind != NO_START_CHILD_CREATED &&
        report->start.kind != NO_START_EXEC_FAILED && report->start.kind != NO_START_READY) return false;
    if (record->profile != PROFILE_PROTECTED || record->admission != ADMISSION_FENCED ||
        record->unsettled_children || record->anchor.state == ANCHOR_READY) return false;
    if (proof->kind == PROOF_WITHOUT_SCOPE) {
        bool execution =
            (proof->detail.without_scope.execution == NO_WORKER_CREATED &&
             record->start == THREAD_NO_THREAD && !record->thread_created) ||
            (proof->detail.without_scope.execution == WORKER_JOIN_REQUIRED &&
             record->start == THREAD_STARTED && record->thread_created);
        if (!execution || !proof->no_child || proof->child_dead ||
            proof->wait.kind != NO_WAIT_NOT_APPLICABLE ||
            record->scope.container.state != DIR_PLANNED || record->scope.payload.state != DIR_PLANNED ||
            report->start.kind != NO_START_FAILED_WITHOUT_CHILD) return false;
        report->kind = NO_REPORT_SETTLED_WITHOUT_SCOPE;
        report->detail.without_scope = (no_no_scope_receipt){record->ticket.service_epoch};
        return true;
    }
    if (proof->kind != PROOF_CONTAINED || record->start != THREAD_STARTED || !record->thread_created)
        return false;
    const contained_evidence *evidence = &proof->detail.contained;
    if (evidence->container != CLEAN_EXACT_REMOVAL ||
        (evidence->payload != CLEAN_NEVER_CREATED && evidence->payload != CLEAN_EXACT_REMOVAL) ||
        evidence->emptiness != EMPTY_POPULATION_OBSERVED || !evidence->admission_fenced ||
        !evidence->children_settled || !evidence->launch_resolved || !evidence->descriptors_clean ||
        !same_id(evidence->protected_tree, record->planned_protected_tree) ||
        record->scope.container.state != DIR_REMOVED ||
        (record->scope.payload.state != DIR_PLANNED && record->scope.payload.state != DIR_REMOVED)) return false;
    report->kind = NO_REPORT_RETIRED;
    report->detail.retired = (no_retired_receipt){proof->wait, evidence->protected_tree, record->ticket.service_epoch};
    return true;
}

static void publish_joined(owner_record *record) {
    pthread_mutex_lock(&record->report_lock);
    if (record->proof.error.kind) {
        record->report.kind = NO_REPORT_STICKY_UNKNOWN;
        record->report.detail.unknown = (no_sticky_unknown){.first_error = record->proof.error,
            .child = record->proof.child_dead ? NO_CHILD_DEAD : NO_CHILD_NEVER_CREATED};
    } else if (record->profile == PROFILE_DIRECT_FIXTURE) {
        record->settled = record->proof.kind == PROOF_DIRECT_FIXTURE && record->proof.io_settled &&
            (record->proof.child_dead || record->proof.no_child);
    } else {
        no_report final = record->report;
        if (maintenance_build_final_report(record, &final)) {
            record->report = final;
            record->settled = true;
        } else {
            record->report.kind = NO_REPORT_STICKY_UNKNOWN;
            record->report.detail.unknown = (no_sticky_unknown){
                .first_error = {NO_ERROR_NATIVE_CONTRACT, EPROTO, 0},
                .child = record->proof.child_dead ? NO_CHILD_DEAD : NO_CHILD_NEVER_CREATED};
        }
    }
    pthread_mutex_unlock(&record->report_lock);
    if (record->settled && record->profile == PROFILE_PROTECTED) {
        if (!record->parent_is_epoch) {
            uint32_t bit;
            if (owner_child_bit((size_t)(record - record->runtime->records), &bit))
                record->runtime->records[record->parent_slot].unsettled_children &= ~bit;
        }
        scope_release(&record->retained_scope);
    }
}

void no_runtime_maintain(no_runtime *runtime, no_deadline deadline) {
    for (size_t i = 0; i < runtime->capacity && owner_now() < deadline.monotonic_ns; ++i) {
        if (pthread_mutex_trylock(&runtime->registry) != 0) return;
        if (i >= runtime->count) { pthread_mutex_unlock(&runtime->registry); break; }
        owner_record *record = &runtime->records[i];
        bool claim = record->start != THREAD_STARTING && record->join == JOIN_ELIGIBLE &&
            atomic_load_explicit(&record->finished, memory_order_acquire);
        if (claim) record->join = JOIN_CLAIMED;
        pthread_mutex_unlock(&runtime->registry);
        if (!claim) continue;
        int rc = record->thread_created ? pthread_tryjoin_np(record->thread, NULL) : 0;
        pthread_mutex_lock(&runtime->registry);
        record->join = rc == 0 ? JOIN_DONE : (rc == EBUSY ? JOIN_ELIGIBLE : JOIN_FAILED);
        if (rc == 0 && record->thread_created) atomic_fetch_add(&record->successful_joins, 1);
        if (rc != 0 && rc != EBUSY) {
            runtime->admission_closed = true;
            owner_fence_locked(record);
            pthread_mutex_lock(&record->report_lock);
            record->report.kind = NO_REPORT_STICKY_UNKNOWN;
            record->report.detail.unknown = (no_sticky_unknown){
                .first_error = {NO_ERROR_CLEANUP, rc, 0}, .cleanup_still_running = true,
                .child = record->proof.child_dead ? NO_CHILD_DEAD : NO_CHILD_NEVER_CREATED};
            pthread_mutex_unlock(&record->report_lock);
        }
        if (rc == 0) publish_joined(record);
        pthread_mutex_unlock(&runtime->registry);
    }
}

bool no_runtime_shutdown(no_runtime **address, no_deadline deadline, no_error *error) {
    no_runtime *runtime = *address;
    *error = (no_error){0};
    pthread_mutex_lock(&runtime->registry);
    runtime->admission_closed = true;
    for (size_t i = 0; i < runtime->count; ++i) owner_fence_locked(&runtime->records[i]);
    pthread_mutex_unlock(&runtime->registry);
    bool complete;
    do {
        no_runtime_maintain(runtime, deadline);
        complete = true;
        for (size_t i = 0; i < runtime->count; ++i) complete &= runtime->records[i].settled;
        if (complete) break;
        owner_pause();
    } while (owner_now() < deadline.monotonic_ns);
    if (!complete) { error->kind = NO_ERROR_CLEANUP; return false; }
    for (size_t i = 0; i < runtime->capacity; ++i) {
        free(runtime->records[i].spec);
        pthread_mutex_destroy(&runtime->records[i].report_lock);
        pthread_mutex_destroy(&runtime->records[i].relay.lock);
    }
    pthread_mutex_destroy(&runtime->registry);
    free(runtime->records); free(runtime); *address = NULL;
    return true;
}

#ifdef NO_ACCEPTANCE_BUILD
bool fixture_allocation_failure(unsigned allocation, no_error *error) {
    no_boot_policy policy = {.capacity = 2, .epoch = {135, 1}};
    allocation_to_fail = allocation;
    no_runtime *runtime = no_runtime_create(&policy, error);
    allocation_to_fail = 0;
    if (runtime) no_runtime_shutdown(&runtime, (no_deadline){owner_now() + 10000000}, error);
    return runtime == NULL && error->kind == NO_ERROR_ALLOCATION;
}

no_runtime *fixture_runtime(size_t capacity) {
    no_boot_policy policy = {.capacity = capacity, .epoch = {135, 1}};
    no_error error;
    no_runtime *runtime = no_runtime_create(&policy, &error);
    if (runtime) {
        runtime->registered_leases[0] = (no_id){0, 1};
        runtime->registered_leases[1] = (no_id){0, 2};
        runtime->registered_lease_count = 2;
    }
    return runtime;
}

no_submit_result fixture_submit(no_runtime *runtime, unsigned key, const char *executable,
                                unsigned flags, no_ticket *ticket, no_error *error) {
    fixture_options options = {.hold_before_call = (flags & FIXTURE_HOLD_BEFORE) != 0,
        .hold_after_success = (flags & FIXTURE_HOLD_AFTER) != 0,
        .fail_thread = (flags & FIXTURE_FAIL_THREAD) != 0,
        .fail_close = (flags & FIXTURE_FAIL_CLOSE) != 0,
        .hold_start_publication = (flags & FIXTURE_HOLD_START) != 0,
        .admission_probe = (flags & FIXTURE_ADMISSION_PROBE) != 0,
        .child_hold = (flags & FIXTURE_CHILD_HOLD) != 0,
        .fail_child_setup = (flags & FIXTURE_FAIL_CHILD_SETUP) != 0,
        .hold_adoption = (flags & FIXTURE_HOLD_ADOPTION) != 0,
        .nested_bootstrap = (flags & FIXTURE_NESTED_BOOTSTRAP) != 0,
        .relay = (flags & FIXTURE_RELAY) != 0};
    return owner_fixture_submit(runtime, (no_request_key){{0, 1}, {0, key}}, executable,
                                options, ticket, error);
}

bool fixture_relay_lease(no_runtime *runtime, no_ticket ticket, no_id *lease) {
    pthread_mutex_lock(&runtime->registry);
    owner_record *record = owner_find_record(runtime, ticket);
    if (record) *lease = record->key.lease;
    pthread_mutex_unlock(&runtime->registry);
    return record != NULL;
}

/* Meaningful once the worker finished: it wipes the delivery copy before finishing. */
static bool delivery_wiped(const owner_record *record) {
    for (size_t i = 0; i < NO_CAPABILITY_BYTES; ++i) if (record->delivery.capability[i]) return false;
    return true;
}

bool fixture_inspect(no_runtime *runtime, no_ticket ticket, fixture_snapshot *snapshot) {
    pthread_mutex_lock(&runtime->registry);
    owner_record *record = owner_find_record(runtime, ticket);
    if (!record) { pthread_mutex_unlock(&runtime->registry); return false; }
    *snapshot = (fixture_snapshot){.request_id = record->key.request.low,
        .before_call = atomic_load(&record->before_call),
        .after_success = atomic_load(&record->after_success), .revoked = atomic_load(&record->revoked),
        .joined = record->join == JOIN_DONE, .direct_fixture_complete = record->settled,
        .launch_attempts = atomic_load(&record->launch_attempts),
        .owned_count = atomic_load(&record->owned_count), .close_attempts = atomic_load(&record->close_attempts),
        .scratch_diagnostic = atomic_load(&record->scratch_diagnostic),
        .creation_returned = atomic_load(&record->creation_returned),
        .failed_call = atomic_load(&record->failed_call),
        .native_success = atomic_load(&record->native_success),
        .pidfd_adopted = atomic_load(&record->pidfd_adopted),
        .nested_delivered = atomic_load(&record->nested_delivered), .delivery_wiped = delivery_wiped(record),
        .closed_pidfd = atomic_load(&record->closed_pidfd),
        .successful_joins = atomic_load(&record->successful_joins),
        .started_published = record->start != THREAD_STARTING};
    snapshot->worker_finished = atomic_load_explicit(&record->finished, memory_order_acquire);
    if (snapshot->worker_finished) {
        snapshot->child_dead = record->proof.child_dead;
        snapshot->no_child = record->proof.no_child;
        snapshot->io_settled = record->proof.io_settled;
        snapshot->wait = record->proof.wait;
        snapshot->sticky = record->proof.error.kind != NO_ERROR_NONE;
    }
    pthread_mutex_lock(&record->report_lock);
    snapshot->start = record->report.start;
    pthread_mutex_unlock(&record->report_lock);
    pthread_mutex_unlock(&runtime->registry);
    return true;
}

void fixture_release(no_runtime *runtime, no_ticket ticket) {
    pthread_mutex_lock(&runtime->registry);
    owner_record *record = owner_find_record(runtime, ticket);
    if (record) {
        atomic_store(&record->release_before, true);
        atomic_store(&record->release_after, true);
        atomic_store(&record->release_start, true);
        atomic_store(&record->release_failure, true);
        atomic_store(&record->release_adoption, true);
    }
    pthread_mutex_unlock(&runtime->registry);
}

void fixture_hold_report(no_runtime *runtime, no_ticket ticket, atomic_bool *entered, atomic_bool *release) {
    pthread_mutex_lock(&runtime->registry);
    owner_record *record = owner_find_record(runtime, ticket);
    pthread_mutex_unlock(&runtime->registry);
    if (!record) return;
    pthread_mutex_lock(&record->report_lock);
    atomic_store(entered, true);
    uint64_t expiry = owner_now() + 5000000000ULL;
    while (!atomic_load(release) && owner_now() < expiry) owner_pause();
    pthread_mutex_unlock(&record->report_lock);
}

bool fixture_failure_write_attempted(no_runtime *runtime, no_ticket ticket) {
    if (ticket.record.low == 0 || ticket.record.low > runtime->capacity) return false;
    return atomic_load(&runtime->records[ticket.record.low - 1].failure_write_attempt);
}
#endif
