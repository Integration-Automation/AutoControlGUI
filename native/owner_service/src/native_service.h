#ifndef AUTOCONTROL_NATIVE_SERVICE_H
#define AUTOCONTROL_NATIVE_SERVICE_H
/* Private to the owner service executable. Never installed and never exposed to
 * Python: the wire frames below are the only thing a client ever sees. */
#include "owner_internal.h"
#include <stddef.h>
#include <sys/socket.h>
#include <sys/types.h>

#define SERVICE_CONNECTION_LIMIT 16
/* IDs in each policy's payload range: one slice per epoch that may run at once, so
 * retiring epochs and the current one never share an ID. The guardian picks each epoch's
 * slice and sends it in the grant. */
#define SERVICE_EPOCH_IDS SERVICE_LEASE_LIMIT
#define SERVICE_PAYLOAD_SLICES 4
#define SERVICE_PAYLOAD_IDS (SERVICE_PAYLOAD_SLICES * SERVICE_EPOCH_IDS)
#define SERVICE_IDLE_GRACE_NS 5000000000ULL /* A spent epoch waits this long for a lease-less connection. */
#define SERVICE_MIN_PIDS 8                     /* Below this a helper cannot start its threads. */
#define SERVICE_MIN_MEMORY (16ULL << 20)      /* 16 MiB. */
#define SERVICE_MAX_PIDS (1ULL << 22)         /* The kernel's own pid_max ceiling. */
#define SERVICE_MAX_MEMORY (1ULL << 46)       /* 64 TiB: times the record capacity, never wraps. */
#define SERVICE_LEASE_LIMIT NO_RECORD_LIMIT
#define SERVICE_CLIENT_LIMIT 4
#define SERVICE_ARGUMENT_BYTES 1024
#define SERVICE_DATA_BYTES 8192 /* Relay bytes per OP_WRITE or OP_READ frame. */
#define SERVICE_CAPABILITY_BYTES 32
#define SERVICE_RIGHTS_LIMIT 253 /* SCM_MAX_FD: every delivered right is collected and owned. */
#define SERVICE_MAGIC 0x41435356u
#define SERVICE_VERSION 1
#define SERVICE_GUARDIAN_FD 3 /* The guardian places its endpoint here before exec. */
_Static_assert(SERVICE_LEASE_LIMIT == NO_RECORD_LIMIT, "lease ledger mirrors the core arrays");
_Static_assert(SERVICE_CAPABILITY_BYTES == NO_CAPABILITY_BYTES, "the core delivers exactly the issued capability");

typedef enum { OP_OPEN_TOP = 1, OP_OPEN_CHILD, OP_START, OP_CLOSE, OP_WRITE, OP_READ, OP_OBSERVE, OP_RENEW
} service_opcode;
enum { REPLY_EOF = 1 }; /* OP_READ: the helper closed fd 1 or stopped, and nothing remains. */
typedef enum {
    STATUS_OK, STATUS_EXISTING, STATUS_REJECTED, STATUS_CLOSED, STATUS_CONFLICT,
    STATUS_CAPACITY, STATUS_UNAUTHENTICATED, STATUS_MALFORMED, STATUS_UNAVAILABLE
} service_status;

/* Exact-size frames. Executable, cwd, environment, credentials and scope are never
 * protocol inputs: a client names a policy and fills its bounded argument slots. */
typedef struct {
    uint32_t magic;
    uint16_t version, opcode;
    no_id nonce, lease, request;
    no_ticket parent;
    uint32_t policy, argc;
    uint8_t capability[SERVICE_CAPABILITY_BYTES];
    char arguments[SERVICE_ARGUMENT_BYTES];
    no_ticket ticket;      /* OP_WRITE / OP_READ: a record admitted under `lease`. */
    uint32_t data_length;  /* OP_WRITE: bytes in `data`. */
    uint8_t data[SERVICE_DATA_BYTES];
} service_request;

