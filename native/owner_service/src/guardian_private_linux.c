#define _GNU_SOURCE
/* An epoch's service and every helper it starts run in a mount namespace and an IPC namespace
 * of their own, which the guardian makes when it starts the service. A fresh tmpfs stands over
 * each root a helper could write (the default purge roots and the manifest's), with the mode
 * and owner the host's directory has and its mount's noexec, nosymfollow and read-only flags,
 * and SysV IPC objects and POSIX message queues belong to the epoch alone. What a helper
 * leaves there is out of every other user's sight and reach, and is gone once the epoch's
 * last process is, unless a helper itself handed a descriptor into it to a process outside
 * the epoch. A root that does not exist when the epoch starts is
 * not covered until the next epoch; the guardian's purge walks the host's roots as before.
 * Each start checks again that no root, as the host now resolves it, hides the listener or the
 * service executable: a root made later as a link over one stops the epoch rather than hiding it. */
#include "guardian.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <unistd.h>

static bool refused(const char *path) {
    int error = errno;
    fprintf(stderr, "autocontrol-owner-guardian: cannot make the epoch's private %s (errno %d); "
                    "the epoch does not start\n", path, error);
    errno = error;
    return false;
}

/* A fresh tmpfs over `path`, as the host's directory is: same mode, same owner, no exec where
 * the host's mount has none, empty. Its pages count against the epoch's memory limit. */
static bool private_root(const char *path) {
    char resolved[4096];
    if (!realpath(path, resolved)) return errno == ENOENT || errno == ENOTDIR || refused(path);
    struct stat status;
    if (lstat(resolved, &status) != 0) return refused(path);
    if (!S_ISDIR(status.st_mode)) return true;
    if (!guardian_path_anchored(resolved)) return refused(path);
    struct statvfs mounted;
    if (statvfs(resolved, &mounted) != 0) return refused(path);
    unsigned long flags = guardian_private_mount_flags(mounted.f_flag);
    char options[96];
    snprintf(options, sizeof(options), "mode=%o,uid=%u,gid=%u", (unsigned)(status.st_mode & 07777),
             (unsigned)status.st_uid, (unsigned)status.st_gid);
    return mount("autocontrol-epoch", resolved, "tmpfs", flags, options) == 0 || refused(path);
}

bool guardian_private_epoch(const guardian_manifest *manifest) {
    if (!guardian_private_roots_hide_nothing(manifest, false)) {
        fprintf(stderr, "autocontrol-owner-guardian: a private root now hides a path the epoch needs, or "
                        "the path cannot be resolved; the epoch does not start\n");
        return false;
    }
    /* A slave of the host's mounts: none of these reach the host, the host's unmounts reach in. */
    if (mount(NULL, "/", NULL, MS_REC | MS_SLAVE, NULL) != 0) return refused("/");
    for (size_t i = 0; guardian_private_root(i); ++i)
        if (!private_root(guardian_private_root(i))) return false;
    for (size_t i = 0; i < manifest->purge_root_count; ++i)
        if (!private_root(manifest->purge_roots[i])) return false;
    /* The epoch's own message queues, where tools look for them (the IPC namespace is new). */
    struct stat queues;
    if (lstat("/dev/mqueue", &queues) == 0 && S_ISDIR(queues.st_mode) &&
        mount("mqueue", "/dev/mqueue", "mqueue", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) != 0)
        return refused("/dev/mqueue");
    return true;
}
