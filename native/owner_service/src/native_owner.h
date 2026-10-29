#ifndef AUTOCONTROL_NATIVE_OWNER_H
#define AUTOCONTROL_NATIVE_OWNER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Service-domain interface. No fd, PID, clone scratch, wire frame or worker
 * operations are available to IPC handlers through this header. */
typedef struct no_runtime no_runtime;
typedef struct no_authenticated_scope no_authenticated_scope;
typedef struct no_validated_spec no_validated_spec;
typedef struct no_boot_policy no_boot_policy;

typedef struct { uint64_t high, low; } no_id;
typedef struct { no_id service_epoch, record; } no_ticket;
typedef struct { no_id lease, request; } no_request_key;
typedef struct { uint64_t monotonic_ns; } no_deadline;

typedef enum {
    NO_ERROR_NONE,
    NO_ERROR_ARGUMENT,
    NO_ERROR_UNAVAILABLE,
    NO_ERROR_CAPACITY,
    NO_ERROR_ALLOCATION,
    NO_ERROR_THREAD_START,
    NO_ERROR_ADMISSION_CLOSED,
    NO_ERROR_KEY_CONFLICT,
    NO_ERROR_UNKNOWN_TICKET,
    NO_ERROR_NATIVE_CONTRACT,
    NO_ERROR_CLEANUP
} no_error_kind;

typedef struct {
    no_error_kind kind;
    int system_errno;
    uint32_t operation_code;
} no_error;

typedef enum {
    NO_ACCEPTED,
    NO_EXISTING,
    NO_REJECTED
} no_submit_result;

typedef enum {
    NO_START_NOT_RESOLVED,
    NO_START_FAILED_WITHOUT_CHILD,
    NO_START_CHILD_CREATED,
    NO_START_EXEC_FAILED,
    NO_START_READY
} no_start_kind;

typedef enum {
    NO_CHILD_NOT_RESOLVED,
    NO_CHILD_NEVER_CREATED,
    NO_CHILD_LIVE,
    NO_CHILD_DEAD
} no_child_state;

typedef enum {
    NO_WAIT_PENDING,
    NO_WAIT_NOT_APPLICABLE,
    NO_WAIT_EXITED,
    NO_WAIT_SIGNALLED,
    NO_WAIT_STATUS_UNAVAILABLE
} no_wait_kind;

typedef struct {
    no_wait_kind kind;
    int value; /* Exit code or signal only for the corresponding kind. */
} no_wait_status;

typedef enum {
    NO_PENDING_LAUNCH,
    NO_PENDING_EXEC,
    NO_PENDING_CHILD,
    NO_PENDING_TREE,
    NO_PENDING_NESTED_LAUNCH,
    NO_PENDING_IO,
    NO_PENDING_JOIN,
    NO_PENDING_SNAPSHOT
} no_pending_reason;

typedef enum {
    NO_REPORT_PENDING,
    NO_REPORT_RETIRED,
    NO_REPORT_STICKY_UNKNOWN,
    NO_REPORT_UNKNOWN_TICKET,
    NO_REPORT_SETTLED_WITHOUT_SCOPE
} no_report_kind;

typedef struct {
    no_start_kind kind;
    no_error failure;
} no_start_outcome;

typedef struct {
    no_child_state child;
    no_wait_status wait;
    no_pending_reason reason;
    bool revoked;
} no_pending;

/* This receipt can be formed only after production containment verification.
 * It has no caller-set booleans for partially established retirement. */
typedef struct {
    no_wait_status wait;
    no_id protected_tree;
    no_id service_epoch;
} no_retired_receipt;

typedef struct {
    no_error first_error;
    uint32_t additional_error_count;
    bool errors_overflowed;
    bool cleanup_still_running;
    no_child_state child;
} no_sticky_unknown;

typedef struct { no_id service_epoch; } no_no_scope_receipt;

typedef struct {
    no_report_kind kind;
    no_start_outcome start;
    union {
        no_pending pending;
        no_retired_receipt retired;
        no_sticky_unknown unknown;
        no_no_scope_receipt without_scope;
    } detail;
} no_report;

/* Memory-only creation copies policy and initializes bounded registry storage.
 * It opens no descriptors and starts no threads. On failure only initialized
 * memory/mutex state needs destruction. Service listener and guardian resources
 * stay owned by the separate service bootstrap record. */
no_runtime *no_runtime_create(const no_boot_policy *policy, no_error *error);

/* Copies argv/env and freezes authenticated scope ownership before registration.
 * Each record receives its own protected subtree below authenticated ancestry.
 * Spec and scope inputs remain caller-owned and can be released after return.
 * All allocation precedes worker launch and kernel resource acquisition.
 * A key retry with changed spec or scope returns NO_REJECTED/KEY_CONFLICT.
 * out_ticket is valid only for ACCEPTED or EXISTING. Failed IPC publication
 * cannot remove its registry record. No ownership is transferred to the caller. */
no_submit_result no_submit(no_runtime *runtime,
                           const no_authenticated_scope *scope,
                           no_request_key key,
                           const no_validated_spec *spec,
                           no_ticket *out_ticket,
                           no_error *error);

/* Idempotent intent. Does no cleanup syscall or worker join. Unknown or stale
 * epoch returns false; it cannot create a new ticket. Child admission fences
 * serialize with this transition before the function returns true. */
bool no_revoke(no_runtime *runtime, no_ticket ticket);

/* Leases are revoked by service disconnect/expiry without Python participation.
 * Future submissions under this lease are rejected. Existing records persist. */
void no_revoke_lease(no_runtime *runtime, no_id lease);

/* Waits only for reports until an absolute monotonic deadline. It performs no
 * signal, close, cgroup read or native wait syscall on the observer's thread.
 * Timeout returns pending; a previous sticky failure remains sticky. */
no_report no_observe(no_runtime *runtime, no_ticket ticket,
                     no_deadline deadline);

/* Service maintenance performs bounded registry work and nonblocking joins of
 * workers that announced completion. A per-record join claim prevents double join. It never performs cleanup syscalls or
 * blocking joins. Call even when client IPC is quiet or notifications failed. */
void no_runtime_maintain(no_runtime *runtime, no_deadline deadline);

/* Requests global revoke. Returns false while any worker/bootstrap cleanup is
 * unresolved. Runtime memory and resource ownership stay intact on false.
 * Caller must stop API admission and drain concurrent API users before a final
 * shutdown call may consume runtime. True consumes it only after all workers
 * have joined and resources settled. False retains the pointer and ownership. */
bool no_runtime_shutdown(no_runtime **runtime, no_deadline deadline,
                          no_error *error);

#endif


