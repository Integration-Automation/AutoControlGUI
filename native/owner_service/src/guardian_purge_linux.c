#define _GNU_SOURCE
/* After an epoch is killed nothing runs as a payload ID, so what those IDs left behind is
 * removed before the IDs are handed out again: files under the shared temporary
 * directories and SysV IPC objects, as systemd does for DynamicUser with RemoveIPC. A
 * later helper with the same ID then finds nothing of an earlier one, and tmpfs pages a
 * killed helper left charged are released. Directories are walked by descriptor, never
 * through a link or into another filesystem, and entries are removed relative to the
 * directory that was opened, so no rename on the way can redirect a removal. */
#include "guardian.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/ipc.h>
#include <sys/msg.h>
#include <sys/sem.h>
#include <sys/shm.h>
#include <sys/stat.h>
#include <unistd.h>

#define PURGE_DEPTH 32

static const service_policy *purged_service;
static int purged_half; /* 0 or 1: one epoch's half of every range; -1: both. */

static bool in_half(uint32_t id, uint32_t base) {
    uint32_t low = purged_half < 0 ? base : base + (uint32_t)purged_half * SERVICE_EPOCH_IDS;
    uint32_t span = purged_half < 0 ? SERVICE_PAYLOAD_IDS : SERVICE_EPOCH_IDS;
    return id >= low && id - low < span;
}

static bool payload_id(const service_policy *service, uint32_t id) {
    (void)service;
    for (size_t i = 0; i < purged_service->policy_count; ++i) {
        const service_launch_policy *entry = &purged_service->policies[i];
        if (in_half(id, entry->payload_uid) || in_half(id, entry->payload_gid)) return true;
    }
    return false;
}

static size_t purge_directory(const service_policy *service, int directory, dev_t device, unsigned depth);

static size_t purge_entry(const service_policy *service, int directory, const char *name, dev_t device,
                          unsigned depth) {
    struct stat status;
    if (fstatat(directory, name, &status, AT_SYMLINK_NOFOLLOW) != 0) return 0;
    size_t removed = 0;
    if (S_ISDIR(status.st_mode) && status.st_dev == device && depth < PURGE_DEPTH) {
        int child = openat(directory, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        struct stat opened;
        if (child >= 0) {
            if (fstat(child, &opened) == 0 && opened.st_ino == status.st_ino && opened.st_dev == status.st_dev)
                removed += purge_directory(service, child, device, depth + 1);
            close(child);
        }
    }
    if (payload_id(service, status.st_uid) &&
        unlinkat(directory, name, S_ISDIR(status.st_mode) ? AT_REMOVEDIR : 0) == 0) ++removed;
    return removed;
}

static size_t purge_directory(const service_policy *service, int directory, dev_t device, unsigned depth) {
    int copy = dup(directory);
    if (copy < 0) return 0;
    DIR *listing = fdopendir(copy);
    if (!listing) { close(copy); return 0; }
    size_t removed = 0;
    for (struct dirent *entry; (entry = readdir(listing));) {
        if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
        removed += purge_entry(service, directory, entry->d_name, device, depth);
    }
    closedir(listing);
    return removed;
}

/* Each /proc/sysvipc table: the ID column and the owner and creator UID columns. */
static size_t purge_ipc(const service_policy *service, const char *table, int kind) {
    FILE *file = fopen(table, "re");
    if (!file) return 0;
    char line[512];
    size_t removed = 0;
    if (!fgets(line, sizeof(line), file)) { fclose(file); return 0; }
    while (fgets(line, sizeof(line), file)) {
        int key, id;
        unsigned uid = 0, cuid = 0;
        int fields = kind == 0 ? sscanf(line, "%d %d %*o %*u %*d %*d %*u %u %*u %u", &key, &id, &uid, &cuid) :
            kind == 1 ? sscanf(line, "%d %d %*o %*u %*u %*d %*d %u %*u %u", &key, &id, &uid, &cuid) :
            sscanf(line, "%d %d %*o %*u %u %*u %u", &key, &id, &uid, &cuid);
        if (fields != 4 || !(payload_id(service, uid) || payload_id(service, cuid))) continue;
        int rc = kind == 0 ? shmctl(id, IPC_RMID, NULL) : kind == 1 ? msgctl(id, IPC_RMID, NULL) :
            semctl(id, 0, IPC_RMID);
        if (rc == 0) ++removed;
    }
    fclose(file);
    return removed;
}

size_t guardian_purge_payloads(const service_policy *service, int half) {
    if (!service) return 0;
    purged_service = service;
    purged_half = half;
    static const char *const roots[] = {"/tmp", "/var/tmp", "/dev/shm", "/dev/mqueue"};
    size_t removed = 0;
    for (size_t i = 0; i < sizeof(roots) / sizeof(roots[0]); ++i) {
        int root = open(roots[i], O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        struct stat status;
        if (root < 0) continue;
        if (fstat(root, &status) == 0) removed += purge_directory(service, root, status.st_dev, 0);
        close(root);
    }
    removed += purge_ipc(service, "/proc/sysvipc/shm", 0);
    removed += purge_ipc(service, "/proc/sysvipc/msg", 1);
    removed += purge_ipc(service, "/proc/sysvipc/sem", 2);
    return removed;
}
