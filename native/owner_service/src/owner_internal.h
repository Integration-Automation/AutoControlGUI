#ifndef OWNER_INTERNAL_H
#define OWNER_INTERNAL_H
#define _GNU_SOURCE
#include "native_owner.h"
#include <pthread.h>
#include <stdatomic.h>

#define NO_RECORD_LIMIT 32
#define NO_PATH_LIMIT 4096

typedef enum { FD_EMPTY, FD_OWNED, FD_CLOSED, FD_CLOSE_ERROR } fd_state;
typedef struct { fd_state state; int number; } owned_fd;
typedef enum { PROOF_UNRESOLVED, PROOF_DIRECT_FIXTURE, PROOF_CONTAINED, PROOF_WITHOUT_SCOPE } proof_kind;
typedef enum { JOIN_NONE, JOIN_ELIGIBLE, JOIN_CLAIMED, JOIN_DONE, JOIN_FAILED } join_state;
typedef enum { THREAD_STARTING, THREAD_STARTED, THREAD_NO_THREAD } start_state;
#define NO_COMPONENT_LIMIT 96
#define NO_ARGUMENT_LIMIT 64
#define NO_SPEC_BYTES 32768
_Static_assert(NO_RECORD_LIMIT <= 32, "child obligations fit uint32_t");
typedef enum { PROFILE_DIRECT_FIXTURE, PROFILE_PROTECTED } owner_profile;
typedef enum { ADMISSION_OPEN, ADMISSION_FENCED } admission_state;
typedef enum { ANCHOR_UNPUBLISHED, ANCHOR_READY, ANCHOR_INVALIDATED } anchor_state;
typedef struct { anchor_state state; int borrowed_directory; } child_anchor;
typedef enum { DIR_PLANNED, DIR_CREATED_UNOPENED, DIR_OPENED, DIR_REMOVED,
               DIR_IDENTITY_UNCERTAIN } directory_state;
typedef struct {
    char component[NO_COMPONENT_LIMIT];
    directory_state state;
    owned_fd descriptor;
} owned_directory;
typedef struct {
    owned_fd parent_anchor, events, kill;
    owned_directory container, payload;
} worker_scope;
typedef enum { EMPTY_UNPROVEN, EMPTY_POPULATION_OBSERVED,
               EMPTY_EXACT_REMOVAL_WITH_FENCED_NO_ENTRY } empty_evidence_kind;
typedef enum { CLEAN_NEVER_CREATED, CLEAN_EXACT_REMOVAL, CLEAN_UNRESOLVED } namespace_result;
typedef struct {
    namespace_result container, payload;
    empty_evidence_kind emptiness;
    no_id protected_tree;
    bool admission_fenced, children_settled, launch_resolved, descriptors_clean;
} contained_evidence;
typedef enum { NO_WORKER_CREATED, WORKER_JOIN_REQUIRED } no_scope_execution;
typedef struct { no_scope_execution execution; } without_scope_evidence;
typedef struct {
    no_id identity, epoch;
    no_ticket permitted_parent;
    no_id lease;
    bool parent_is_epoch;
} scope_identity;
typedef struct authenticated_scope_slot {
    scope_identity identity;
    atomic_uint borrowers;
    atomic_bool issuance_closed;
    owned_fd peer, epoch_anchor;
    bool resources_settled;
} authenticated_scope_slot;
typedef struct { authenticated_scope_slot slots[NO_RECORD_LIMIT]; size_t count; } scope_owner;
typedef struct { authenticated_scope_slot *slot; } scope_reference;
#define NO_CAPABILITY_BYTES 32
#define NO_BOOTSTRAP_MAGIC 0x4143424eu
#define NO_BOOTSTRAP_VERSION 1
#define NO_BOOTSTRAP_FD 4
/* A delivery copy, not authority: the service's grant stays the only record of the
 * capability. The worker writes it once to its own child and then wipes it. */
