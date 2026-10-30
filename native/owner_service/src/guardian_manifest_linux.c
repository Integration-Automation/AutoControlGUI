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
#include <unistd.h>
#include <ctype.h>

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

/* The spelling of an absolute name, in place: repeated and trailing slashes collapsed, "."
 * components dropped. Where a name leads is not decided here, so ".." stays. A relative name is
 * left as it is (every caller refuses one): rewriting it in place could write past its end. */
static void tidy(char *path) {
    if (path[0] != '/') return;
    char *out = path;
    const char *in = path;
    while (*in) {
        while (*in == '/') ++in;
        size_t length = strcspn(in, "/");
        if (length && !(length == 1 && in[0] == '.')) {
            *out++ = '/';
            memmove(out, in, length);
            out += length;
        }
        in += length;
    }
    if (out == path) *out++ = '/';
    *out = '\0';
}

/* `name` lies in either form of the root: at or below it, or with `strict` only below it. */
static bool in_root(char forms[][4096], int count, const char *name, bool strict) {
    for (int i = 0; i < count; ++i)
        if (under(name, forms[i], strict)) return true;
    return false;
}

/* True when `rest` holds a ".." component: below a name not made yet, where it leads depends
 * on what is made there later. */
static bool climbs(const char *rest) {
    for (const char *at = rest; (at = strstr(at, "..")) != NULL; at += 2)
        if ((at == rest || at[-1] == '/') && (at[2] == '/' || at[2] == '\0')) return true;
    return false;
}

/* Resolves `path` component by component, as the kernel does, following at most 40 links, and
 * is true as soon as any name it visits lies in the root: each directory on the way, each link,
 * each name a link leads through, and, once a name is not there yet, what lies below it as
 * written (a ".." there is refused). With `root_itself`, the final name may be the root itself
 * (only what lies below it counts). What it cannot resolve (too long, too many links, not readable) counts as
 * hidden. */
static bool walk_hides(char forms[][4096], int count, const char *path, bool root_itself) {
    char current[4096] = "", rest[8192], next[8192], target[4096], candidate[4096];
    if (snprintf(rest, sizeof(rest), "%s", path) >= (int)sizeof(rest)) return true;
    for (unsigned links = 0;;) {
        char *component = rest;
        while (*component == '/') ++component;
        if (!*component) return false;
        size_t length = strcspn(component, "/");
        char *after = component + length;
        while (*after == '/') ++after;
        bool final = *after == '\0';
        if (length <= 2 && !strncmp(component, "..", length)) {  /* "." or "..": no name visited. */
            char *slash = length == 2 ? strrchr(current, '/') : NULL;
            if (slash) *slash = '\0';
            memmove(rest, after, strlen(after) + 1);
            continue;
        }
        if (snprintf(candidate, sizeof(candidate), "%s/%.*s", current, (int)length, component) >=
            (int)sizeof(candidate) || in_root(forms, count, candidate, final && root_itself)) return true;
        struct stat entry;
        if (lstat(candidate, &entry) != 0) {
            if (errno != ENOENT) return true;
            /* Not there yet: the rest of the path lies below it as written, unless it climbs back
             * out with "..", which leads wherever what is made there later leads. */
            if (climbs(after) || snprintf(next, sizeof(next), "%s/%s", candidate, after) >= (int)sizeof(next))
                return true;
            tidy(next);
            return in_root(forms, count, next, root_itself);
        }
        if (S_ISLNK(entry.st_mode)) {
            ssize_t size = ++links > 40 ? -1 : readlink(candidate, target, sizeof(target) - 1);
            if (size <= 0 || size >= (ssize_t)sizeof(target) - 1) return true;  /* Empty, or perhaps cut. */
            target[size] = '\0';
            if (target[0] == '/') current[0] = '\0';  /* Otherwise it goes on from the link's directory. */
            if (snprintf(next, sizeof(next), "%s/%s", target, after) >= (int)sizeof(next)) return true;
            memcpy(rest, next, strlen(next) + 1);
            continue;
        }
        memcpy(current, candidate, strlen(candidate) + 1);
        memmove(rest, after, strlen(after) + 1);
    }
}

/* True when a tmpfs over `root` would stand over `path`: `root` as written or resolved,
 * both tidied (repeated slashes and "." dropped), against `path` as written and every name its
 * resolution visits (walk_hides). With `root_itself` (a scratch variable's directory) the path
 * may be the root itself: only what lies below it is hidden. */
static bool hides(const char *root, const char *path, bool root_itself) {
    char forms[2][4096], written[4096];
    if (snprintf(forms[0], sizeof(forms[0]), "%s", root) >= (int)sizeof(forms[0]) ||
        snprintf(written, sizeof(written), "%s", path) >= (int)sizeof(written)) return true;
    tidy(forms[0]);
    tidy(written);
    if (climbs(forms[0])) return true;  /* A root written with "..": where it leads is not known. */
    int count = realpath(root, forms[1]) ? 2 : 1;
    return in_root(forms, count, written, root_itself) || walk_hides(forms, count, written, root_itself);
}

/* True when any private root (default or the manifest's) would stand over `path`. */
static bool hidden(const guardian_manifest *manifest, const char *path, bool root_itself) {
    if (!path || path[0] != '/') return true;
    for (size_t i = 0; guardian_private_root(i); ++i)
        if (hides(guardian_private_root(i), path, root_itself)) return true;
    for (size_t i = 0; i < manifest->purge_root_count; ++i)
        if (!manifest->purge_roots[i] || manifest->purge_roots[i][0] != '/' ||
            hides(manifest->purge_roots[i], path, root_itself))
            return true;
    return false;
}

