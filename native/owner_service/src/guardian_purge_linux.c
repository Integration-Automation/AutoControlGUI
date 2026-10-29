#define _GNU_SOURCE
/* After an epoch is killed nothing runs as its payload IDs, so what those IDs left behind is
 * removed before the IDs are handed out again: files under the shared writable directories
 * and SysV IPC objects, as systemd does for DynamicUser with RemoveIPC. A later helper with
 * the same ID then finds nothing of an earlier one, and tmpfs pages a killed helper left
 * charged are released. Directories are walked by descriptor on a heap stack, never through
 * a link or into another filesystem and with no depth limit, and entries are removed
 * relative to the directory that was opened, so no rename on the way can redirect a
 * removal. Ownership is judged by user ID only: a file's group says nothing of who made it.
 * Anything a payload ID owns that cannot be removed makes the purge report unclean, and the
 * guardian then never hands that half out again until it restarts and purges anew. */
#include "guardian.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ipc.h>
#include <sys/msg.h>
#include <sys/resource.h>
#include <sys/sem.h>
#include <sys/shm.h>
#include <sys/stat.h>
#include <unistd.h>

typedef struct { const service_policy *service; int half; } purge_scope;

/* `half` 0 or 1 is one epoch's half of every user-ID range; -1 both halves. */
static bool payload_uid(const purge_scope *scope, uint32_t uid) {
    uint32_t span = scope->half < 0 ? SERVICE_PAYLOAD_IDS : SERVICE_EPOCH_IDS;
    for (size_t i = 0; i < scope->service->policy_count; ++i) {
        uint32_t low = scope->service->policies[i].payload_uid;
        if (scope->half > 0) low += SERVICE_EPOCH_IDS;
        if (uid >= low && uid - low < span) return true;
    }
    return false;
}

typedef struct { DIR *listing; size_t parent; char *name; bool owned; } level;

typedef struct { level *levels; size_t depth, capacity; bool clean; } walk;

static bool push(walk *state, DIR *listing, size_t parent, const char *name, bool owned) {
    if (state->depth == state->capacity) {
        size_t capacity = state->capacity ? 2 * state->capacity : 64;
        level *grown = realloc(state->levels, capacity * sizeof(*grown));
        if (!grown) return false;
        state->levels = grown;
        state->capacity = capacity;
    }
    char *copy = name ? strdup(name) : NULL;
    if (name && !copy) return false;
    state->levels[state->depth++] = (level){listing, parent, copy, owned};
    return true;
}

/* A finished directory is closed, then removed from its parent when a payload ID owns it. */
static void pop(walk *state) {
    level done = state->levels[--state->depth];
    closedir(done.listing);
    if (done.owned && unlinkat(dirfd(state->levels[done.parent].listing), done.name, AT_REMOVEDIR) != 0)
        state->clean = false;
    free(done.name);
}

static void visit(walk *state, const purge_scope *scope, dev_t device, const char *name) {
    size_t at = state->depth - 1;
    int directory = dirfd(state->levels[at].listing);
    struct stat status;
    if (fstatat(directory, name, &status, AT_SYMLINK_NOFOLLOW) != 0) return;
    bool owned = payload_uid(scope, status.st_uid);
    if (!S_ISDIR(status.st_mode) || status.st_dev != device) {
        if (owned && unlinkat(directory, name, 0) != 0) state->clean = false;
        return;
    }
    int child = openat(directory, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    struct stat opened;
    DIR *listing = NULL;
    if (child >= 0 && fstat(child, &opened) == 0 && opened.st_ino == status.st_ino && opened.st_dev == status.st_dev)
        listing = fdopendir(child);
    if (!listing) {
        if (child >= 0) close(child);
        if (owned) state->clean = false;
        return;
    }
    if (!push(state, listing, at, name, owned)) {
        closedir(listing);
        state->clean = false;
    }
}

static bool purge_tree(const purge_scope *scope, const char *path) {
    int root = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (root < 0) return errno == ENOENT;
    struct stat status;
    DIR *listing = fstat(root, &status) == 0 ? fdopendir(root) : NULL;
    if (!listing) { close(root); return false; }
    walk state = {.clean = true};
    if (!push(&state, listing, 0, NULL, false)) { closedir(listing); return false; }
    while (state.depth) {
        struct dirent *entry = readdir(state.levels[state.depth - 1].listing);
        if (!entry) {
            if (state.depth == 1) { closedir(state.levels[0].listing); break; }
            pop(&state);
            continue;
        }
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, ".."))
            visit(&state, scope, status.st_dev, entry->d_name);
    }
    free(state.levels);
    return state.clean;
}

/* Each /proc/sysvipc table: the ID column and the owner and creator user ID columns. */
static bool purge_ipc(const purge_scope *scope, const char *table, int kind) {
    FILE *file = fopen(table, "re");
    if (!file) return errno == ENOENT;
    char line[512];
    bool clean = true;
    if (!fgets(line, sizeof(line), file)) { fclose(file); return true; }
    while (fgets(line, sizeof(line), file)) {
        int key, id;
        unsigned uid = 0, cuid = 0;
        int fields = kind == 0 ? sscanf(line, "%d %d %*o %*u %*d %*d %*u %u %*u %u", &key, &id, &uid, &cuid) :
            kind == 1 ? sscanf(line, "%d %d %*o %*u %*u %*d %*d %u %*u %u", &key, &id, &uid, &cuid) :
            sscanf(line, "%d %d %*o %*u %u %*u %u", &key, &id, &uid, &cuid);
        if (fields != 4 || !(payload_uid(scope, uid) || payload_uid(scope, cuid))) continue;
        int rc = kind == 0 ? shmctl(id, IPC_RMID, NULL) : kind == 1 ? msgctl(id, IPC_RMID, NULL) :
            semctl(id, 0, IPC_RMID);
        if (rc != 0 && errno != EINVAL && errno != EIDRM) clean = false;
    }
    fclose(file);
    return clean;
}

bool guardian_purge_payloads(const service_policy *service, int half) {
    if (!service) return true;
    /* One descriptor per directory level: let a deep tree use every one root may hold. */
    struct rlimit files;
    if (getrlimit(RLIMIT_NOFILE, &files) == 0 && files.rlim_cur < files.rlim_max) {
        files.rlim_cur = files.rlim_max;
        setrlimit(RLIMIT_NOFILE, &files);
    }
    purge_scope scope = {service, half};
    static const char *const roots[] = {"/tmp", "/var/tmp", "/dev/shm", "/dev/mqueue", "/run/lock"};
    bool clean = true;
    for (size_t i = 0; i < sizeof(roots) / sizeof(roots[0]); ++i) clean &= purge_tree(&scope, roots[i]);
    clean &= purge_ipc(&scope, "/proc/sysvipc/shm", 0);
    clean &= purge_ipc(&scope, "/proc/sysvipc/msg", 1);
    clean &= purge_ipc(&scope, "/proc/sysvipc/sem", 2);
    return clean;
}
