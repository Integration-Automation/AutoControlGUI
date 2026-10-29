#ifndef AUTOCONTROL_GUARDIAN_H
#define AUTOCONTROL_GUARDIAN_H
/* The root guardian: the only party that creates, delegates, grants and reclaims a
 * service epoch. Private to the guardian executable. */
#include "guardian_journal.h"
#include "native_service.h"
#include <stdbool.h>
#include <stdint.h>
#include <sys/types.h>

/* A client account and the namespaces its processes must live in. */
typedef struct { uint32_t uid, gid; service_namespaces namespaces; } guardian_client;

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
} guardian_manifest;

typedef enum { GUARDIAN_READY, GUARDIAN_REFUSED, GUARDIAN_UNRESOLVED } guardian_result;

typedef struct {
    const guardian_manifest *manifest;
    gj_journal journal;
    int mount, subtree, epoch;      /* Owned descriptors, -1 when closed. */
    uint32_t operation;             /* The step that refused, for the journal-free diagnostic. */
    int system_errno;
} guardian_state;

/* Steps 2-5 of the design: journal, hierarchy, cold recovery, a new durable epoch with
 * its branches created and delegated. READY leaves the state holding the epoch
 * directory; REFUSED leaves the journal CLEAN; UNRESOLVED leaves it RECOVERING. */
guardian_result guardian_prepare(guardian_state *state, const guardian_manifest *manifest);
/* Kills, waits for and removes the journaled branches, then marks CLEAN. */
guardian_result guardian_recover(guardian_state *state);
void guardian_close(guardian_state *state);

typedef enum { FORWARD_IDLE, FORWARD_HANDED, FORWARD_REFUSED, FORWARD_CHANNEL_FAILED } guardian_forward_result;
/* guardian_forward_linux.c: principal and namespaces through the client's pidfd. */
bool guardian_client_verified(const guardian_manifest *manifest, const peer_identity *peer);
/* Accepts one pending client; hands it to the service only if verified. */
guardian_forward_result guardian_forward(int listener, int channel, const guardian_manifest *manifest, no_id epoch,
                                         uint64_t generation);
#endif