/* A relative part that reads as a path: no spaces, quotes, brackets or other program text. */
static bool path_like(const char *part) {
    for (const unsigned char *at = (const unsigned char *)part; *at; ++at)
        if (!isalnum(*at) && !strchr("._-+@%,~=/", *at)) return false;
    return true;
}

static bool named(const char *entry, const char *name) {
    size_t length = strlen(name);
    return !strncmp(entry, name, length) && entry[length] == '=';
}

/* An environment entry whose name ends in PATH or LIB: a search list, read for programs or code. */
static bool search_list(const char *entry) {
    const char *equals = strchr(entry, '=');
    size_t length = equals ? (size_t)(equals - entry) : strlen(entry);
    return (length >= 4 && !strncmp(entry + length - 4, "PATH", 4)) ||
        (length >= 3 && !strncmp(entry + length - 3, "LIB", 3));
}

/* True when one part of an argument or an environment value names something at or below a
 * private root: hidden from the epoch, or, a root itself, shared by every helper of the epoch,
 * which could plant what is read from there. Only a scratch variable (`scratch`: TMPDIR, TMP,
 * TEMP) may name a root itself. An absolute part is always judged. In a search list every part
 * is a directory: an empty or "." part is the policy's working directory and any other relative
 * part is judged from it. Elsewhere a relative part counts only when it holds a '/' and reads as
 * a path. */
static bool part_hidden(const guardian_manifest *manifest, const char *cwd, const char *part, bool search,
                        bool scratch) {
    if (part[0] == '/') return hidden(manifest, part, scratch);
    if (search && (!part[0] || !strcmp(part, "."))) return hidden(manifest, cwd, false);
    if (!search && (!path_like(part) || !strchr(part, '/'))) return false;
    char joined[4096];
    if (!cwd || snprintf(joined, sizeof(joined), "%s/%s", cwd, part) >= (int)sizeof(joined)) return true;
    return hidden(manifest, joined, scratch);
}

/* True when a fixed argument (`environment` false: the whole text, and what follows its first
 * '=') or an environment entry (its value) leads below a private root, alone or as one part of
 * a ':' list. Other shapes (a second '=', ',' lists, an option's value attached as in
 * -I/tmp/x) are not judged; the README says so. */
static bool names_hidden(const guardian_manifest *manifest, const char *cwd, const char *text, bool environment) {
    if (!text) return true;
    const char *equals = strchr(text, '=');
    const char *starts[] = {environment ? (equals ? equals + 1 : text) : text,
                            !environment && equals ? equals + 1 : NULL};
    bool search = environment && search_list(text);
    bool scratch = environment && (named(text, "TMPDIR") || named(text, "TMP") || named(text, "TEMP"));
    for (size_t s = 0; s < 2 && starts[s]; ++s) {
        char part[4096];
        for (const char *at = starts[s];;) {
            size_t length = strcspn(at, ":");
            if (length >= sizeof(part)) return true;
            memcpy(part, at, length);
            part[length] = '\0';
            if (part_hidden(manifest, cwd, part, search, scratch)) return true;
            if (at[length] != ':') break;
            at += length + 1;
        }
    }
    return false;
}

bool guardian_private_roots_hide_nothing(const guardian_manifest *manifest, bool policies) {
    if (hidden(manifest, manifest->listener_path, false) || hidden(manifest, manifest->service_executable, false))
        return false;
    const service_policy *service = policies ? manifest->service : NULL;
    for (size_t i = 0; service && i < service->policy_count; ++i) {
        const service_launch_policy *policy = &service->policies[i];
        if (hidden(manifest, policy->executable, false) || hidden(manifest, policy->cwd, false)) return false;
        for (size_t k = 0; k < policy->fixed_argc; ++k)
            if (!policy->fixed_argv || names_hidden(manifest, policy->cwd, policy->fixed_argv[k], false))
                return false;
        for (size_t k = 0; k < policy->envc; ++k)
            if (!policy->env || names_hidden(manifest, policy->cwd, policy->env[k], true)) return false;
    }
    return true;
}

bool guardian_manifest_valid(const guardian_manifest *manifest) {
    const service_policy *service = manifest->service;
    if (!service || !service_policy_valid(service) || manifest->client_count > GUARDIAN_CLIENT_LIMIT ||
        manifest->listener_gid == 0 || (service->socket_gid && manifest->listener_gid != service->socket_gid) ||
        !guardian_purge_roots_valid(manifest) || in_any_range(service, manifest->service_uid, manifest->service_gid))
        return false;
    if (!guardian_private_roots_hide_nothing(manifest, true)) {
        fprintf(stderr, "autocontrol-owner-guardian: the listener, the service executable, or a policy's "
                        "executable, directory, fixed argument or environment value leads under a root each "
                        "epoch covers with its own tmpfs, or cannot be resolved; the manifest is refused\n");
        return false;
    }
    for (size_t i = 0; i < manifest->client_count; ++i)
        if (!client_valid(service, &manifest->clients[i])) return false;
    for (size_t i = 0; i < service->policy_count; ++i)
        if (!unallocated(service->policies[i].payload_uid, service->policies[i].payload_gid)) return false;
    return true;
}
