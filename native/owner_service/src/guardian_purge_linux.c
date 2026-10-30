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
 * A purge runs in a child with a mount namespace of its own, a slave of the host's so nothing
 * it does propagates out. Every root and SysV IPC table is opened before anything is
 * detached. A walk that meets an entry on another mount (a payload directory another user
 * covered with a mount of their own) detaches that mount there, by the descriptor of the
 * mount's root opened relative to the directory being walked, never by a path, and goes on
 * with what lies beneath; removing a payload mountpoint detaches the host's mount too. A
 * mount it cannot detach is never entered nor judged, and makes the purge run again.
 * Directories on another device of the same mount (btrfs subvolumes) are entered only when
 * a payload owns them. Each walk enters a directory once: one met again
 * (renamed behind the walk, or a directory this purge just moved into the quarantine) is
 * skipped. Its identity is its exact inode number together with a keyed digest of its file
 * handle, which carries the inode generation, so neither a reused inode number nor a
 * computed digest is taken for an earlier directory; a payload directory met again outside
 * the quarantine makes the purge run again rather than be skipped for good. The size of what
 * others keep under a root only makes a purge slower. What stops one short is churn only a live user causes, a listing
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
#include <stdalign.h>
#include <stdlib.h>
#include <string.h>
#include <sched.h>
#include <sys/file.h>
#include <sys/mount.h>
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
#define SEEN_SLOTS_MAX (1UL << 20)  /* Directories one walk remembers, to enter each once. */
#define LISTING_SLACK (1UL << 20)   /* Entries a listing may grow by while it is read. */

/* Directories entered in the current walk: the exact device and inode number and a keyed
 * digest of the file handle (one mount may hold several devices, btrfs subvolumes). A slot is
 * empty while its generation is 0. */
typedef struct { uint64_t device, inode, handle; unsigned generation; } seen_slot;
typedef struct { uint64_t device, inode, handle; } identity;
typedef struct { int fd; bool quarantined; } deferred_directory;
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
    deferred_directory *deferred; /* Opened, not-owned directories at the depth bound. */
    size_t deferred_count, deferred_limit;
    bool overflow_logged;
    seen_set seen;
    uint64_t key[2];              /* Random, per purge: nobody can compute the digests. */
    uint64_t mount;               /* The root's mount: nothing on another is entered or judged. */
    bool mount_logged, subvolume_logged;
    bool revisit_logged;
} purge_scope;

/* Set once the purge's own mount namespace is a slave: only then are mounts detached. */
static bool private_mounts;

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

/* SipHash-2-4 of `length` bytes under the 128-bit key (k0, k1): a digest nobody without the
 * key can compute, so a matching one cannot be searched for. */
#define ROTATE(x, b) (uint64_t)(((x) << (b)) | ((x) >> (64 - (b))))
#define SIPROUND(v0, v1, v2, v3) \
    do { v0 += v1; v1 = ROTATE(v1, 13); v1 ^= v0; v0 = ROTATE(v0, 32); v2 += v3; v3 = ROTATE(v3, 16); \
         v3 ^= v2; v0 += v3; v3 = ROTATE(v3, 21); v3 ^= v0; v2 += v1; v1 = ROTATE(v1, 17); v1 ^= v2; \
         v2 = ROTATE(v2, 32); } while (0)
static uint64_t siphash(uint64_t k0, uint64_t k1, const unsigned char *bytes, size_t length) {
    uint64_t v0 = k0 ^ 0x736f6d6570736575ULL, v1 = k1 ^ 0x646f72616e646f6dULL;
    uint64_t v2 = k0 ^ 0x6c7967656e657261ULL, v3 = k1 ^ 0x7465646279746573ULL;
    for (size_t at = 0; at <= length; at += 8) {
        uint64_t word = 0;
        size_t take = length - at < 8 ? length - at : 8;
        memcpy(&word, bytes + at, take);
        if (take < 8) word |= (uint64_t)(length & 0xff) << 56;
        v3 ^= word;
        SIPROUND(v0, v1, v2, v3);
        SIPROUND(v0, v1, v2, v3);
        v0 ^= word;
        if (take < 8) break;
    }
    v2 ^= 0xff;
    for (int round = 0; round < 4; ++round) SIPROUND(v0, v1, v2, v3);
    return v0 ^ v1 ^ v2 ^ v3;
}

