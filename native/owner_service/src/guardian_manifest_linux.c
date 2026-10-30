#define _GNU_SOURCE
/* The guardian's own judgement of the compiled manifest, before it builds the identity
 * filter or starts anything: the service would refuse it later, but by then the filter
 * built from it already runs. */
#include "guardian.h"
#include <sys/stat.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <grp.h>
#include <pwd.h>

#define PAYLOAD_ID_FLOOR 1000u /* Below it: system accounts and groups, such as disk or adm. */

/* No ID of the range is known to the host's databases: an allocated one could be a system
 * group (disk is root-equivalent) or a real user whose files the purge would remove. */
static bool lookup_failed(int error) {
    return error != 0 && error != ENOENT && error != ESRCH && error != EBADF && error != EPERM;
}

static bool unallocated(uint32_t uid_base, uint32_t gid_base) {
    if (uid_base < PAYLOAD_ID_FLOOR || gid_base < PAYLOAD_ID_FLOOR) return false;
    for (uint32_t k = 0; k < SERVICE_PAYLOAD_IDS; ++k) {
        /* NULL with a real error (an LDAP or sssd outage) is refused too; the codes the
         * manual lists for "not found" are not errors. */
        errno = 0;
        if (getpwuid(uid_base + k) || lookup_failed(errno)) return false;
        errno = 0;
        if (getgrgid(gid_base + k) || lookup_failed(errno)) return false;
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

/* What an existing purge root resolves to must be a directory the purge would trust: root's,
 * and writable by others only if sticky. */
static bool trusted_directory(const char *resolved) {
    struct stat status;
    return lstat(resolved, &status) == 0 && S_ISDIR(status.st_mode) && status.st_uid == 0 &&
        (!(status.st_mode & (S_IWGRP | S_IWOTH)) || (status.st_mode & S_ISVTX));
}

bool guardian_purge_roots_valid(const guardian_manifest *manifest) {
    if ((manifest->purge_root_count && !manifest->purge_roots) ||
        manifest->purge_root_count > GUARDIAN_PURGE_ROOT_LIMIT) return false;
    for (size_t i = 0; i < manifest->purge_root_count; ++i) {
        const char *path = manifest->purge_roots[i];
        if (!path || path[0] != '/') return false;
        /* The path as written, and what an existing one resolves to: a link into a user's
         * directory, a user's own directory, or a link loop would otherwise be skipped, or
         * hold the purge incomplete, at every purge. A root that does not exist yet is fine. */
        char resolved[4096];
        bool exists = realpath(path, resolved) != NULL;
        bool missing = !exists && (errno == ENOENT || errno == ENOTDIR);
        if (!guardian_path_anchored(path) || (!exists && !missing) ||
            (exists && (!guardian_path_anchored(resolved) || !trusted_directory(resolved)))) {
            fprintf(stderr, "autocontrol-owner-guardian: purge root %s is refused: it must sit under directories "
                            "only root can change and, if it exists, be a directory the purge trusts\n", path);
            return false;
        }
    }
    return true;
}

static bool under(const char *path, const char *root) {
    size_t length = strlen(root);
    return strncmp(path, root, length) == 0 && (path[length] == '/' || path[length] == '\0');
}

/* The listener must not lie under a root each epoch covers with its own tmpfs: helpers in the
 * epoch would not see it. Checked as written and, when its directory exists, as resolved. */
bool guardian_listener_outside_private_roots(const guardian_manifest *manifest) {
    const char *path = manifest->listener_path;
    char directory[4096], resolved[4096];
    if (!path || snprintf(directory, sizeof(directory), "%s", path) >= (int)sizeof(directory)) return false;
    char *slash = strrchr(directory, '/');
    if (slash) *(slash == directory ? slash + 1 : slash) = '\0';
    bool known = realpath(directory, resolved) != NULL;
    for (size_t i = 0; guardian_private_root(i); ++i)
        if (under(path, guardian_private_root(i)) || (known && under(resolved, guardian_private_root(i))))
            return false;
    for (size_t i = 0; i < manifest->purge_root_count; ++i)
        if (manifest->purge_roots[i] && (under(path, manifest->purge_roots[i]) ||
                                         (known && under(resolved, manifest->purge_roots[i])))) return false;
    return true;
}

bool guardian_manifest_valid(const guardian_manifest *manifest) {
    const service_policy *service = manifest->service;
    if (!service || !service_policy_valid(service) || manifest->client_count > GUARDIAN_CLIENT_LIMIT ||
        manifest->listener_gid == 0 || (service->socket_gid && manifest->listener_gid != service->socket_gid) ||
        !guardian_purge_roots_valid(manifest) || in_any_range(service, manifest->service_uid, manifest->service_gid))
        return false;
    if (!guardian_listener_outside_private_roots(manifest)) {
        fprintf(stderr, "autocontrol-owner-guardian: listener %s is refused: it lies under a root each epoch "
                        "covers with its own tmpfs\n", manifest->listener_path ? manifest->listener_path : "(none)");
        return false;
    }
    for (size_t i = 0; i < manifest->client_count; ++i)
        if (!client_valid(service, &manifest->clients[i])) return false;
    for (size_t i = 0; i < service->policy_count; ++i)
        if (!unallocated(service->policies[i].payload_uid, service->policies[i].payload_gid)) return false;
    return true;
}