typedef struct {
    uint32_t magic;
    uint16_t version, opcode;
    uint32_t status;
    no_error error;
    no_id nonce, lease;
    uint64_t lease_deadline_ns;
    no_ticket ticket;
    uint32_t flags;        /* OP_READ: REPLY_EOF. */
    uint32_t data_length;  /* OP_WRITE: bytes accepted. OP_READ: bytes in `data`. */
    uint32_t report_kind, start_kind, wait_kind; /* OP_OBSERVE: no_report_kind, no_start_kind, no_wait_kind. */
    int32_t wait_value;
    uint8_t data[SERVICE_DATA_BYTES];
} service_reply;

/* The Python client (owner_service_wire.py) mirrors these exact layouts. */
_Static_assert(sizeof(service_request) == 9384 && offsetof(service_request, nonce) == 8 &&
               offsetof(service_request, lease) == 24 && offsetof(service_request, request) == 40 &&
               offsetof(service_request, parent) == 56 && offsetof(service_request, policy) == 88 &&
               offsetof(service_request, capability) == 96 && offsetof(service_request, arguments) == 128 &&
               offsetof(service_request, ticket) == 1152 && offsetof(service_request, data_length) == 1184 &&
               offsetof(service_request, data) == 1188, "request layout is the client's wire contract");
_Static_assert(sizeof(service_reply) == 8312 && offsetof(service_reply, status) == 8 &&
               offsetof(service_reply, error) == 12 && offsetof(service_reply, nonce) == 24 &&
               offsetof(service_reply, lease) == 40 && offsetof(service_reply, lease_deadline_ns) == 56 &&
               offsetof(service_reply, ticket) == 64 && offsetof(service_reply, flags) == 96 &&
               offsetof(service_reply, data_length) == 100 && offsetof(service_reply, report_kind) == 104 &&
               offsetof(service_reply, data) == 120, "reply layout is the client's wire contract");

/* Handshake: the service enables credential passing, then sends GRANT_REQUESTED.
 * A frame queued before that carries no sender identity (the kernel reports pid 0
 * and the overflow UID, without SCM_PIDFD), so the guardian sends only after it. */
/* GRANT_CONNECTION hands over one client connection the guardian accepted and verified
 * (principal and namespaces, which only root can read); the service never listens. */
/* GRANT_RETIRING, service to guardian: this epoch is spent but still holds open leases.
 * The guardian stops handing it connections and starts the next epoch beside it; this one
 * keeps serving its leases and drains when they end. */
typedef enum { GRANT_EPOCH = 1, GRANT_ACKNOWLEDGED, GRANT_REQUESTED, GRANT_CONNECTION, GRANT_RETIRING } grant_kind;
typedef struct {
    uint32_t magic;
    uint16_t version, kind;
    no_id epoch;
    uint64_t generation;
    /* GRANT_EPOCH: the slice of every payload range this epoch uses, below
     * SERVICE_PAYLOAD_SLICES. The guardian picks it so epochs running at once never share one. */
    uint32_t payload_slice, reserved;
} guardian_grant;
enum { GRANT_EPOCH_DIRECTORY, GRANT_RIGHTS };

/* nsfs identities. Reading another process's namespaces needs ptrace read access to
 * it (measured: EPERM across users), so only the root guardian compares them. */
typedef struct { uint64_t device, user, pid, mount, cgroup; } service_namespaces;
typedef struct { uint32_t uid, gid; } service_principal;

typedef struct {
    uint32_t id;
    bool nested;
    const char *executable, *cwd;
    const char *const *fixed_argv, *const *env;
    size_t fixed_argc, envc, max_client_arguments;
    const char *argument_alphabet; /* Every client argument byte; never empty, never a leading '-'. */
    /* The first of SERVICE_PAYLOAD_IDS user and group IDs. A record runs as base + its
     * epoch's half + its lease position, so no two live helpers share an account, even
     * across a retiring epoch and its successor; no account need exist for them. */
    uint32_t payload_uid, payload_gid;
    uint32_t child_policies; /* Bit i permits nested policy id i under a record of this policy. */
} service_launch_policy;

