#define _GNU_SOURCE
/* After an epoch is killed nothing runs as its payload IDs, so what those IDs left behind is
 * removed before the IDs are handed out again: files under the shared writable directories
 * and SysV IPC objects, as systemd does for DynamicUser with RemoveIPC. A later helper with
 * the same ID then finds nothing of an earlier one, and tmpfs pages a killed helper left
 * charged are released.
 *
 * Directories are walked by descriptor, never through a link or into another filesystem, and
 * entries are removed relative to the directory that was opened. Ownership is judged by user
 * ID only. At most PURGE_DEPTH directories are open at once. A payload-owned directory that
 * cannot be removed where it is (deeper than the walk, or another ID wrote into it) is moved
 * whole into a quarantine directory only root can enter, on the same filesystem, after its
 * inode is checked; its name is free again at once. Quarantined directories are then walked
 * from their own top, again and again, so a chain of any depth is taken apart PURGE_DEPTH
 * levels at a time until only what other IDs own is left there, out of every payload's
 * reach. A name that vanished or changed meanwhile is never an error: another ID moved it,
 * and the next purge meets it wherever it went. */
#include "guardian.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/fs.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ipc.h>
#include <sys/msg.h>
#include <sys/sem.h>
#include <sys/shm.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

#ifndef SYS_fchmodat2
#define SYS_fchmodat2 452 /* The same number on every architecture. */
#endif
#define PURGE_DEPTH 64
#define QUARANTINE ".autocontrol-owner-quarantine"
#define QUARANTINE_PASSES 65536 /* Each pass takes PURGE_DEPTH levels off the deepest chain. */
#define DEFERRED_LIMIT 256      /* Other IDs' directories at the depth bound, walked from their own top. */

typedef struct {
    const service_policy *service;
    int slice;
    bool clean;
    int quarantine;        /* Root-only directory on the walked filesystem, or -1. */
    struct stat quarantined; /* Its identity: nothing already in it is moved again. */
    unsigned long moved;   /* Directories moved into the quarantine this pass. */
    int deferred[DEFERRED_LIMIT]; /* Opened, not-owned directories at the depth bound. */
    size_t deferred_count;
} purge_scope;

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

/* True when `name` in `directory` is still the object the walk saw. */
static bool still_seen(int directory, const char *name, const struct stat *seen) {
    struct stat now;
    return fstatat(directory, name, &now, AT_SYMLINK_NOFOLLOW) == 0 && now.st_dev == seen->st_dev &&
        now.st_ino == seen->st_ino;
}

/* Moves the object the walk saw into the quarantine under a fresh name. A name that
 * changed meanwhile is left alone; one moved by mistake is moved back. */
static bool quarantine(purge_scope *scope, int directory, const char *name, const struct stat *seen) {
    struct stat parent;
    if (scope->quarantine < 0 || !still_seen(directory, name, seen) || fstat(directory, &parent) != 0 ||
        (parent.st_dev == scope->quarantined.st_dev && parent.st_ino == scope->quarantined.st_ino)) return false;
    /* Quarantined leftovers outlive the guardian that moved them, and a later guardian may
     * reuse its PID: names also carry the clock, and a taken one is simply skipped. */
    static unsigned long serial;
    char fresh[96];
    long moved = -1;
    for (int attempt = 0; attempt < 64 && moved != 0; ++attempt) {
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        snprintf(fresh, sizeof(fresh), "q-%ld-%lld%09ld-%lu", (long)getpid(), (long long)now.tv_sec, now.tv_nsec,
                 ++serial);
        moved = syscall(SYS_renameat2, directory, name, scope->quarantine, fresh, RENAME_NOREPLACE);
        if (moved != 0 && errno != EEXIST) return false;
    }
    if (moved != 0) return false;
    if (!still_seen(scope->quarantine, fresh, seen)) {
        syscall(SYS_renameat2, scope->quarantine, fresh, directory, name, RENAME_NOREPLACE);
        return false;
    }
    ++scope->moved;
    return true;
}

/* Removes the payload-owned object the walk saw, or takes it out of every payload's reach.
 * Only an object that is still there and can be neither removed nor moved nor closed off
 * makes the purge unclean. */
static void dispose(purge_scope *scope, int directory, const char *name, const struct stat *seen) {
    bool is_directory = S_ISDIR(seen->st_mode);
    if (!still_seen(directory, name, seen)) return; /* Moved or replaced by another ID. */
    if (unlinkat(directory, name, is_directory ? AT_REMOVEDIR : 0) == 0 || errno == ENOENT) return;
    if (quarantine(scope, directory, name, seen) || !still_seen(directory, name, seen)) return;
    /* No quarantine here: close it off where it is, on the opened, checked object. */
    int opened = openat(directory, name, O_PATH | O_NOFOLLOW | O_CLOEXEC);
    struct stat now;
    bool done = opened >= 0 && fstat(opened, &now) == 0 && now.st_dev == seen->st_dev &&
        now.st_ino == seen->st_ino && fchownat(opened, "", 0, 0, AT_EMPTY_PATH) == 0 &&
        syscall(SYS_fchmodat2, opened, "", 0, AT_EMPTY_PATH) == 0;
    if (opened >= 0) close(opened);
    if (done) fprintf(stderr, "autocontrol-owner-guardian: closed off a payload leftover it could not move\n");
    else if (still_seen(directory, name, seen)) scope->clean = false;
}

