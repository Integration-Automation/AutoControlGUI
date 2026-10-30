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
 * whole, after its identity is checked, into a quarantine: a directory only root can enter,
 * created on the same filesystem under a random name when first needed and recognised by its
 * inode, never by its name. Its name is free again at once. The quarantine is then walked
 * from its own top, pass after pass, so a chain of any depth is taken apart PURGE_DEPTH
 * levels at a time; what other IDs own is all that may stay there, out of every payload's
 * reach, and an emptied quarantine is removed. A name that vanished or changed meanwhile is
 * never an error: another ID moved it, and the next purge meets it wherever it went.
 *
 * One root's purge reads at most PURGE_BUDGET entries, so a live local user who keeps
 * renaming names under the walk cannot hold it forever; a purge that stopped short, or had
 * no quarantine when it needed one, reports itself incomplete and is run again before its
 * slice is handed out. Only an object that can be neither removed, moved nor closed off
 * makes it unclean. */
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
#include <sys/random.h>
#include <sys/sem.h>
#include <sys/shm.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

#ifndef SYS_fchmodat2
#define SYS_fchmodat2 452 /* The same number on every architecture. */
#endif
#define PURGE_DEPTH 64
#define QUARANTINE_PREFIX ".autocontrol-owner-quarantine"
#define QUARANTINE_PASSES 4096   /* Each pass takes PURGE_DEPTH levels off the deepest chain. */
#define DEFERRED_LIMIT 256       /* Other IDs' directories at the depth bound, walked from their own top. */
#define PURGE_BUDGET (1UL << 22) /* Directory entries one root's purge reads before it stops. */