/* Compiled into the installed service from the reviewed manifest. Not a CLI input. */
typedef struct {
    service_principal guardian;
    service_principal clients[SERVICE_CLIENT_LIMIT];
    size_t client_count;
    const service_launch_policy *policies;
    size_t policy_count;
    uint64_t lease_lifetime_ns;
    uint64_t lease_max_age_ns;   /* OP_RENEW never extends a lease past this age. */
    uint32_t socket_gid;         /* The listener's group; no payload may hold it. */
    size_t client_lease_quota; /* Lease positions one account may use per epoch, open or spent. */
    size_t nested_lease_quota; /* Child leases one parent record may open per epoch, open or spent. */
    size_t record_capacity;
    uint64_t record_pids_max;   /* Processes one helper and its nested children may hold. */
    size_t connections_per_account; /* At most half the table, so no account locks out another. */
    uint64_t record_memory_max; /* Bytes of memory for the same; swap is closed where accounted. */
} service_policy;

/* Kernel identity of a process: pidfs inode. Never a numeric PID or fd number. */
typedef struct { owned_fd pidfd; uint64_t inode; struct ucred credentials; } peer_identity;

typedef enum { CONNECTION_EMPTY, CONNECTION_OPEN, CONNECTION_CLOSED } connection_phase;
typedef struct {
    connection_phase phase;
    uint64_t generation;
    owned_fd socket;
    peer_identity connector;
    uint64_t active_ns; /* Last packet received, or adoption. */
} service_connection;

typedef enum { LEASE_UNUSED, LEASE_RESERVED, LEASE_OPEN, LEASE_CLOSED } lease_phase;
typedef enum {
    CLOSE_NONE, CLOSE_REQUESTED, CLOSE_DISCONNECT, CLOSE_PEER_DEATH, CLOSE_EXPIRED,
    CLOSE_REPLY_LOST, CLOSE_SENDER_MISMATCH, CLOSE_SHUTDOWN, CLOSE_FAILED_ISSUE, CLOSE_ACCOUNT_LIMIT
} close_reason;
typedef struct {
    lease_phase phase;
    close_reason reason;
    no_id id, open_nonce;
    size_t connection;
    uint64_t connection_generation, holder_inode;
    uint32_t holder_uid;
    bool nested;
    uint32_t policy;
    no_ticket parent;
    uint64_t expires_ns, opened_ns;
    bool started;          /* START was admitted: its request ID and ticket are kept for replay. */
    no_id start_request;
    no_ticket ticket;
    no_authenticated_scope scope; /* The issuer's own reference, released once on close. */
} service_lease;

typedef struct {
    bool issued;
    uint32_t policy;
    uint8_t capability[SERVICE_CAPABILITY_BYTES];
} nested_grant;

typedef enum {
    BOOT_EMPTY, BOOT_ACTIVE, BOOT_DRAINING, BOOT_QUIESCENT, BOOT_STICKY,
#ifdef NO_ACCEPTANCE_BUILD
    BOOT_PEER_EVIDENCE_ONLY, /* Acceptance only: real peers and leases, no protected authority. */
#endif
} bootstrap_phase;
/* REFUSED took nothing: the channel and the service are exactly as passed in. */
typedef enum {
    BOOTSTRAP_READY, BOOTSTRAP_CLEAN_FAILURE, BOOTSTRAP_OWNED_UNRESOLVED, BOOTSTRAP_REFUSED
} bootstrap_result;
typedef enum { SERVICE_RUNNING, SERVICE_PENDING, SERVICE_CLEAN, SERVICE_STICKY } service_result;