typedef struct { DIR *listing; size_t parent; char *name; bool owned; struct stat seen; } level;
typedef struct { level levels[PURGE_DEPTH]; size_t depth; } walk;

static void pop(purge_scope *scope, walk *state) {
    level done = state->levels[--state->depth];
    closedir(done.listing);
    if (done.owned) dispose(scope, dirfd(state->levels[done.parent].listing), done.name, &done.seen);
    free(done.name);
}

static void visit(purge_scope *scope, walk *state, dev_t device, const char *name) {
    size_t at = state->depth - 1;
    int directory = dirfd(state->levels[at].listing);
    if (at == 0 && !strcmp(name, QUARANTINE)) return; /* Walked on its own, after the root. */
    struct stat status;
    if (fstatat(directory, name, &status, AT_SYMLINK_NOFOLLOW) != 0) return;
    bool owned = payload_uid(scope, status.st_uid);
    if (!S_ISDIR(status.st_mode) || status.st_dev != device) {
        if (owned) dispose(scope, directory, name, &status);
        return;
    }
    if (state->depth == PURGE_DEPTH) {
        /* Deeper than the walk goes. An owned directory is moved whole and taken apart from
         * its own top; another ID's stays where it is and is walked later from its own top. */
        if (owned) { dispose(scope, directory, name, &status); return; }
        int deeper = openat(directory, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        struct stat seen;
        if (deeper >= 0 && fstat(deeper, &seen) == 0 && seen.st_ino == status.st_ino &&
            seen.st_dev == status.st_dev && scope->deferred_count < DEFERRED_LIMIT) {
            scope->deferred[scope->deferred_count++] = deeper;
        } else {
            if (deeper >= 0) close(deeper);
            fprintf(stderr, "autocontrol-owner-guardian: purge left a directory deeper than %d unwalked\n",
                    PURGE_DEPTH);
        }
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
        if (owned) dispose(scope, directory, name, &status);
        else fprintf(stderr, "autocontrol-owner-guardian: purge could not open a directory\n");
        return;
    }
    state->levels[state->depth++] = (level){listing, at, copy, owned, status};
}

/* Walks one opened directory; `top` is closed when done. */
static void walk_directory(purge_scope *scope, int top) {
    struct stat status;
    DIR *listing = fstat(top, &status) == 0 ? fdopendir(top) : NULL;
    if (!listing) { close(top); return; }
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

/* The root's quarantine: root's, mode 0700, a real directory; created when missing. */
static int open_quarantine(int root) {
    if (mkdirat(root, QUARANTINE, 0700) != 0 && errno != EEXIST) return -1;
    int quarantine = openat(root, QUARANTINE, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    struct stat status;
    if (quarantine >= 0 && (fstat(quarantine, &status) != 0 || status.st_uid != 0 ||
                            fchmod(quarantine, 0700) != 0)) {
        close(quarantine);
        return -1;
    }
    return quarantine;
}

static void purge_tree(purge_scope *scope, const char *path) {
    int root = open_root(path);
    if (root < 0) return; /* Absent, or not a directory this guardian may trust. */
    scope->quarantine = open_quarantine(root);
    if (scope->quarantine >= 0 && fstat(scope->quarantine, &scope->quarantined) != 0) {
        close(scope->quarantine);
        scope->quarantine = -1;
    }
    walk_directory(scope, dup(root));
    /* Other IDs' deep directories, each from its own top; walking one may defer more. */
    while (scope->deferred_count) walk_directory(scope, scope->deferred[--scope->deferred_count]);
    /* Take quarantined chains apart until a pass moves nothing deeper out. */
    for (unsigned pass = 0; scope->quarantine >= 0 && pass < QUARANTINE_PASSES; ++pass) {
        scope->moved = 0;
        int listing = dup(scope->quarantine);
        if (listing < 0) break;
        walk_directory(scope, listing);
        if (!scope->moved) break;
    }
    if (scope->quarantine >= 0) close(scope->quarantine);
    scope->quarantine = -1;
    close(root);
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
    purge_scope scope = {.service = service, .slice = slice, .clean = true, .quarantine = -1};
    for (size_t i = 0; i < sizeof(default_roots) / sizeof(default_roots[0]); ++i) purge_tree(&scope, default_roots[i]);
    for (size_t i = 0; i < manifest->purge_root_count; ++i) purge_tree(&scope, manifest->purge_roots[i]);
    purge_ipc(&scope, "/proc/sysvipc/shm", 0);
    purge_ipc(&scope, "/proc/sysvipc/msg", 1);
    purge_ipc(&scope, "/proc/sysvipc/sem", 2);
    return scope.clean;
}