/* The opened directory's identity: its inode number and, where the filesystem has one, the
 * keyed digest of its file handle (inode generation included). */
static identity identity_of(const purge_scope *scope, int directory, const struct stat *status) {
    identity found = {(uint64_t)status->st_dev, (uint64_t)status->st_ino, 0};
    union { struct file_handle header; alignas(struct file_handle) unsigned char bytes[sizeof(struct file_handle) +
                                                                                      MAX_HANDLE_SZ]; } handle;
    handle.header.handle_bytes = MAX_HANDLE_SZ;
    int mount;
    if (name_to_handle_at(directory, "", &handle.header, &mount, AT_EMPTY_PATH) == 0)
        found.handle = siphash(scope->key[0], scope->key[1], handle.bytes,
                               sizeof(struct file_handle) + handle.header.handle_bytes);
    return found;
}

static size_t seen_index(const seen_set *set, identity key) {
    uint64_t mixed = ((key.inode ^ (key.device << 32)) * 0x9E3779B97F4A7C15ULL) ^ key.handle;
    return (size_t)(mixed ^ (mixed >> 29)) & (set->capacity - 1);
}

/* The mount an open descriptor lies on, from its fdinfo: the kernel's own record of the
 * descriptor, read without any inode operation. 0 when unknown, with errno set. */
static uint64_t mount_of_descriptor(int descriptor) {
    char path[48];
    snprintf(path, sizeof(path), "/proc/self/fdinfo/%d", descriptor);
    FILE *info = fopen(path, "re");
    if (!info) return 0;
    char line[256];
    unsigned long long mount = 0;
    while (fgets(line, sizeof(line), info) && sscanf(line, "mnt_id: %llu", &mount) != 1) continue;
    fclose(info);
    if (!mount) errno = ENOSYS;
    return (uint64_t)mount;
}

/* The mount `name` in `directory` lies on (the mounted one, for a mount point); 0 when
 * unknown, with errno set. Nothing is asked of the filesystem: an O_PATH open neither opens
 * nor stats the object, so another user's FUSE mount (which refuses root a getattr, or
 * answers EIO once its root inode went bad) and a daemon that never replies are named all
 * the same. With AT_EMPTY_PATH, `directory` itself. */
static uint64_t mount_of(int directory, const char *name, int flags) {
    if (flags & AT_EMPTY_PATH) return mount_of_descriptor(directory);
    int opened = openat(directory, name, O_PATH | O_NOFOLLOW | O_CLOEXEC);
    if (opened < 0) return 0;
    uint64_t mount = mount_of_descriptor(opened);
    int error = errno;
    close(opened);
    errno = error;
    return mount;
}

/* The purge's heartbeat, in memory the guardian reads: bumped as the purge goes on, so a
 * purge stuck in one call (a FUSE daemon that never answers) is told from a long one. */
uint64_t *guardian_purge_heartbeat;

static void beat(void) {
    if (guardian_purge_heartbeat) __atomic_fetch_add(guardian_purge_heartbeat, 1, __ATOMIC_RELAXED);
}

/* Grows the table, keeping this walk's entries only. False when it cannot grow. */
static bool seen_grow(seen_set *set) {
    size_t capacity = set->capacity ? set->capacity * 2 : 4096;
    if (capacity > SEEN_SLOTS_MAX) return false;
    seen_set grown = {calloc(capacity, sizeof(seen_slot)), capacity, 0, set->generation, false};
    if (!grown.slots) return false;
    for (size_t i = 0; i < set->capacity; ++i) {
        if (set->slots[i].generation != set->generation) continue;
        size_t at = seen_index(&grown, (identity){set->slots[i].device, set->slots[i].inode, set->slots[i].handle});
        while (grown.slots[at].generation) at = (at + 1) & (capacity - 1);
        grown.slots[at] = set->slots[i];
        ++grown.used;
    }
    free(set->slots);
    *set = grown;
    return true;
}

