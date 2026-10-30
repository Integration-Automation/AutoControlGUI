#define _GNU_SOURCE
/* After an epoch is killed nothing runs as its payload IDs, so what those IDs left behind is
 * removed before the IDs are handed out again: files under the shared writable directories
 * and SysV IPC objects, as systemd does for DynamicUser with RemoveIPC. A later helper with
 * the same ID then finds nothing of an earlier one, and tmpfs pages a killed helper left
 * charged are released.
 *
 * Directories are walked by descriptor, never through a link or into another filesystem, and
 * entries are removed relative to the directory that was opened; what a directory's owner
 * is, is read from the opened directory. Ownership is judged by user ID only. At most
 * PURGE_DEPTH directories are open at once. A payload-owned directory that cannot be removed
 * where it is (deeper than the walk, or another ID wrote into it) is moved whole, after its
 * identity is checked, into a quarantine: a directory only root can enter, created on the
 * same filesystem under a random name when first needed, locked while its purge runs, and
 * recognised by its inode, never by its name. Its name is free again at once. The quarantine
 * is then walked from its own top, pass after pass, so a chain of any depth is taken apart
 * PURGE_DEPTH levels at a time; what other IDs own is all that may stay there, out of every
 * payload's reach, and an emptied quarantine is removed.
 *
 * Each walk enters a directory once: one met again (renamed behind the walk, a bind mount, a
 * directory this purge just moved into the quarantine) is skipped, its identity being the
 * inode number together with its file handle, which carries the inode generation, so a
 * reused inode number is never mistaken for it. The size of what others keep under a root
 * only makes a purge slower. What stops one short is churn only a live user causes, a listing
 * growing far past its size when opened; a purge that met it, or could not move a payload
 * directory into the quarantine, reports itself incomplete and runs again before its slice
 * is handed out. Only an object that can be neither removed, moved nor closed off makes it
 * unclean. */
#include "guardian.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/fs.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ipc.h>
#include <sys/msg.h>
#include <sys/random.h>
#include <sys/resource.h>
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
#define QUARANTINE_PASSES 4096      /* Each pass takes PURGE_DEPTH levels off the deepest chain. */
#define DEFERRED_LIMIT 4096         /* Other IDs' directories at the depth bound, walked from their own top. */
#define SEEN_SLOTS_MAX (1UL << 21)  /* Directories one walk remembers, to enter each once. */
#define LISTING_SLACK (1UL << 20)   /* Entries a listing may grow by while it is read. */

/* Directories entered in the current walk, by a 64-bit digest of their identity. A slot is
 * empty while its generation is 0. */
typedef struct { uint64_t key; unsigned generation; } seen_slot;
typedef struct { seen_slot *slots; size_t capacity, used; unsigned generation; bool untracked; } seen_set;
typedef enum { SEEN_NEW, SEEN_AGAIN, SEEN_UNTRACKED } seen_result;

