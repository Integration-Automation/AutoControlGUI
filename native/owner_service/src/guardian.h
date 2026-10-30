#ifndef AUTOCONTROL_GUARDIAN_H
#define AUTOCONTROL_GUARDIAN_H
/* The root guardian: the only party that creates, delegates, grants and reclaims a
 * service epoch. Private to the guardian executable. */
#include "guardian_journal.h"
#include "native_service.h"
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/mount.h>
#include <sys/types.h>

/* A client account and the namespaces its processes must live in. */
/* `id_count` > 1 lists a payload range: uid + k with gid + k, for k below it. */
typedef struct { uint32_t uid, gid; service_namespaces namespaces; uint32_t id_count; } guardian_client;

/* Compiled in from the provisioned manifest; never an argument or environment value. */
typedef struct {
    const char *state_directory;
    uid_t administrator;            /* Owner of the state directory: root in production. */
    const char *cgroup_mount;       /* An absolute cgroup2 mount. */
    const char *subtree;            /* Beneath the mount; "." for the mount itself. */
    uid_t hierarchy_owner;          /* Owner of the subtree: root in production. */
    uint32_t service_uid, service_gid;
    const char *service_executable;
    const char *listener_path;
    uint32_t listener_gid;          /* Clients reach the 0660 socket through this group. */
    uint8_t installation[GJ_INSTALLATION_BYTES];
    uint32_t manifest_version;
    const guardian_client *clients;
    size_t client_count;
    /* The service compiled from the same manifest; its per-helper limits times its record
     * capacity bound the whole epoch. NULL sets no epoch-wide limit (tests). */
    const service_policy *service;
    /* World-writable directories to purge besides /tmp, /var/tmp, /dev/shm, /dev/mqueue and
     * /run/lock, for example /var/crash on Ubuntu; may be NULL. */
    const char *const *purge_roots; /* At most GUARDIAN_PURGE_ROOT_LIMIT. */
    size_t purge_root_count;
    /* Optional caps on the whole subtree, every running epoch together; 0 leaves it
     * uncapped (then the administrator caps the subtree's parent instead). */
    uint64_t subtree_pids_max, subtree_memory_max;
} guardian_manifest;

typedef enum { GUARDIAN_READY, GUARDIAN_REFUSED, GUARDIAN_UNRESOLVED } guardian_result;

typedef struct {
    const guardian_manifest *manifest;
    gj_journal journal;
    int mount, subtree, epoch;      /* Owned descriptors, -1 when closed. */
    uint32_t operation;             /* The step that refused, for the journal-free diagnostic. */
    bool tainted[SERVICE_PAYLOAD_SLICES];  /* A slice whose purge left something: never handed out again. */
    int purging[SERVICE_PAYLOAD_SLICES];   /* pidfd of a slice's purge child, -1 when none runs. */
    bool purge_async;                      /* While serving: purges run in a child, the loop goes on. */
    bool repurge[SERVICE_PAYLOAD_SLICES];  /* A slice whose last purge stopped short: run again first. */
    uint64_t *heartbeat;                   /* Shared with purge children: one counter per slice. */
    uint64_t beat_seen[SERVICE_PAYLOAD_SLICES], beat_at[SERVICE_PAYLOAD_SLICES];
    bool stalled[SERVICE_PAYLOAD_SLICES];  /* A purge child killed for making no progress. */
    unsigned stall_round[SERVICE_PAYLOAD_SLICES]; /* Stalls in a row: each doubles the next allowance. */
    int system_errno;
} guardian_state;

/* Steps 2-5 of the design: journal, hierarchy, cold recovery, a new durable epoch with
 * its branches created and delegated. READY leaves the state holding the epoch
 * directory; REFUSED leaves the journal CLEAN; UNRESOLVED leaves it RECOVERING. */