/* Remembers a directory entered in this walk; AGAIN when it was entered before. */
static seen_result remember(seen_set *set, identity key) {
    if (set->untracked) return SEEN_UNTRACKED;
    if ((set->used + 1) * 2 > set->capacity && !seen_grow(set) && (set->used + 1) * 10 > set->capacity * 9) {
        fprintf(stderr, "autocontrol-owner-guardian: purge walks on without noticing repeats\n");
        set->untracked = true;
        return SEEN_UNTRACKED;
    }
    size_t at = seen_index(set, key);
    for (; set->slots[at].generation; at = (at + 1) & (set->capacity - 1)) {
        if (set->slots[at].device != key.device || set->slots[at].inode != key.inode ||
            set->slots[at].handle != key.handle) continue;
        if (set->slots[at].generation == set->generation) return SEEN_AGAIN;
        set->slots[at].generation = set->generation;
        return SEEN_NEW;
    }
    set->slots[at] = (seen_slot){key.device, key.inode, key.handle, set->generation};
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
                           bool owned, int opened, bool quarantined) {
    if (owned) { close(opened); dispose(scope, directory, name, status); return; }
    if (scope->deferred_count < scope->deferred_limit) {
        scope->deferred[scope->deferred_count++] = (deferred_directory){opened, quarantined};
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

/* Detaches, in the purge's own namespace, the mount whose root `name` in `directory` shows:
 * opened relative to the walked directory, without following a link, and unmounted by that
 * descriptor, so no path anyone else wrote is ever resolved. */
static bool detach_entry(int directory, const char *name) {
    int opened = openat(directory, name, O_PATH | O_NOFOLLOW | O_CLOEXEC);
    if (opened < 0) return false;
    char path[32];
    snprintf(path, sizeof(path), "/proc/self/fd/%d", opened);
    bool detached = umount2(path, MNT_DETACH) == 0;
    close(opened);
    return detached;
}

static void left_mount(purge_scope *scope) {
    if (!scope->mount_logged) fprintf(stderr, "autocontrol-owner-guardian: purge left a mount in place\n");
    scope->mount_logged = true;
    /* In its own namespace a mount it could not detach is a race with a live user: run again.
     * Without one (no namespace could be made) mounts stay, skipped, as they always do. */
    if (private_mounts) scope->complete = false;
}

/* The mount `name` shows once every mount stacked on it is detached; 0 when gone or unknown.
 * Each detach removes one of a namespace's finite mounts, so only a user mounting anew while
 * it runs can keep it going; the bound is the kernel's own default for fs.mount-max. */
static uint64_t bare_mount(purge_scope *scope, int directory, const char *name) {
    uint64_t mount = mount_of(directory, name, AT_SYMLINK_NOFOLLOW);
    for (long layer = 0; mount && mount != scope->mount && private_mounts && layer < 100000; ++layer) {
        beat();
        if (!detach_entry(directory, name)) break;
        mount = mount_of(directory, name, AT_SYMLINK_NOFOLLOW);
    }
    if (!mount && errno != ENOENT) {
        fprintf(stderr, "autocontrol-owner-guardian: purge could not tell an entry's mount; it runs again\n");
        scope->complete = false;
    } else if (mount && mount != scope->mount) {
        left_mount(scope);
    }
    return mount;
}

static void visit(purge_scope *scope, walk *state, bool root_walk, const char *name) {
    size_t at = state->depth - 1;
    int directory = dirfd(state->levels[at].listing);
    if (bare_mount(scope, directory, name) != scope->mount) return; /* Another mount's, or gone. */
    struct stat status;
    if (fstatat(directory, name, &status, AT_SYMLINK_NOFOLLOW) != 0) return;
    if (at == 0 && scope->quarantine >= 0 && same_inode(&status, &scope->quarantined)) return; /* Walked later. */
    if (!S_ISDIR(status.st_mode)) {
        if (payload_uid(scope, status.st_uid)) dispose(scope, directory, name, &status);
        return;
    }
    /* What is walked is the directory opened, whatever the name pointed at before. */
    int child = openat(directory, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    int error = child < 0 ? errno : 0;
    if (child >= 0 && (fstat(child, &status) != 0 || mount_of(child, "", AT_EMPTY_PATH) != scope->mount)) {
        close(child);
        left_mount(scope); /* Mounted or swapped meanwhile: not this walk's to judge. */
        return;
    }
    if (child < 0) {
        if (payload_uid(scope, status.st_uid)) dispose(scope, directory, name, &status);
        else if (error != ENOENT && error != ENOTDIR && error != ELOOP)
            fprintf(stderr, "autocontrol-owner-guardian: purge could not open another ID's directory\n");
        return;
    }
    bool owned = payload_uid(scope, status.st_uid);
    if (child >= 0 && status.st_dev != state->levels[at].seen.st_dev && !owned) {
        /* Another ID's subvolume (a read-only snapshot, say): not entered. Payload files in it
         * were put there with that ID's leave. */
        if (!scope->subvolume_logged)
            fprintf(stderr, "autocontrol-owner-guardian: purge left another ID's subvolume unwalked\n");
        scope->subvolume_logged = true;
        close(child);
        return;
    }
    bool earlier = root_walk && at == 0 && earlier_quarantine(&status, name);
    if (earlier && flock(child, LOCK_EX | LOCK_NB) != 0) { close(child); return; } /* A running purge's. */
    if (remember(&scope->seen, identity_of(scope, child, &status)) == SEEN_AGAIN) {
        close(child); /* Walked already in this walk; one moved here by this purge, next pass. */
        bool in_quarantine = state->levels[at].quarantined || is_quarantine(scope, directory);
        if (in_quarantine) return;
        /* Only a live user renaming behind the walk brings a directory round again here. */
        if (!scope->revisit_logged) fprintf(stderr, "autocontrol-owner-guardian: purge met a directory again\n");
        scope->revisit_logged = true;
        if (owned) scope->complete = false; /* A payload's, possibly not walked whole: run again. */
        return;
    }
    bool quarantined = state->levels[at].quarantined || earlier;
    if (state->depth == PURGE_DEPTH) {
        at_depth_bound(scope, directory, name, &status, owned, child, quarantined);
        return;
    }
    DIR *listing = fdopendir(child);
    char *copy = listing ? strdup(name) : NULL;
    if (!listing || !copy) {
        if (listing) closedir(listing);
        else close(child);
        if (owned) dispose(scope, directory, name, &status);
        return;
    }
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
        beat();
        if (++current->read > current->limit) { churn(scope, "a listing kept growing"); continue; }
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, ".."))
            visit(scope, &state, root_walk, entry->d_name);
    }
}

