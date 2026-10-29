#define _GNU_SOURCE
/* After an epoch is killed nothing runs as its payload IDs, so what those IDs left behind is
 * removed before the IDs are handed out again: files under the shared writable directories
 * and SysV IPC objects, as systemd does for DynamicUser with RemoveIPC. A later helper with
 * the same ID then finds nothing of an earlier one, and tmpfs pages a killed helper left
 * charged are released.
 *
 * Directories are walked by descriptor, never through a link or into another filesystem, and
 * entries are removed relative to the directory that was opened, so no rename on the way can
 * redirect a removal. Ownership is judged by user ID only. The walk is bounded: at most
 * PURGE_DEPTH directories are open at once. A payload-owned object that cannot be removed
 * (a directory deeper than the bound, or one another ID wrote into) is neutralised instead:
 * owned by root with mode 0, nothing below it is reachable to any payload ID again. An
 * object already gone counts as removed. Only an object that can be neither removed nor
 * neutralised makes the purge unclean. */
#include "guardian.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ipc.h>
#include <sys/msg.h>
#include <sys/sem.h>
#include <sys/shm.h>
#include <sys/stat.h>
#include <unistd.h>

#define PURGE_DEPTH 64

typedef struct { const service_policy *service; int slice; bool clean; } purge_scope;

/* `slice` below SERVICE_PAYLOAD_SLICES is one epoch's slice of every user-ID range; -1 all. */
static bool payload_uid(const purge_scope *scope, uint32_t uid) {
    uint32_t span = scope->slice < 0 ? SERVICE_PAYLOAD_IDS : SERVICE_EPOCH_IDS;
    for (size_t i = 0; i < scope->service->policy_count; ++i) {
        uint32_t low = scope->service->policies[i].payload_uid;
        if (scope->slice > 0) low += (uint32_t)scope->slice * SERVICE_EPOCH_IDS;
        if (uid >= low && uid - low < span) return true;
    }
    return false;
}

/* Root and mode 0 on the very directory the walk saw: opened without following a link and
 * checked by inode, so a name swapped for a link meanwhile is never the one changed. */