typedef struct {
    const service_policy *service;
    int slice;
    bool clean, complete, churned;
    int root;                     /* The root being purged: the quarantine is made in it. */
    bool quarantine_tried;
    int quarantine;               /* Root-only directory on the walked filesystem, or -1. */
    char quarantine_name[64];
    struct stat quarantined;      /* Its identity: it is skipped, and nothing in it moves again. */
    unsigned long moved;          /* Directories moved into the quarantine this pass. */
    int *deferred;                /* Opened, not-owned directories at the depth bound. */
    size_t deferred_count, deferred_limit;
    bool overflow_logged;
    seen_set seen;
    unsigned long revisits;       /* Directories met again and skipped. */
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

static void churn(purge_scope *scope, const char *what) {
    if (!scope->churned) fprintf(stderr, "autocontrol-owner-guardian: purge met churn (%s); it runs again\n", what);
    scope->churned = true;
    scope->complete = false;
}

static uint64_t mix(uint64_t hash, const void *bytes, size_t length) {
    const unsigned char *byte = bytes;
    for (size_t i = 0; i < length; ++i) hash = (hash ^ byte[i]) * 0x100000001B3ULL;
    return hash;
}

/* The opened directory's identity: device, inode number and, where the filesystem has one,
 * its file handle (inode generation included). Never 0. */
static uint64_t identity_of(int directory, const struct stat *status) {
    uint64_t hash = mix(0xCBF29CE484222325ULL, &status->st_dev, sizeof(status->st_dev));
    hash = mix(hash, &status->st_ino, sizeof(status->st_ino));
    struct { struct file_handle header; unsigned char bytes[MAX_HANDLE_SZ]; } handle;
    handle.header.handle_bytes = MAX_HANDLE_SZ;
    int mount;
    if (name_to_handle_at(directory, "", &handle.header, &mount, AT_EMPTY_PATH) == 0) {
        hash = mix(hash, &handle.header.handle_type, sizeof(handle.header.handle_type));
        hash = mix(hash, handle.header.f_handle, handle.header.handle_bytes);
    }
    return hash ? hash : 1;
}

static size_t seen_index(const seen_set *set, uint64_t key) {
    return (size_t)(key ^ (key >> 29)) & (set->capacity - 1);
}

/* Grows the table, keeping this walk's entries only. False when it cannot grow. */
static bool seen_grow(seen_set *set) {
    size_t capacity = set->capacity ? set->capacity * 2 : 4096;
    if (capacity > SEEN_SLOTS_MAX) return false;
    seen_set grown = {calloc(capacity, sizeof(seen_slot)), capacity, 0, set->generation, false};
    if (!grown.slots) return false;
    for (size_t i = 0; i < set->capacity; ++i) {
        if (set->slots[i].generation != set->generation) continue;
        size_t at = seen_index(&grown, set->slots[i].key);
        while (grown.slots[at].generation) at = (at + 1) & (capacity - 1);
        grown.slots[at] = set->slots[i];
        ++grown.used;
    }
    free(set->slots);
    *set = grown;
    return true;
}

/* Remembers a directory entered in this walk; AGAIN when it was entered before. */
static seen_result remember(seen_set *set, uint64_t key) {
    if (set->untracked) return SEEN_UNTRACKED;
    if ((set->used + 1) * 2 > set->capacity && !seen_grow(set) && (set->used + 1) * 10 > set->capacity * 9) {
        fprintf(stderr, "autocontrol-owner-guardian: purge walks on without noticing repeats\n");
        set->untracked = true;
        return SEEN_UNTRACKED;
    }
    size_t at = seen_index(set, key);
    for (; set->slots[at].generation; at = (at + 1) & (set->capacity - 1)) {
        if (set->slots[at].key != key) continue;
        if (set->slots[at].generation == set->generation) return SEEN_AGAIN;
        set->slots[at].generation = set->generation;
        return SEEN_NEW;
    }
    set->slots[at] = (seen_slot){key, set->generation};
    ++set->used;
    return SEEN_NEW;
}

/* A new walk: earlier walks' entries no longer count, and a table mostly full of them is cleared. */
static void seen_next_walk(seen_set *set) {
    ++set->generation;
    set->untracked = false;
    if (set->slots && set->used * 4 > set->capacity) {
        memset(set->slots, 0, set->capacity * sizeof(seen_slot));
        set->used = 0;
    }
}

static bool is_quarantine(const purge_scope *scope, int directory) {
    struct stat status;
    return scope->quarantine >= 0 && fstat(directory, &status) == 0 && same_inode(&status, &scope->quarantined);
}

/* The quarantine, made on first need under a fresh random name and locked while this purge
 * runs: nobody can have taken it beforehand, a name somebody else made is just another
 * directory to walk, and a concurrent purge leaves a locked one alone. */
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
        if (quarantine >= 0 && flock(quarantine, LOCK_EX | LOCK_NB) == 0 && fchmod(quarantine, 0700) == 0 &&
            fstat(quarantine, &status) == 0 && status.st_uid == 0) {
            scope->quarantine = quarantine;
            scope->quarantined = status;
            return true;
        }
        if (quarantine >= 0) close(quarantine);
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
    /* A directory that could not be moved keeps its name taken and what lies below: run again. */
    if (is_directory) scope->complete = false;
}

/* `quarantined`: the level lies in a quarantine, this one or an earlier one, where nothing is
 * any payload's and an emptied directory, whoever's, is removed. `limit`: entries the listing
 * may yield before it counts as churn. */
typedef struct {
    DIR *listing;
    size_t parent;
    char *name;
    bool owned, quarantined;
    struct stat seen;
    unsigned long read, limit;
} level;
typedef struct { level levels[PURGE_DEPTH]; size_t depth; } walk;

static unsigned long listing_limit(const struct stat *status) {
    return 4UL * (unsigned long)(status->st_size > 0 ? status->st_size : 0) + LISTING_SLACK;
}