guardian_result guardian_prepare(guardian_state *state, const guardian_manifest *manifest);
/* Both are compiled in from the one manifest file. */
extern const service_policy service_manifest;
/* Installs the service's identity filter (guardian_seccomp_linux.c); needs no_new_privs. */
bool guardian_confine_identities(const service_policy *policy, uint32_t service_uid, uint32_t service_gid);
/* Removes files and SysV IPC objects the payload ranges own (guardian_purge_linux.c);
 * true when nothing they own remains. `slice` below SERVICE_PAYLOAD_SLICES is one epoch's
 * slice of every range, -1 all. Only once nothing runs as those IDs: after their epoch is
 * killed. */
typedef enum { PURGE_CLEAN = 0, PURGE_UNCLEAN = 1, PURGE_INCOMPLETE = 2 } guardian_purge_outcome;
guardian_purge_outcome guardian_purge_payloads(const guardian_manifest *manifest, int slice);
/* Ends every running purge child without waiting for its work (shutdown: the next start
 * purges everything before it serves). */
void guardian_purge_abandon(guardian_state *state);
/* Waits for `slice`'s purge child, taints the slice if it left anything, frees the slot. */
void guardian_purge_reap(guardian_state *state, int slice);
/* Starts the purge again of every slice whose last one stopped short and is not running. */
void guardian_purge_resume(guardian_state *state);
/* Kills every purge child that made no progress for a minute (it runs again); the poll
 * timeout until the next look, -1 when no purge runs. */
int guardian_purge_watch(guardian_state *state);
/* Set in a purge child to its slice's counter; the purge bumps it as it goes. */
extern uint64_t *guardian_purge_heartbeat;
/* In a purge child: a private mount namespace of its own, so the purge may detach the mounts
 * below each root (guardian_purge_linux.c). False leaves mounts in place and skipped. */
bool guardian_purge_unshare(void);
#define GUARDIAN_PURGE_NONE (-2) /* guardian_recover: the epoch never ran, nothing to purge. */
/* Refuses a manifest the service would refuse, or whose payload IDs anyone else holds: below
 * 1000, or known to the host's user and group databases. Run before anything starts. */
bool guardian_manifest_valid(const guardian_manifest *manifest);
/* The manifest's purge roots alone (part of guardian_manifest_valid): each under directories
 * only root can change and, when it exists, a directory the purge would trust. */
bool guardian_purge_roots_valid(const guardian_manifest *manifest);
/* No path the epoch needs lies under a root an epoch covers with its own tmpfs, each checked as
 * written and as resolved, roots too: the listener and the service executable, and with
 * `policies` each policy's executable and working directory (a working directory may be a root
 * itself, an empty one). Manifest validation checks all; each epoch start checks the first two
 * again, so a policy path another user could reach never stops every epoch. */
bool guardian_private_roots_hide_nothing(const guardian_manifest *manifest, bool policies);
#ifndef MS_NOSYMFOLLOW
#define MS_NOSYMFOLLOW 256
#endif
#ifndef ST_NOSYMFOLLOW
#define ST_NOSYMFOLLOW 8192
#endif
/* The mount flags of an epoch's tmpfs over a root whose host mount reports `host` (statvfs's
 * f_flag): never set-ID or devices, and noexec, nosymfollow and read-only as the host's. */
static inline unsigned long guardian_private_mount_flags(unsigned long host) {
    return MS_NOSUID | MS_NODEV | ((host & ST_NOEXEC) ? MS_NOEXEC : 0) |
        ((host & ST_NOSYMFOLLOW) ? MS_NOSYMFOLLOW : 0) | ((host & ST_RDONLY) ? MS_RDONLY : 0);
}
/* In the service's child, before it drops root: the epoch's own mount and IPC namespaces get
 * fresh tmpfs mounts over every purge root (guardian_private_linux.c). False: do not start. */
bool guardian_private_epoch(const guardian_manifest *manifest);
/* The default roots each epoch gets a private tmpfs over, and the purge walks, in order; NULL
 * past the last. /var/crash too: apport writes a crash report, core image included, owned by
 * the crashing UID there, whatever the core limit. */
