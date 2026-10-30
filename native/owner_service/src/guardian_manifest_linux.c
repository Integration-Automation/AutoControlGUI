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

/* `path` is `root` or below it; with `strict`, only below it. */
static bool under(const char *path, const char *root, bool strict) {
    size_t length = strlen(root);
    if (length == 1 && root[0] == '/') return path[0] == '/' && (!strict || path[1] != '\0');
    return strncmp(path, root, length) == 0 && (path[length] == '/' || (!strict && path[length] == '\0'));
}

static void drop_trailing_slashes(char *path) {
    size_t length = strlen(path);
    while (length > 1 && path[length - 1] == '/') path[--length] = '\0';
}

/* True when a tmpfs over `root` would stand over `path`. `root` is taken as written and as
 * resolved, trailing slashes dropped from both. `path` is taken as written and then each of
 * its prefixes, itself first, as resolved: a resolved prefix in a root puts the path in it,
 * whatever does not exist yet below that prefix and whatever links lie on the way. A prefix
 * that is there but does not resolve (a dangling link, a loop) could resolve into a root later,
 * so it is refused. A directory the epoch enters (`directory_path`) may be the root itself:
 * only the path as a whole is compared strictly, every proper prefix as at or below. */
static bool hides(const char *root, const char *path, bool directory_path) {
    char forms[2][4096], written[4096], prefix[4096], resolved[4096];
    if (snprintf(forms[0], sizeof(forms[0]), "%s", root) >= (int)sizeof(forms[0]) ||
        snprintf(written, sizeof(written), "%s", path) >= (int)sizeof(written)) return true;
    drop_trailing_slashes(forms[0]);
    drop_trailing_slashes(written);
    int count = realpath(root, forms[1]) ? 2 : 1;
    for (int i = 0; i < count; ++i)
        if (under(written, forms[i], directory_path)) return true;
    memcpy(prefix, written, strlen(written) + 1);
    for (bool whole = true;; whole = false) {
        struct stat entry;
        if (realpath(prefix, resolved)) {
            for (int i = 0; i < count; ++i)
                if (under(resolved, forms[i], whole && directory_path)) return true;
        } else if (lstat(prefix, &entry) == 0) {
            return true;
        }
        char *slash = strrchr(prefix, '/');
        if (!slash || (slash == prefix && prefix[1] == '\0')) return false;
        *(slash == prefix ? slash + 1 : slash) = '\0';
    }
}

/* True when any private root (default or the manifest's) would stand over `path`. */
static bool hidden(const guardian_manifest *manifest, const char *path, bool directory_path) {
    if (!path || path[0] != '/') return true;
    for (size_t i = 0; guardian_private_root(i); ++i)
        if (hides(guardian_private_root(i), path, directory_path)) return true;
    for (size_t i = 0; i < manifest->purge_root_count; ++i)
        if (!manifest->purge_roots[i] || manifest->purge_roots[i][0] != '/' ||
            hides(manifest->purge_roots[i], path, directory_path))
            return true;
    return false;
}

bool guardian_private_roots_hide_nothing(const guardian_manifest *manifest, bool policies) {
    if (hidden(manifest, manifest->listener_path, false) || hidden(manifest, manifest->service_executable, false))
        return false;
    const service_policy *service = policies ? manifest->service : NULL;
    for (size_t i = 0; service && i < service->policy_count; ++i)
        if (hidden(manifest, service->policies[i].executable, false) ||
            hidden(manifest, service->policies[i].cwd, true)) return false;
    return true;
}

bool guardian_manifest_valid(const guardian_manifest *manifest) {
    const service_policy *service = manifest->service;
    if (!service || !service_policy_valid(service) || manifest->client_count > GUARDIAN_CLIENT_LIMIT ||
        manifest->listener_gid == 0 || (service->socket_gid && manifest->listener_gid != service->socket_gid) ||
        !guardian_purge_roots_valid(manifest) || in_any_range(service, manifest->service_uid, manifest->service_gid))
        return false;
    if (!guardian_private_roots_hide_nothing(manifest, true)) {
        fprintf(stderr, "autocontrol-owner-guardian: the listener, the service executable or a policy's "
                        "executable or directory lies under a root each epoch covers with its own tmpfs; "
                        "the manifest is refused\n");
        return false;
    }
    for (size_t i = 0; i < manifest->client_count; ++i)
        if (!client_valid(service, &manifest->clients[i])) return false;
    for (size_t i = 0; i < service->policy_count; ++i)
        if (!unallocated(service->policies[i].payload_uid, service->policies[i].payload_gid)) return false;
    return true;
}