typedef struct { bool wanted; uint8_t capability[NO_CAPABILITY_BYTES]; } nested_delivery;
#define NO_RELAY_BYTES 65536
/* Application bytes between a client lease and its helper. The service thread
 * appends requests and drains replies; the worker moves bytes between these
 * buffers and the child's fd 0 and fd 1. The lock covers memory copies only:
 * every pipe syscall runs outside it on a stack chunk. */
typedef struct {
    pthread_mutex_t lock;
    size_t request_length, reply_length;
    bool reply_eof, closed;
    uint8_t request[NO_RELAY_BYTES], reply[NO_RELAY_BYTES];
} relay_buffers;
/* The one frame a nested-capable child reads from NO_BOOTSTRAP_FD, then EOF. */
typedef struct {
    uint32_t magic, version;
    no_ticket parent;
    uint8_t capability[NO_CAPABILITY_BYTES];
} owner_nested_bootstrap;
typedef struct {
    size_t argc, envc, bytes;
    char *argv[NO_ARGUMENT_LIMIT + 1], *env[NO_ARGUMENT_LIMIT + 1];
    char executable[NO_PATH_LIMIT], cwd[NO_PATH_LIMIT];
    uint32_t uid, gid, socket_gid;
    uint64_t pids_max, memory_max;
    /* Replay compares whether a capability exists, never its bytes: a retried START
     * carries a fresh one, and the record keeps the first. */
    nested_delivery delivery;
    char storage[NO_SPEC_BYTES];
} immutable_spec_arena;
/* Published once by the worker after payload creation and a live child. The
 * cgroup2 directory inode equals the kernel cgroup ID on 64-bit hosts. */
typedef struct { bool published; uint64_t device, inode; uint32_t uid, gid; } payload_identity;
typedef struct { bool eligible; no_ticket parent; payload_identity payload; } parent_payload_identity;
typedef struct {
    proof_kind kind;
    bool child_dead, no_child, io_settled;
    no_wait_status wait;
    no_error error;
    union { contained_evidence contained; without_scope_evidence without_scope; } detail;
} finished_proof;

struct no_boot_policy { size_t capacity; no_id epoch; };
struct no_authenticated_scope { scope_reference reference; };
struct no_validated_spec {
    const char *executable, *cwd;
    const char *const *argv, *const *env;
    size_t argc, envc;
    uint32_t uid, gid;
    const uint8_t *nested_capability; /* NULL unless the policy permits child policies. */
    uint32_t socket_gid; /* Only supplementary group of a nested-capable payload; 0 for none. */
    /* Written to the record's container before its payload exists; 0 inherits the parent's. */
    uint64_t pids_max, memory_max;
};

typedef struct {
    bool hold_before_call, hold_after_success, fail_thread, fail_close, hold_start_publication;
    bool admission_probe, child_hold, fail_child_setup, hold_adoption, nested_bootstrap, relay, rpc;
} fixture_options;

typedef struct owner_record {
    struct no_runtime *runtime;
    no_ticket ticket;
    no_request_key key;
    char executable[NO_PATH_LIMIT];
    fixture_options options;
    owner_profile profile;
    size_t parent_slot;
    bool parent_is_epoch;
    scope_identity immutable_scope_identity;
    scope_reference retained_scope;
    immutable_spec_arena *spec;
    admission_state admission;
    uint32_t unsettled_children;
    child_anchor anchor;
    payload_identity published_payload;
    worker_scope scope;
    no_id planned_protected_tree;
    pthread_t thread;
    pthread_mutex_t report_lock;
    atomic_bool revoked, finished, before_call, after_success, release_before, release_after;
    atomic_bool creation_returned, release_start;
    atomic_bool failed_call, release_failure;
    atomic_bool native_success, release_adoption, pidfd_adopted, failure_write_attempt;
    atomic_uint launch_attempts, owned_count, close_attempts;
    atomic_int scratch_diagnostic;
    atomic_int closed_pidfd;
    atomic_uint successful_joins;
    no_report report;
    finished_proof proof;
    join_state join;
    start_state start;
    bool registered, thread_created, settled;
    owned_fd pidfd, lifetime_read, lifetime_write, exec_read, exec_write, cgroup_probe;
    owned_fd output_sink; /* /dev/null for the child's stdout/stderr; closed once a child exists. */
    owned_fd bootstrap_read, bootstrap_write; /* Present only while delivery.wanted. */
    owned_fd reply_read, reply_write;         /* Present only while relay_enabled. */
    bool relay_enabled;                       /* Protected records always; fixtures by option. */
    relay_buffers relay;
    nested_delivery delivery;
    atomic_bool nested_delivered;
} owner_record;