typedef struct {
    const service_policy *service;
    int slice;
    bool clean, complete;
    int root;                     /* The root being purged: the quarantine is made in it. */
    bool quarantine_tried;
    int quarantine;               /* Root-only directory on the walked filesystem, or -1. */
    char quarantine_name[64];
    struct stat quarantined;      /* Its identity: it is skipped, and nothing in it moves again. */
    unsigned long moved;          /* Directories moved into the quarantine this pass. */
    unsigned long budget;         /* Entries this root's purge may still read. */
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

static bool same_inode(const struct stat *a, const struct stat *b) {
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino;
}

/* True when `name` in `directory` is still the object the walk saw, with the same owner. */
static bool still_seen(int directory, const char *name, const struct stat *seen) {
    struct stat now;
    return fstatat(directory, name, &now, AT_SYMLINK_NOFOLLOW) == 0 && same_inode(&now, seen) &&
        now.st_uid == seen->st_uid;
}

static bool is_quarantine(const purge_scope *scope, int directory) {
    struct stat status;
    return scope->quarantine >= 0 && fstat(directory, &status) == 0 && same_inode(&status, &scope->quarantined);
}

/* The quarantine, made on first need under a fresh random name: nobody can have taken it
 * beforehand, and a name somebody else made is just another directory to walk. */
static bool have_quarantine(purge_scope *scope) {
    if (scope->quarantine >= 0) return true;
    if (scope->quarantine_tried) return false;
    scope->quarantine_tried = true;
    for (int attempt = 0; attempt < 16; ++attempt) {
        unsigned char bytes[8];
        if (getrandom(bytes, sizeof(bytes), 0) != (ssize_t)sizeof(bytes)) return false;
        char *name = scope->quarantine_name;
        int at = snprintf(name, sizeof(scope->quarantine_name), "%s-", QUARANTINE_PREFIX);
        for (size_t i = 0; i < sizeof(bytes); ++i) at += snprintf(name + at, 3, "%02x", bytes[i]);
        if (mkdirat(scope->root, name, 0700) != 0) {
            if (errno == EEXIST) continue;
            return false;
        }
        int quarantine = openat(scope->root, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        struct stat status;
        if (quarantine >= 0 && fchmod(quarantine, 0700) == 0 && fstat(quarantine, &status) == 0 &&
            status.st_uid == 0) {
            scope->quarantine = quarantine;
            scope->quarantined = status;
            return true;
        }
        if (quarantine >= 0) close(quarantine);
        return false;
    }
    return false;
}

/* Moves the object the walk saw into the quarantine under a fresh name. A name that changed
 * meanwhile is left alone; one moved by mistake is moved back. */
static bool quarantine(purge_scope *scope, int directory, const char *name, const struct stat *seen) {
    if (is_quarantine(scope, directory) || !have_quarantine(scope) || !still_seen(directory, name, seen))
        return false;
    static unsigned long serial;
    char fresh[48];
    long moved = -1;
    for (int attempt = 0; attempt < 64 && moved != 0; ++attempt) {
        snprintf(fresh, sizeof(fresh), "q-%lu", ++serial);
        moved = syscall(SYS_renameat2, directory, name, scope->quarantine, fresh, RENAME_NOREPLACE);
        if (moved != 0 && errno != EEXIST) return false;
    }
    if (moved != 0) return false;
    if (!still_seen(scope->quarantine, fresh, seen)) {
        if (syscall(SYS_renameat2, scope->quarantine, fresh, directory, name, RENAME_NOREPLACE) != 0)
            fprintf(stderr, "autocontrol-owner-guardian: an object swapped in during a move stays quarantined\n");
        return false;
    }
    ++scope->moved;
    return true;
}

/* Removes the payload-owned object the walk saw, or takes it out of every payload's reach. */
static void dispose(purge_scope *scope, int directory, const char *name, const struct stat *seen) {
    bool is_directory = S_ISDIR(seen->st_mode);
    if (!still_seen(directory, name, seen)) return; /* Moved or replaced by another ID. */
    if (unlinkat(directory, name, is_directory ? AT_REMOVEDIR : 0) == 0 || errno == ENOENT) return;
    if (quarantine(scope, directory, name, seen) || !still_seen(directory, name, seen)) return;
    /* Close it off where it is, on the opened, checked object: mode 0 first, so a failure
     * never leaves a root-owned object others may write. */
    int opened = openat(directory, name, O_PATH | O_NOFOLLOW | O_CLOEXEC);
    struct stat now;
    bool done = opened >= 0 && fstat(opened, &now) == 0 && same_inode(&now, seen) &&
        syscall(SYS_fchmodat2, opened, "", 0, AT_EMPTY_PATH) == 0 && fchownat(opened, "", 0, 0, AT_EMPTY_PATH) == 0;
    if (opened >= 0) close(opened);
    if (!done) {
        if (still_seen(directory, name, seen)) scope->clean = false;
        return;
    }
    if (is_quarantine(scope, directory)) return; /* Already out of reach: what another ID wrote stays. */
    fprintf(stderr, "autocontrol-owner-guardian: closed off a payload leftover it could not move\n");
    /* Without a quarantine its name stays taken and what lies below is not freed: run again. */
    if (is_directory && scope->quarantine < 0) scope->complete = false;
}

/* `quarantined`: the level lies in a quarantine, this one or an earlier one, where nothing is
 * any payload's and an emptied directory, whoever's, is removed. */
typedef struct { DIR *listing; size_t parent; char *name; bool owned, quarantined; struct stat seen; } level;
typedef struct { level levels[PURGE_DEPTH]; size_t depth; } walk;

static void pop(purge_scope *scope, walk *state) {
    level done = state->levels[--state->depth];
    closedir(done.listing);
    int parent = dirfd(state->levels[done.parent].listing);
    if (done.owned) dispose(scope, parent, done.name, &done.seen);
    else if (done.quarantined && still_seen(parent, done.name, &done.seen)) unlinkat(parent, done.name, AT_REMOVEDIR);
    free(done.name);
}

/* An earlier quarantine: root's, mode 0700, a directory at the root's top with the prefix.
 * Walked like any other directory and removed once empty. */
static bool earlier_quarantine(const struct stat *status, const char *name) {
    return S_ISDIR(status->st_mode) && status->st_uid == 0 && (status->st_mode & 07777) == 0700 &&
        !strncmp(name, QUARANTINE_PREFIX, strlen(QUARANTINE_PREFIX));
}

/* Deeper than the walk goes: an owned directory is moved whole and taken apart from its own
 * top; another ID's stays where it is and is walked later from its own top. */
static void at_depth_bound(purge_scope *scope, int directory, const char *name, const struct stat *status,
                           bool owned) {
    if (owned) { dispose(scope, directory, name, status); return; }
    int deeper = openat(directory, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    struct stat seen;
    if (deeper >= 0 && fstat(deeper, &seen) == 0 && same_inode(&seen, status) && scope->deferred_count < DEFERRED_LIMIT) {
        scope->deferred[scope->deferred_count++] = deeper;
        return;
    }
    if (deeper >= 0) close(deeper);
    /* Payload files there were put inside another ID's directory, with that ID's leave. */
    fprintf(stderr, "autocontrol-owner-guardian: purge left another ID's directory deeper than %d unwalked\n",
            PURGE_DEPTH);
}

static void visit(purge_scope *scope, walk *state, dev_t device, bool root_walk, const char *name) {
    size_t at = state->depth - 1;
    int directory = dirfd(state->levels[at].listing);
    struct stat status;
    if (fstatat(directory, name, &status, AT_SYMLINK_NOFOLLOW) != 0) return;
    if (at == 0 && scope->quarantine >= 0 && same_inode(&status, &scope->quarantined)) return; /* Walked later. */
    bool owned = payload_uid(scope, status.st_uid);
    if (!S_ISDIR(status.st_mode) || status.st_dev != device) {
        if (owned) dispose(scope, directory, name, &status);
        return;
    }
    if (state->depth == PURGE_DEPTH) { at_depth_bound(scope, directory, name, &status, owned); return; }
    int child = openat(directory, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    struct stat opened;
    DIR *listing = NULL;
    if (child >= 0 && fstat(child, &opened) == 0 && same_inode(&opened, &status)) listing = fdopendir(child);
    char *copy = listing ? strdup(name) : NULL;
    if (!listing || !copy) {
        if (listing) closedir(listing);
        else if (child >= 0) close(child);
        if (owned) dispose(scope, directory, name, &status);
        else fprintf(stderr, "autocontrol-owner-guardian: purge could not open another ID's directory\n");
        return;
    }
    bool quarantined = state->levels[at].quarantined || (root_walk && at == 0 && earlier_quarantine(&status, name));
    state->levels[state->depth++] = (level){listing, at, copy, owned, quarantined, status};
}

/* Walks one opened directory; `top` is closed when done. `root_walk`: `top` is a purge root;
 * `in_quarantine`: `top` is the quarantine. */
static void walk_directory(purge_scope *scope, int top, bool root_walk, bool in_quarantine) {
    struct stat status;
    DIR *listing = fstat(top, &status) == 0 ? fdopendir(top) : NULL;
    if (!listing) { close(top); return; }
    static walk state;
    state.depth = 0;
    state.levels[state.depth++] = (level){listing, 0, NULL, false, in_quarantine, status};
    while (state.depth) {
        struct dirent *entry = scope->budget ? readdir(state.levels[state.depth - 1].listing) : NULL;
        if (!entry) {
            if (state.depth == 1) { closedir(state.levels[0].listing); break; }
            pop(scope, &state);
            continue;
        }
        if (--scope->budget == 0) {
            fprintf(stderr, "autocontrol-owner-guardian: purge stopped after %lu entries; it runs again\n",
                    PURGE_BUDGET);
            scope->complete = false;
        }
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, ".."))
            visit(scope, &state, status.st_dev, root_walk, entry->d_name);
    }
}

/* Walks `top`, then every directory deferred meanwhile, each from its own top. */
static void walk_all(purge_scope *scope, int top, bool root_walk) {
    walk_directory(scope, top, root_walk, !root_walk);
    while (scope->deferred_count) walk_directory(scope, scope->deferred[--scope->deferred_count], false, false);
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
    scope->root = root;
    scope->quarantine = -1;
    scope->quarantine_tried = false;
    scope->budget = PURGE_BUDGET;
    int top = dup(root);
    if (top < 0) scope->complete = false;
    else walk_all(scope, top, true);
    /* Take quarantined chains apart until a pass moves nothing deeper out. */
    unsigned pass = 0;
    for (; scope->quarantine >= 0 && scope->budget && pass < QUARANTINE_PASSES; ++pass) {
        scope->moved = 0;
        int listing = dup(scope->quarantine);
        if (listing < 0) { scope->complete = false; break; }
        walk_all(scope, listing, false);
        if (!scope->moved) break;
    }
    if (pass == QUARANTINE_PASSES) scope->complete = false;
    if (scope->quarantine >= 0) {
        close(scope->quarantine);
        unlinkat(root, scope->quarantine_name, AT_REMOVEDIR); /* Only an emptied one goes. */
    }
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

guardian_purge_outcome guardian_purge_payloads(const guardian_manifest *manifest, int slice) {
    const service_policy *service = manifest->service;
    if (!service) return PURGE_CLEAN;
    purge_scope scope = {.service = service, .slice = slice, .clean = true, .complete = true, .root = -1,
                         .quarantine = -1};
    for (size_t i = 0; i < sizeof(default_roots) / sizeof(default_roots[0]); ++i) purge_tree(&scope, default_roots[i]);
    for (size_t i = 0; i < manifest->purge_root_count; ++i) purge_tree(&scope, manifest->purge_roots[i]);
    purge_ipc(&scope, "/proc/sysvipc/shm", 0);
    purge_ipc(&scope, "/proc/sysvipc/msg", 1);
    purge_ipc(&scope, "/proc/sysvipc/sem", 2);
    return !scope.clean ? PURGE_UNCLEAN : scope.complete ? PURGE_CLEAN : PURGE_INCOMPLETE;
}