static void pop(purge_scope *scope, walk *state) {
    level done = state->levels[--state->depth];
    closedir(done.listing);
    int parent = dirfd(state->levels[done.parent].listing);
    if (done.owned) dispose(scope, parent, done.name, &done.seen);
    else if (done.quarantined && still_seen(parent, done.name, &done.seen)) unlinkat(parent, done.name, AT_REMOVEDIR);
    free(done.name);
}

/* An earlier quarantine: root's, mode 0700, a directory at the root's top with the prefix.
 * Walked like any other directory and removed once empty; one a running purge holds locked
 * is that purge's. */
static bool earlier_quarantine(const struct stat *status, const char *name) {
    return S_ISDIR(status->st_mode) && status->st_uid == 0 && (status->st_mode & 07777) == 0700 &&
        !strncmp(name, QUARANTINE_PREFIX, strlen(QUARANTINE_PREFIX));
}

/* Deeper than the walk goes: an owned directory is moved whole and taken apart from its own
 * top; another ID's stays where it is and is walked later from its own top. */
static void at_depth_bound(purge_scope *scope, int directory, const char *name, const struct stat *status,
                           bool owned, int opened) {
    if (owned) { close(opened); dispose(scope, directory, name, status); return; }
    if (scope->deferred_count < scope->deferred_limit) {
        scope->deferred[scope->deferred_count++] = opened;
        return;
    }
    /* With a stable listing order the same ones overflow every time: what a payload put in
     * them stays as long as they do. */
    close(opened);
    /* Payload files there were put inside another ID's directory, with that ID's leave. */
    if (!scope->overflow_logged)
        fprintf(stderr, "autocontrol-owner-guardian: purge left other IDs' directories deeper than %d unwalked\n",
                PURGE_DEPTH);
    scope->overflow_logged = true;
}

static void visit(purge_scope *scope, walk *state, dev_t device, bool root_walk, const char *name) {
    size_t at = state->depth - 1;
    int directory = dirfd(state->levels[at].listing);
    struct stat status;
    if (fstatat(directory, name, &status, AT_SYMLINK_NOFOLLOW) != 0) return;
    if (at == 0 && scope->quarantine >= 0 && same_inode(&status, &scope->quarantined)) return; /* Walked later. */
    if (!S_ISDIR(status.st_mode) || status.st_dev != device) {
        if (payload_uid(scope, status.st_uid)) dispose(scope, directory, name, &status);
        return;
    }
    /* What is walked is the directory opened, whatever the name pointed at before. */
    int child = openat(directory, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (child < 0 || fstat(child, &status) != 0 || status.st_dev != device) {
        int error = errno;
        if (child >= 0) close(child);
        if (payload_uid(scope, status.st_uid)) dispose(scope, directory, name, &status);
        else if (error != ENOENT && error != ENOTDIR && error != ELOOP)
            fprintf(stderr, "autocontrol-owner-guardian: purge could not open another ID's directory\n");
        return;
    }
    bool owned = payload_uid(scope, status.st_uid);
    bool earlier = root_walk && at == 0 && earlier_quarantine(&status, name);
    if (earlier && flock(child, LOCK_EX | LOCK_NB) != 0) { close(child); return; } /* A running purge's. */
    if (remember(&scope->seen, identity_of(child, &status)) == SEEN_AGAIN) {
        close(child); /* Walked already in this walk; one moved here by this purge, next pass. */
        ++scope->revisits;
        return;
    }
    if (state->depth == PURGE_DEPTH) { at_depth_bound(scope, directory, name, &status, owned, child); return; }
    DIR *listing = fdopendir(child);
    char *copy = listing ? strdup(name) : NULL;
    if (!listing || !copy) {
        if (listing) closedir(listing);
        else close(child);
        if (owned) dispose(scope, directory, name, &status);
        return;
    }
    bool quarantined = state->levels[at].quarantined || earlier;
    state->levels[state->depth++] = (level){listing, at, copy, owned, quarantined, status, 0, listing_limit(&status)};
}

/* Walks one opened directory; `top` is closed when done. `root_walk`: `top` is a purge root;
 * `in_quarantine`: `top` lies in the quarantine. */
static void walk_directory(purge_scope *scope, int top, bool root_walk, bool in_quarantine) {
    struct stat status;
    DIR *listing = fstat(top, &status) == 0 ? fdopendir(top) : NULL;
    if (!listing) { close(top); return; }
    static walk state;
    state.depth = 0;
    state.levels[state.depth++] = (level){listing, 0, NULL, false, in_quarantine, status, 0, listing_limit(&status)};
    while (state.depth) {
        level *current = &state.levels[state.depth - 1];
        struct dirent *entry = scope->churned ? NULL : readdir(current->listing);
        if (!entry) {
            if (state.depth == 1) { closedir(state.levels[0].listing); break; }
            pop(scope, &state);
            continue;
        }
        if (++current->read > current->limit) { churn(scope, "a listing kept growing"); continue; }
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, ".."))
            visit(scope, &state, status.st_dev, root_walk, entry->d_name);
    }
}

