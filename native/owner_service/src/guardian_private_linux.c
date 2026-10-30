#define _GNU_SOURCE
/* An epoch's service and every helper it starts run in a mount namespace and an IPC namespace
 * of their own, which the guardian makes when it starts the service. A fresh tmpfs stands over
 * each world-writable root (the default purge roots and the manifest's), and SysV IPC objects
 * and POSIX message queues belong to the epoch alone. What a helper leaves there is out of
 * every other user's sight and reach, and goes with the epoch: once its last process is killed
 * the namespaces and their mounts are gone, so nothing of it can wait for the next helper with
 * the same ID. The guardian's purge still walks the host's roots, for anything a helper put
 * where these mounts do not reach. */
#include "guardian.h"
#include <errno.h>
#include <stdlib.h>
#include <sys/mount.h>
#include <sys/stat.h>

/* A fresh tmpfs over `path` when it names a directory under root-only directories; a root
 * that does not exist has nothing to hide. */
static bool private_root(const char *path) {
    char resolved[4096];
    if (!realpath(path, resolved)) return errno == ENOENT || errno == ENOTDIR;
    struct stat status;
    if (lstat(resolved, &status) != 0 || !S_ISDIR(status.st_mode)) return true;
    if (!guardian_path_anchored(resolved)) return false;
    return mount("autocontrol-epoch", resolved, "tmpfs", MS_NOSUID | MS_NODEV, "mode=1777") == 0;
}

bool guardian_private_epoch(const guardian_manifest *manifest) {
    /* A slave of the host's mounts: none of these reach the host, the host's unmounts reach in. */
    if (mount(NULL, "/", NULL, MS_REC | MS_SLAVE, NULL) != 0) return false;
    static const char *const roots[] = {"/tmp", "/var/tmp", "/dev/shm", "/run/lock", "/var/crash"};
    for (size_t i = 0; i < sizeof(roots) / sizeof(roots[0]); ++i)
        if (!private_root(roots[i])) return false;
    for (size_t i = 0; i < manifest->purge_root_count; ++i)
        if (!private_root(manifest->purge_roots[i])) return false;
    /* The epoch's own message queues, where tools look for them (the IPC namespace is new). */
    struct stat queues;
    if (lstat("/dev/mqueue", &queues) == 0 && S_ISDIR(queues.st_mode) &&
        mount("mqueue", "/dev/mqueue", "mqueue", MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) != 0) return false;
    return true;
}