static bool neutralise_directory(int directory, const char *name, dev_t device, ino_t inode) {
    int opened = openat(directory, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (opened < 0) return errno == ENOENT;
    struct stat now;
    bool done = fstat(opened, &now) == 0 && now.st_dev == device && now.st_ino == inode &&
        fchown(opened, 0, 0) == 0 && fchmod(opened, 0) == 0;
    close(opened);
    return done;
}

/* Removes `name` from `directory`, or failing that takes it from every payload ID. */
static void remove_or_neutralise(purge_scope *scope, int directory, const char *name, const struct stat *seen) {
    bool is_directory = S_ISDIR(seen->st_mode);
    if (unlinkat(directory, name, is_directory ? AT_REMOVEDIR : 0) == 0 || errno == ENOENT) return;
    bool done = is_directory ? neutralise_directory(directory, name, seen->st_dev, seen->st_ino) :
        fchownat(directory, name, 0, 0, AT_SYMLINK_NOFOLLOW) == 0 || errno == ENOENT;
    if (done) fprintf(stderr, "autocontrol-owner-guardian: neutralised a payload leftover it could not remove\n");
    else scope->clean = false;
}

typedef struct { DIR *listing; size_t parent; char *name; bool owned; struct stat seen; } level;
typedef struct { level levels[PURGE_DEPTH]; size_t depth; } walk;

static void pop(purge_scope *scope, walk *state) {
    level done = state->levels[--state->depth];
    closedir(done.listing);
    if (done.owned) remove_or_neutralise(scope, dirfd(state->levels[done.parent].listing), done.name, &done.seen);
    free(done.name);
}

static void visit(purge_scope *scope, walk *state, dev_t device, const char *name) {
    size_t at = state->depth - 1;
    int directory = dirfd(state->levels[at].listing);
    struct stat status;
    if (fstatat(directory, name, &status, AT_SYMLINK_NOFOLLOW) != 0) return;
    bool owned = payload_uid(scope, status.st_uid);
    if (!S_ISDIR(status.st_mode) || status.st_dev != device) {
        if (owned) remove_or_neutralise(scope, directory, name, &status);
        return;
    }
    if (state->depth == PURGE_DEPTH) {
        /* Deeper than the walk goes: an owned directory is closed off whole; another ID's is
         * reported, since payload files below it stay out of reach. */
        if (owned) remove_or_neutralise(scope, directory, name, &status);
        else fprintf(stderr, "autocontrol-owner-guardian: purge stopped at a directory deeper than %d\n",
                     PURGE_DEPTH);
        return;
    }
    int child = openat(directory, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    struct stat opened;
    DIR *listing = NULL;
    if (child >= 0 && fstat(child, &opened) == 0 && opened.st_ino == status.st_ino && opened.st_dev == status.st_dev)
        listing = fdopendir(child);
    char *copy = listing ? strdup(name) : NULL;
    if (!listing || !copy) {
        if (listing) closedir(listing);
        else if (child >= 0) close(child);
        if (owned) remove_or_neutralise(scope, directory, name, &status);
        else fprintf(stderr, "autocontrol-owner-guardian: purge could not open a directory\n");
        return;
    }
    state->levels[state->depth++] = (level){listing, at, copy, owned, status};
}

/* A root may be a link (/dev/shm -> /run/shm on older systems): resolved once, and used
 * only when the directory it names is root's and others may write it only if sticky. */
static int open_root(const char *path) {
    char resolved[4096];
    if (!realpath(path, resolved)) return -1;
    int root = open(resolved, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    struct stat status;
    if (root >= 0 && (fstat(root, &status) != 0 || status.st_uid != 0 ||
                      ((status.st_mode & (S_IWGRP | S_IWOTH)) && !(status.st_mode & S_ISVTX)))) {
        close(root);
        return -1;
    }
    return root;
}

static void purge_tree(purge_scope *scope, const char *path) {
    int root = open_root(path);
    if (root < 0) return; /* Absent, or not a directory this guardian may trust. */
    struct stat status;
    DIR *listing = fstat(root, &status) == 0 ? fdopendir(root) : NULL;
    if (!listing) { close(root); return; }
    static walk state;
    state.depth = 0;
    state.levels[state.depth++] = (level){listing, 0, NULL, false, status};
    while (state.depth) {
        struct dirent *entry = readdir(state.levels[state.depth - 1].listing);
        if (!entry) {
            if (state.depth == 1) { closedir(state.levels[0].listing); break; }
            pop(scope, &state);
            continue;
        }
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, ".."))
            visit(scope, &state, status.st_dev, entry->d_name);
    }
}

/* Each /proc/sysvipc table: the ID column and the owner and creator user ID columns. */
static void purge_ipc(purge_scope *scope, const char *table, int kind) {
    FILE *file = fopen(table, "re");
    if (!file) return;
    char line[512];
    if (!fgets(line, sizeof(line), file)) { fclose(file); return; }
    while (fgets(line, sizeof(line), file)) {
        int key, id;
        unsigned uid = 0, cuid = 0;
        int fields = kind == 0 ? sscanf(line, "%d %d %*o %*u %*d %*d %*u %u %*u %u", &key, &id, &uid, &cuid) :
            kind == 1 ? sscanf(line, "%d %d %*o %*u %*u %*d %*d %u %*u %u", &key, &id, &uid, &cuid) :
            sscanf(line, "%d %d %*o %*u %u %*u %u", &key, &id, &uid, &cuid);
        if (fields != 4 || !(payload_uid(scope, uid) || payload_uid(scope, cuid))) continue;
        int rc = kind == 0 ? shmctl(id, IPC_RMID, NULL) : kind == 1 ? msgctl(id, IPC_RMID, NULL) :
            semctl(id, 0, IPC_RMID);
        if (rc != 0 && errno != EINVAL && errno != EIDRM) scope->clean = false;
    }
    fclose(file);
}

static const char *const default_roots[] = {"/tmp", "/var/tmp", "/dev/shm", "/dev/mqueue", "/run/lock"};

bool guardian_purge_payloads(const guardian_manifest *manifest, int slice) {
    const service_policy *service = manifest->service;
    if (!service) return true;
    purge_scope scope = {service, slice, true};
    for (size_t i = 0; i < sizeof(default_roots) / sizeof(default_roots[0]); ++i) purge_tree(&scope, default_roots[i]);
    for (size_t i = 0; i < manifest->purge_root_count; ++i) purge_tree(&scope, manifest->purge_roots[i]);
    purge_ipc(&scope, "/proc/sysvipc/shm", 0);
    purge_ipc(&scope, "/proc/sysvipc/msg", 1);
    purge_ipc(&scope, "/proc/sysvipc/sem", 2);
    return scope.clean;
}