/* One walk: `top`, then every directory deferred meanwhile, each from its own top. */
static void walk_all(purge_scope *scope, int top, bool root_walk) {
    seen_next_walk(&scope->seen);
    walk_directory(scope, top, root_walk, !root_walk);
    while (scope->deferred_count)
        walk_directory(scope, scope->deferred[--scope->deferred_count], false, !root_walk);
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
    scope->churned = false;
    int top = dup(root);
    if (top < 0) scope->complete = false;
    else walk_all(scope, top, true);
    /* Take quarantined chains apart until a pass moves nothing deeper out. Each pass opens
     * the quarantine afresh, so it reads from the first entry. */
    unsigned pass = 0;
    for (; scope->quarantine >= 0 && !scope->churned && pass < QUARANTINE_PASSES; ++pass) {
        scope->moved = 0;
        int listing = openat(scope->quarantine, ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (listing < 0) { scope->complete = false; break; }
        walk_all(scope, listing, false);
        if (!scope->moved) break;
    }
    if (pass == QUARANTINE_PASSES) scope->complete = false;
    if (scope->quarantine >= 0) {
        unlinkat(root, scope->quarantine_name, AT_REMOVEDIR); /* Only an emptied one goes. */
        close(scope->quarantine);
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

/* Deferred directories each hold a descriptor: as many as the descriptor limit leaves room
 * for, after raising it as far as allowed. */
static size_t deferred_room(struct rlimit *before) {
    struct rlimit files;
    if (getrlimit(RLIMIT_NOFILE, &files) != 0) return 0;
    *before = files;
    if (files.rlim_cur < files.rlim_max) {
        files.rlim_cur = files.rlim_max;
        if (setrlimit(RLIMIT_NOFILE, &files) != 0) getrlimit(RLIMIT_NOFILE, &files);
    }
    size_t room = files.rlim_cur > PURGE_DEPTH * 4 + 64 ? (size_t)(files.rlim_cur - PURGE_DEPTH * 4 - 64) : 0;
    return room < DEFERRED_LIMIT ? room : DEFERRED_LIMIT;
}

static const char *const default_roots[] = {"/tmp", "/var/tmp", "/dev/shm", "/dev/mqueue", "/run/lock"};

guardian_purge_outcome guardian_purge_payloads(const guardian_manifest *manifest, int slice) {
    const service_policy *service = manifest->service;
    if (!service) return PURGE_CLEAN;
    purge_scope scope = {.service = service, .slice = slice, .clean = true, .complete = true, .root = -1,
                         .quarantine = -1};
    struct rlimit before = {0, 0};
    scope.deferred_limit = deferred_room(&before);
    scope.deferred = scope.deferred_limit ? calloc(scope.deferred_limit, sizeof(int)) : NULL;
    if (!scope.deferred) scope.deferred_limit = 0;
    for (size_t i = 0; i < sizeof(default_roots) / sizeof(default_roots[0]); ++i) purge_tree(&scope, default_roots[i]);
    for (size_t i = 0; i < manifest->purge_root_count; ++i) purge_tree(&scope, manifest->purge_roots[i]);
    purge_ipc(&scope, "/proc/sysvipc/shm", 0);
    purge_ipc(&scope, "/proc/sysvipc/msg", 1);
    purge_ipc(&scope, "/proc/sysvipc/sem", 2);
    free(scope.deferred);
    free(scope.seen.slots);
    /* The startup purge runs in the guardian: what it launches later keeps the usual limit. */
    if (before.rlim_max) setrlimit(RLIMIT_NOFILE, &before);
    return !scope.clean ? PURGE_UNCLEAN : scope.complete ? PURGE_CLEAN : PURGE_INCOMPLETE;
}