/* One walk: `top`, then every directory deferred meanwhile, each from its own top. */
static void walk_all(purge_scope *scope, int top, bool root_walk) {
    seen_next_walk(&scope->seen);
    walk_directory(scope, top, root_walk, !root_walk);
    while (scope->deferred_count) {
        deferred_directory next = scope->deferred[--scope->deferred_count];
        walk_directory(scope, next.fd, false, next.quarantined);
    }
}

bool guardian_purge_unshare(void) {
    if (unshare(CLONE_NEWNS) != 0) return false;
    /* Shared propagation would carry every detach back to the host: none without this. A
     * slave still receives the host's unmounts, so it pins no filesystem the host lets go. */
    if (mount(NULL, "/", NULL, MS_REC | MS_SLAVE, NULL) != 0) return false;
    private_mounts = true;
    return true;
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

/* `root` is the root opened beforehand; it is closed here. */
static void purge_tree(purge_scope *scope, int root, const char *path) {
    scope->root = root;
    scope->mount = mount_of(root, "", AT_EMPTY_PATH);
    if (!scope->mount) {
        fprintf(stderr, "autocontrol-owner-guardian: purge cannot tell mounts apart under %s; it runs again\n", path);
        scope->complete = false;
        close(root);
        return;
    }
    scope->quarantine = -1;
    scope->quarantine_tried = false;
    scope->churned = false;
    int top = dup(root);
    if (top < 0) {
        fprintf(stderr, "autocontrol-owner-guardian: purge could not walk %s; it runs again\n", path);
        scope->complete = false;
    } else {
        walk_all(scope, top, true);
    }
    /* Take quarantined chains apart until a pass moves nothing deeper out. Each pass opens
     * the quarantine afresh, so it reads from the first entry. */
    unsigned pass = 0;
    for (; scope->quarantine >= 0 && !scope->churned && pass < QUARANTINE_PASSES; ++pass) {
        scope->moved = 0;
        int listing = openat(scope->quarantine, ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (listing < 0) {
            fprintf(stderr, "autocontrol-owner-guardian: purge could not reopen its quarantine; it runs again\n");
            scope->complete = false;
            break;
        }
        walk_all(scope, listing, false);
        if (!scope->moved) break;
    }
    if (pass == QUARANTINE_PASSES) {
        fprintf(stderr, "autocontrol-owner-guardian: purge used every quarantine pass; it runs again\n");
        scope->complete = false;
    }
    if (scope->quarantine >= 0) {
        unlinkat(root, scope->quarantine_name, AT_REMOVEDIR); /* Only an emptied one goes. */
        close(scope->quarantine);
    }
    scope->quarantine = -1;
    close(root);
}

/* Each /proc/sysvipc table, opened beforehand and closed here: the ID column and the owner
 * and creator user ID columns. */
static void purge_ipc(purge_scope *scope, FILE *file, int kind) {
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
    if (getrandom(scope.key, sizeof(scope.key), 0) != (ssize_t)sizeof(scope.key)) {
        fprintf(stderr, "autocontrol-owner-guardian: purge has no random key; it runs again\n");
        return PURGE_INCOMPLETE;
    }
    struct rlimit before = {0, 0};
    scope.deferred_limit = deferred_room(&before);
    scope.deferred = scope.deferred_limit ? calloc(scope.deferred_limit, sizeof(deferred_directory)) : NULL;
    if (!scope.deferred) scope.deferred_limit = 0;
    /* Everything is opened before any mount is detached: nothing detached later can hide a
     * root or a table. */
    size_t defaults = sizeof(default_roots) / sizeof(default_roots[0]);
    size_t count = defaults + manifest->purge_root_count;
    int roots[sizeof(default_roots) / sizeof(default_roots[0]) + GUARDIAN_PURGE_ROOT_LIMIT];
    const char *names[sizeof(roots) / sizeof(roots[0])];
    if (count > sizeof(roots) / sizeof(roots[0])) {
        count = sizeof(roots) / sizeof(roots[0]); /* Manifest validation refuses this already. */
        scope.complete = false;
    }
    for (size_t i = 0; i < count; ++i) {
        names[i] = i < defaults ? default_roots[i] : manifest->purge_roots[i - defaults];
        roots[i] = open_root(names[i]); /* -1: absent, or not a directory this guardian may trust. */
    }
    static const char *const tables[] = {"/proc/sysvipc/shm", "/proc/sysvipc/msg", "/proc/sysvipc/sem"};
    FILE *opened[3];
    for (int kind = 0; kind < 3; ++kind) {
        opened[kind] = fopen(tables[kind], "re");
        /* Absent only where the kernel has no SysV IPC; any other failure is run again. */
        if (!opened[kind] && errno != ENOENT) {
            fprintf(stderr, "autocontrol-owner-guardian: purge could not read %s; it runs again\n", tables[kind]);
            scope.complete = false;
        }
    }
    for (size_t i = 0; i < count; ++i) if (roots[i] >= 0) purge_tree(&scope, roots[i], names[i]);
    for (int kind = 0; kind < 3; ++kind) purge_ipc(&scope, opened[kind], kind);
    free(scope.deferred);
    free(scope.seen.slots);
    /* The startup purge runs in the guardian: what it launches later keeps the usual limit. */
    if (before.rlim_max) setrlimit(RLIMIT_NOFILE, &before);
    return !scope.clean ? PURGE_UNCLEAN : scope.complete ? PURGE_CLEAN : PURGE_INCOMPLETE;
}
