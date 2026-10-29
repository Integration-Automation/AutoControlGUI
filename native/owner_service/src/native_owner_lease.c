#define _GNU_SOURCE
/* The core's lease ledger and the service-facing queries over it: production lease
 * registration, the parent payload snapshot, the admission state and the
 * application relay entry points. Every function takes the registry lock itself. */
#include "owner_internal.h"
#include <string.h>

static bool same_id(no_id a, no_id b) { return a.high == b.high && a.low == b.low; }

static bool parent_eligible_locked(no_runtime *runtime, no_ticket ticket, owner_record **out) {
    owner_record *parent = owner_find_record(runtime, ticket);
    if (!parent || parent->profile != PROFILE_PROTECTED || parent->anchor.state != ANCHOR_READY ||
        !parent->published_payload.published) return false;
    owner_record *ancestor = parent;
    for (size_t depth = 0; depth < NO_RECORD_LIMIT; ++depth) {
        if (ancestor->admission != ADMISSION_OPEN) return false;
        if (ancestor->parent_is_epoch) { *out = parent; return true; }
        size_t index = (size_t)(ancestor - runtime->records);
        if (ancestor->parent_slot >= index) return false;
        ancestor = &runtime->records[ancestor->parent_slot];
    }
    return false;
}

bool owner_register_lease(no_runtime *runtime, no_id lease, const no_ticket *parent, no_error *error) {
    *error = (no_error){0};
    if (!runtime || (lease.high == 0 && lease.low == 0)) { error->kind = NO_ERROR_ARGUMENT; return false; }
    pthread_mutex_lock(&runtime->registry);
    owner_record *eligible = NULL;
    if (runtime->admission_closed) error->kind = NO_ERROR_ADMISSION_CLOSED;
    else if (owner_lease_registered(runtime, lease) || owner_lease_closed(runtime, lease)) error->kind = NO_ERROR_KEY_CONFLICT;
    else if (runtime->registered_lease_count == NO_RECORD_LIMIT) error->kind = NO_ERROR_CAPACITY;
    else if (parent && !parent_eligible_locked(runtime, *parent, &eligible)) error->kind = NO_ERROR_ADMISSION_CLOSED;
    if (!error->kind) runtime->registered_leases[runtime->registered_lease_count++] = lease;
    pthread_mutex_unlock(&runtime->registry);
    return error->kind == NO_ERROR_NONE;
}

bool owner_parent_snapshot(no_runtime *runtime, no_ticket parent, parent_payload_identity *snapshot) {
    *snapshot = (parent_payload_identity){.parent = parent};
    pthread_mutex_lock(&runtime->registry);
    owner_record *record = NULL;
    if (parent_eligible_locked(runtime, parent, &record)) {
        snapshot->eligible = true;
        snapshot->payload = record->published_payload;
    }
    pthread_mutex_unlock(&runtime->registry);
    return snapshot->eligible;
}

/* Under the registry lock: the record exists, belongs to this lease, the lease is
 * registered and not closed, and the record relays at all. */
static owner_record *relay_record_locked(no_runtime *runtime, no_id lease, no_ticket ticket, no_error *error) {
    owner_record *record = owner_find_record(runtime, ticket);
    if (!record || !record->relay_enabled || !same_id(record->key.lease, lease)) {
        error->kind = NO_ERROR_UNKNOWN_TICKET; return NULL;
    }
    if (!owner_lease_registered(runtime, lease) || owner_lease_closed(runtime, lease)) {
        error->kind = NO_ERROR_ADMISSION_CLOSED; return NULL;
    }
    return record;
}

bool owner_relay_write(no_runtime *runtime, no_id lease, no_ticket ticket, const uint8_t *data, size_t length,
                       size_t *accepted, no_error *error) {
    *error = (no_error){0};
    *accepted = 0;
    pthread_mutex_lock(&runtime->registry);
    owner_record *record = relay_record_locked(runtime, lease, ticket, error);
    if (record && record->admission != ADMISSION_OPEN) { error->kind = NO_ERROR_ADMISSION_CLOSED; record = NULL; }
    if (record) {
        pthread_mutex_lock(&record->relay.lock);
        if (record->relay.closed) error->kind = NO_ERROR_ADMISSION_CLOSED;
        else {
            size_t room = NO_RELAY_BYTES - record->relay.request_length;
            *accepted = length < room ? length : room;
            memcpy(record->relay.request + record->relay.request_length, data, *accepted);
            record->relay.request_length += *accepted;
        }
        pthread_mutex_unlock(&record->relay.lock);
    }
    pthread_mutex_unlock(&runtime->registry);
    return error->kind == NO_ERROR_NONE;
}

/* A fenced record still yields what its child wrote before exiting; only a
 * closed lease ends delivery, so a reply can never outlive its lease. */
bool owner_relay_read(no_runtime *runtime, no_id lease, no_ticket ticket, uint8_t *data, size_t capacity,
                      size_t *length, bool *eof, no_error *error) {
    *error = (no_error){0};
    *length = 0;
    *eof = false;
    pthread_mutex_lock(&runtime->registry);
    owner_record *record = relay_record_locked(runtime, lease, ticket, error);
    if (record) {
        pthread_mutex_lock(&record->relay.lock);
        *length = record->relay.reply_length < capacity ? record->relay.reply_length : capacity;
        memcpy(data, record->relay.reply, *length);
        memmove(record->relay.reply, record->relay.reply + *length, record->relay.reply_length - *length);
        record->relay.reply_length -= *length;
        *eof = record->relay.reply_length == 0 && (record->relay.reply_eof || record->relay.closed);
        pthread_mutex_unlock(&record->relay.lock);
    }
    pthread_mutex_unlock(&runtime->registry);
    return error->kind == NO_ERROR_NONE;
}

/* A closed lease may still learn how its own helper ended; nobody else may. */
bool owner_observe_for_lease(no_runtime *runtime, no_id lease, no_ticket ticket, no_report *report,
                             no_error *error) {
    *error = (no_error){0};
    pthread_mutex_lock(&runtime->registry);
    owner_record *record = owner_find_record(runtime, ticket);
    bool owned = record && same_id(record->key.lease, lease) && owner_lease_registered(runtime, lease);
    pthread_mutex_unlock(&runtime->registry);
    if (!owned) { error->kind = NO_ERROR_UNKNOWN_TICKET; return false; }
    *report = no_observe(runtime, ticket, (no_deadline){owner_now() + 1000000ULL});
    return true;
}

bool owner_admission_open(no_runtime *runtime) {
    pthread_mutex_lock(&runtime->registry);
    bool open = !runtime->admission_closed;
    pthread_mutex_unlock(&runtime->registry);
    return open;
}