typedef struct service_state {
    bootstrap_phase phase;
    const service_policy *policy;
    peer_identity guardian_peer;
    owned_fd guardian, listener, epoch_anchor;
    uint64_t epoch_device;
    no_id epoch;
    uint64_t generation;
    no_runtime *runtime;
    scope_owner scopes; /* Lease i owns slot i; neither is reused within the epoch. */
    service_connection connections[SERVICE_CONNECTION_LIMIT];
    service_lease leases[SERVICE_LEASE_LIMIT];
    size_t lease_count;
    nested_grant grants[NO_RECORD_LIMIT];
    no_error first_error;
    bool close_uncertain;
    bool retiring; /* GRANT_RETIRING was sent: the guardian hands this epoch nothing more. */
    uint32_t payload_slice; /* From the grant. */
#ifdef NO_ACCEPTANCE_BUILD
    const char *fixture_executable; /* Acceptance only: START admits a direct-fixture relay record. */
#endif
} service_state;

/* native_service.c: the single event owner for every resource above. */
/* True when the compiled manifest is coherent (service_policy.c). */
bool service_policy_valid(const service_policy *policy);
/* Open connections of `uid`'s account other than `except`; a payload range is one account. */
size_t service_account_connections(const service_state *service, size_t except, uint32_t uid);
/* argv for a START: the policy's fixed words, then the client's, each a non-empty word
 * over the policy alphabet that cannot be read as an option (service_policy.c). */
bool service_client_arguments(const service_request *request, const service_launch_policy *policy,
                              const char **argv, size_t *argc);
/* Fresh child capability bytes when the policy may start nested children. */
bool service_fresh_capability(const service_launch_policy *policy, uint8_t *capability, bool *wanted);
service_state *service_allocate(const service_policy *policy, no_error *error);
service_result service_run_one(service_state *service, int timeout_ms);
service_result service_drain(service_state *service, no_deadline deadline);
bool service_free(service_state **service);
void service_close_lease(service_state *service, service_lease *lease, close_reason reason);
void service_settle(service_state *service);

/* service_bootstrap_linux.c: consumes the inherited guardian channel unless REFUSED. */
bootstrap_result service_bootstrap(service_state *service, int inherited_channel,
                                   no_deadline deadline, no_error *error);

/* service_peer_linux.c: kernel credential handling shared by bootstrap and clients. */
typedef struct {
    ssize_t bytes;
    int flags;
    bool credentials_seen, duplicate_credentials;
    struct ucred credentials;
    peer_identity sender;
    size_t right_count;
    owned_fd rights[SERVICE_RIGHTS_LIMIT];
} received_packet;

bool service_close_fd(owned_fd *slot);
bool peer_identity_adopt(peer_identity *identity, int pidfd);
bool peer_identity_from_connection(peer_identity *identity, int socket, no_error *error);
bool peer_alive(const peer_identity *identity);
bool peer_same_process(const peer_identity *a, const peer_identity *b);
bool peer_in_cgroup(const peer_identity *peer, uint64_t cgroup_inode);
bool peer_in_namespaces(const peer_identity *peer, const service_namespaces *expected);
/* As peer_in_namespaces, leaving the mount namespace to peer_shares_mount_namespace. */
bool peer_in_namespaces_beside_mount(const peer_identity *peer, const service_namespaces *expected);
/* True when `peer` lives in `other`'s mount namespace (both read through their pidfds). */
bool peer_shares_mount_namespace(const peer_identity *peer, const peer_identity *other);
bool peer_enable_credentials(int socket, no_error *error);
bool packet_receive(int socket, void *frame, size_t size, int flags, received_packet *packet, no_error *error);
bool packet_authenticated(const received_packet *packet, const peer_identity *connector, size_t expected_rights);
bool packet_release(received_packet *packet);
bool service_random(void *buffer, size_t size);

#ifdef NO_ACCEPTANCE_BUILD
bool fixture_service_peer_only(service_state *service, int listener, int anchor, no_id epoch);
/* The test process, as creator of `channel`, plays the guardian that hands over connections. */
bool fixture_service_guardian(service_state *service, int channel);
#endif
#endif