#define GUARDIAN_PRIVATE_ROOTS 5
static inline const char *guardian_private_root(size_t index) {
    static const char *const roots[] = {"/tmp", "/var/tmp", "/dev/shm", "/run/lock", "/var/crash"};
    _Static_assert(sizeof(roots) / sizeof(roots[0]) == GUARDIAN_PRIVATE_ROOTS, "one name per private root");
    return index < GUARDIAN_PRIVATE_ROOTS ? roots[index] : NULL;
}
/* After a retiring epoch's service ended: kills and removes its branch, then removes what
 * its half of the payload IDs left. The journal does not track a retiring epoch. */
guardian_result guardian_reclaim_retired(guardian_state *state, const char *epoch, int slice);
/* Plans and creates the next epoch on a CLEAN journal (rollover after a drained one). */
guardian_result guardian_next_epoch(guardian_state *state);
/* Kills, waits for and removes the journaled branches, purges `slice` of the payload
 * ranges (-1 all, once nothing runs; GUARDIAN_PURGE_NONE none), then marks CLEAN. */
guardian_result guardian_recover(guardian_state *state, int slice);
void guardian_close(guardian_state *state);

typedef enum { FORWARD_IDLE, FORWARD_HANDED, FORWARD_REFUSED, FORWARD_CHANNEL_FAILED, FORWARD_HELD }
    guardian_forward_result;
/* guardian_forward_linux.c: principal and namespaces through the client's pidfd. */
bool guardian_client_verified(const guardian_manifest *manifest, const peer_identity *peer);
/* Accepts one pending client; hands it to the service only if verified. */
#define GUARDIAN_CLIENT_LIMIT 16  /* Listed client accounts, payload accounts included. */
#define GUARDIAN_PURGE_ROOT_LIMIT 16  /* Manifest purge roots beside the default ones. */

/* True when "/" and every directory above `path` are real directories, root's and not
 * writable by anyone else, sticky or not (in a sticky directory others may still create a
 * missing name): nobody but root can change what `path` names. */
static inline bool guardian_path_anchored(const char *path) {
    char ancestor[4096];
    size_t length = strlen(path);
    struct stat status;
    if (path[0] != '/' || length >= sizeof(ancestor) || lstat("/", &status) != 0 || status.st_uid != 0 ||
        (status.st_mode & (S_IWGRP | S_IWOTH))) return false;
    for (size_t end = 1; end < length; ++end) {
        if (path[end] != '/') continue;
        memcpy(ancestor, path, end);
        ancestor[end] = 0;
        if (lstat(ancestor, &status) != 0 || !S_ISDIR(status.st_mode) || status.st_uid != 0 ||
            (status.st_mode & (S_IWGRP | S_IWOTH))) return false;
    }
    return true;
}
#define GUARDIAN_ACCEPT_BURST 32  /* Connections one account may have handed over per second. */
/* Forgets every account's connection count (tests). */
void guardian_forward_reset_rates(void);
/* Where a verified client's connection goes: its channel, epoch and generation. */
typedef struct { int channel; no_id epoch; uint64_t generation; } guardian_target;
/* Where a verified client goes: dropped, sent to `target`, or held by the caller until an
 * epoch can take it. */
typedef enum { ROUTE_DROP, ROUTE_SEND, ROUTE_HOLD } guardian_route_result;
typedef guardian_route_result (*guardian_route)(void *context, const peer_identity *peer, guardian_target *target);
/* As guardian_forward, but each client goes where `route` sends it; `*used` names the
 * channel that was tried, and a held connection is returned in `*held` (FORWARD_HELD). */
guardian_forward_result guardian_forward_routed(int listener, const guardian_manifest *manifest,
                                                guardian_route route, void *context, int *used, int *held);
/* Hands one accepted connection to a service; never blocks. */
bool guardian_send_connection(int channel, int connection, no_id epoch, uint64_t generation);
/* Every verified client to one channel. It does not check a payload range's mount namespace
 * against an epoch (guardian_forward_routed's route does): for tests only. */
guardian_forward_result guardian_forward(int listener, int channel, const guardian_manifest *manifest, no_id epoch,
                                         uint64_t generation);
#endif