struct no_runtime {
    pthread_mutex_t registry;
    size_t capacity, count;
    no_id epoch;
    bool admission_closed;
    no_id revoked_leases[NO_RECORD_LIMIT];
    size_t revoked_lease_count;
    no_id registered_leases[NO_RECORD_LIMIT];
    size_t registered_lease_count;
    owner_record *records;
};

bool scope_retain(scope_reference existing, scope_reference *copy);
/* Sole production lease registration. A non-NULL parent must be eligible under
 * the same registry lock, so a parent revoke either precedes and refuses the
 * lease or follows and fences the descendants admitted under it. */
bool owner_register_lease(no_runtime *runtime, no_id lease, const no_ticket *parent, no_error *error);
bool owner_parent_snapshot(no_runtime *runtime, no_ticket parent, parent_payload_identity *snapshot);
/* Application relay, service thread only. The ticket's record must have been
 * admitted under this still-open lease. Writes need open admission and accept at
 * most the free buffer space; reads drain what the worker collected and report EOF
 * once the child closed fd 1 or the worker stopped relaying and nothing remains. */
bool owner_relay_write(no_runtime *runtime, no_id lease, no_ticket ticket, const uint8_t *data, size_t length,
                       size_t *accepted, no_error *error);
bool owner_relay_read(no_runtime *runtime, no_id lease, no_ticket ticket, uint8_t *data, size_t capacity,
                      size_t *length, bool *eof, no_error *error);
/* Read-only, for the lease the record was admitted under, open or closed. */
bool owner_observe_for_lease(no_runtime *runtime, no_id lease, no_ticket ticket, no_report *report,
                             no_error *error);
void owner_relay_pump(owner_record *record);
void owner_relay_drain(owner_record *record);
void owner_relay_close(owner_record *record);
/* True once every record slot of the epoch has been admitted. */
bool owner_records_full(no_runtime *runtime);
/* False once the core closed admission for the epoch (join failure, revoke ledger full). */
bool owner_admission_open(no_runtime *runtime);
void owner_publish_payload(owner_record *record);
void scope_release(scope_reference *reference);
void authentication_owner_scan(scope_owner *owner);
owner_record *owner_find_record(no_runtime *runtime, no_ticket ticket);
bool owner_lease_closed(no_runtime *runtime, no_id lease);
bool owner_lease_registered(no_runtime *runtime, no_id lease);
bool owner_child_bit(size_t slot, uint32_t *bit);
void owner_fence_locked(owner_record *record);
bool owner_invalidate_anchor_locked(owner_record *record);
void owner_publish_anchor_locked(owner_record *record);
void *owner_protected_worker(void *raw);
uint64_t owner_now(void);
void owner_pause(void);
void owner_set_error(owner_record *record, no_error_kind kind, int error);
void owner_close_slot(owner_record *record, owned_fd *slot);
void owner_publish(owner_record *record, no_pending_reason reason, no_child_state child);
void *owner_worker(void *raw);
int owner_launch(owner_record *record);
void owner_retire_child(owner_record *record);

#ifdef NO_ACCEPTANCE_BUILD
no_submit_result owner_fixture_submit(no_runtime *, no_request_key, const char *,
                                      fixture_options, no_ticket *, no_error *);
#endif
#endif
