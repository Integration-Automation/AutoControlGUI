#define _GNU_SOURCE
/* Protected acceptance, run as root: the purge's paths that only a fault or a live user
 * reaches, each in its own forked child with the purge's own mount namespace. Faults are
 * injected around the real purge code: a listing that fails, a mount placed on an entry while
 * the walk reads its directory, a payload directory renamed behind the walk, and the mount API
 * refused (no message queues, or /dev/mqueue missing or present). Prints one JSON object. */
#include <dirent.h>
#include <stdarg.h>
#include <stdio.h>
#include <sys/syscall.h>
#include <unistd.h>

static long test_syscall(long number, ...);
static struct dirent *test_readdir(DIR *listing);
#define syscall test_syscall
#define readdir test_readdir
#include "../src/guardian_purge_linux.c"
#undef syscall
#undef readdir
long syscall(long number, ...);
struct dirent *readdir(DIR *listing);

#include <sys/wait.h>
#include <mqueue.h>

#define BASE 2100000000u /* A payload range nothing else uses. */

static int fsopen_error;
static long test_syscall(long number, ...) {
    va_list arguments;
    va_start(arguments, number);
    long a = va_arg(arguments, long), b = va_arg(arguments, long), c = va_arg(arguments, long);
    long d = va_arg(arguments, long), e = va_arg(arguments, long), f = va_arg(arguments, long);
    va_end(arguments);
    if (fsopen_error && number == SYS_fsopen) { errno = fsopen_error; return -1; }
    return syscall(number, a, b, c, d, e, f);
}

/* One hook per scenario, on the listing of one directory (by inode). */
enum { HOOK_NONE, HOOK_READ_ERROR, HOOK_MOUNT_ON_ENTRY, HOOK_RENAME_PARENT_ENTRY };
static int hook;
static dev_t hook_device;
static ino_t hook_directory;
static bool hook_done;
static char hook_name[64], hook_path[256], hook_target[256];
static dev_t parent_device; /* HOOK_RENAME_PARENT_ENTRY: the listing that meets the new name. */
static ino_t parent_directory;
static bool replayed;

static struct dirent *test_readdir(DIR *listing) {
    struct stat status;
    bool known = hook && fstat(dirfd(listing), &status) == 0;
    bool watched = known && !hook_done && status.st_ino == hook_directory && status.st_dev == hook_device;
    if (watched && hook == HOOK_READ_ERROR) { hook_done = true; errno = EIO; return NULL; }
    if (watched && hook == HOOK_RENAME_PARENT_ENTRY) { hook_done = true; rename(hook_path, hook_target); }
    struct dirent *entry = readdir(listing);
    /* A filesystem that lists a renamed entry again (ext4's hash order may; tmpfs since 6.13
     * stops at the end it saw on opening): the parent's listing yields the new name once. */
    if (!entry && hook_done && !replayed && hook == HOOK_RENAME_PARENT_ENTRY && known &&
        status.st_ino == parent_directory && status.st_dev == parent_device) {
        static struct dirent again;
        replayed = true;
        snprintf(again.d_name, sizeof(again.d_name), "%s", strrchr(hook_target, '/') + 1);
        return &again;
    }
    if (watched && hook == HOOK_MOUNT_ON_ENTRY && entry && !strcmp(entry->d_name, hook_name)) {
        hook_done = true;
        mount("cover", hook_path, "tmpfs", 0, "size=1m");
    }
    return entry;
}

static service_launch_policy launch = {.payload_uid = BASE, .payload_gid = BASE};
static service_policy policy = {.policies = &launch, .policy_count = 1};
static guardian_manifest manifest = {.service = &policy};

/* Where the hook watches: a directory's device and inode. */
static void watch(const char *path, dev_t *device, ino_t *inode) {
    struct stat status;
    if (stat(path, &status) != 0) { *device = 0; *inode = 0; return; }
    *device = status.st_dev;
    *inode = status.st_ino;
}

/* Fixtures live under a fresh directory only root can enter, made with mkdtemp: nobody can have
 * planted a name or a link in them. Each step must succeed. */
static bool fixture_root(char *path) {
    return mkdtemp(path) != NULL;
}

static bool payload_file(const char *path) {
    int file = open(path, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW | O_CLOEXEC, 0600);
    bool made = file >= 0 && write(file, "payload", 7) == 7 && fchown(file, BASE, BASE) == 0;
    if (file >= 0) close(file);
    return made;
}

static bool payload_directory(const char *path) {
    return mkdir(path, 0700) == 0 && lchown(path, BASE, BASE) == 0;
}

static bool payload_queue(const char *name) {
    pid_t child = fork();
    if (child == 0) {
        if (setgid(BASE) != 0 || setuid(BASE) != 0) _exit(2);
        mqd_t queue = mq_open(name, O_CREAT | O_RDWR, 0600, NULL);
        _exit(queue != (mqd_t)-1 && mq_send(queue, "left", 4, 0) == 0 ? 0 : 1);
    }
    int status = 0;
    return child > 0 && waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

/* Runs one scenario in a child; true when its check holds. */
static bool scenario(const char *name, bool (*body)(void)) {
    fflush(stdout);
    pid_t child = fork();
    if (child == 0) {
        if (!guardian_purge_unshare()) _exit(3);
        _exit(body() ? 0 : 1);
    }
    int status = 0;
    bool held = child > 0 && waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0;
    printf("%s\"%s\": %s", strcmp(name, "read_error") ? ", " : "", name, held ? "true" : "false");
    return held;
}

static char path_buffer[256];

static const char *under(const char *top, const char *name) {
    snprintf(path_buffer, sizeof(path_buffer), "%s/%s", top, name);
    return path_buffer;
}

static bool read_error(void) {
    char top[] = "/tmp/autocontrol-fault-read-XXXXXX";
    if (!fixture_root(top) || !payload_file(under(top, "left"))) return false;
    hook = HOOK_READ_ERROR;
    watch(top, &hook_device, &hook_directory);
    guardian_purge_outcome outcome = guardian_purge_payloads(&manifest, -1);
    unlink(under(top, "left"));
    rmdir(top);
    return hook_done && outcome == PURGE_INCOMPLETE; /* Never a clean purge that read nothing. */
}

static bool mounted_during_walk(void) {
    char top[] = "/tmp/autocontrol-fault-mount-XXXXXX";
    if (!fixture_root(top)) return false;
    if (!payload_directory(under(top, "victim")) || !payload_file(under(top, "victim/data"))) {
        unlink(under(top, "victim/data"));
        rmdir(under(top, "victim"));
        rmdir(top);
        return false;
    }
    hook = HOOK_MOUNT_ON_ENTRY;
    watch(top, &hook_device, &hook_directory);
    snprintf(hook_name, sizeof(hook_name), "victim");
    snprintf(hook_path, sizeof(hook_path), "%s/victim", top);
    guardian_purge_outcome outcome = guardian_purge_payloads(&manifest, -1);
    struct stat left;
    bool gone = lstat(hook_path, &left) != 0;
    umount2(hook_path, MNT_DETACH);
    unlink(under(top, "victim/data"));
    rmdir(hook_path);
    rmdir(top);
    return hook_done && outcome == PURGE_CLEAN && gone; /* Laid bare and removed. */
}

static bool renamed_behind(void) {
    char top[] = "/dev/shm/autocontrol-fault-rename-XXXXXX";
    if (!fixture_root(top)) return false;
    if (!payload_directory(under(top, "first")) || !payload_file(under(top, "first/data"))) {
        unlink(under(top, "first/data"));
        rmdir(under(top, "first"));
        rmdir(top);
        return false;
    }
    hook = HOOK_RENAME_PARENT_ENTRY;
    watch(under(top, "first"), &hook_device, &hook_directory);
    watch(top, &parent_device, &parent_directory);
    snprintf(hook_path, sizeof(hook_path), "%s/first", top);
    snprintf(hook_target, sizeof(hook_target), "%s/zz-moved", top);
    guardian_purge_outcome outcome = guardian_purge_payloads(&manifest, -1);
    unlink(under(top, "zz-moved/data"));
    rmdir(under(top, "zz-moved"));
    unlink(under(top, "first/data"));
    rmdir(hook_path);
    rmdir(top);
    return hook_done && outcome == PURGE_INCOMPLETE; /* Met again: the purge runs again. */
}

static bool no_message_queues(void) {
    fsopen_error = ENODEV; /* A kernel without POSIX message queues: none to purge. */
    return guardian_purge_payloads(&manifest, -1) == PURGE_CLEAN;
}

static bool mount_api_refused_no_mqueue(void) {
    fsopen_error = EPERM; /* Filtered, and no /dev/mqueue (an empty /dev, in this namespace). */
    if (mount("dev", "/dev", "tmpfs", 0, "size=1m,mode=0755") != 0) return false;
    return guardian_purge_payloads(&manifest, -1) == PURGE_INCOMPLETE;
}

static bool mount_api_refused_with_mqueue(void) {
    fsopen_error = EPERM; /* Filtered, and /dev/mqueue the mqueue filesystem: purged through it. */
    if (mount("dev", "/dev", "tmpfs", 0, "size=1m,mode=0755") != 0 || mkdir("/dev/mqueue", 01777) != 0 ||
        mount("mqueue", "/dev/mqueue", "mqueue", 0, NULL) != 0) return false;
    const char *queue = "/autocontrol-fault-queue";
    bool made = payload_queue(queue);
    guardian_purge_outcome outcome = guardian_purge_payloads(&manifest, -1);
    mqd_t left = mq_open(queue, O_RDONLY);
    bool gone = left == (mqd_t)-1 && errno == ENOENT;
    if (!gone) { if (left != (mqd_t)-1) mq_close(left); mq_unlink(queue); }
    return made && outcome == PURGE_CLEAN && gone;
}

int main(void) {
    if (geteuid() != 0) { printf("{\"root\": false}\n"); return 77; }
    printf("{");
    bool held = scenario("read_error", read_error);
    held &= scenario("mounted_during_walk", mounted_during_walk);
    held &= scenario("renamed_behind", renamed_behind);
    held &= scenario("no_message_queues", no_message_queues);
    held &= scenario("mount_api_refused_no_mqueue", mount_api_refused_no_mqueue);
    held &= scenario("mount_api_refused_with_mqueue", mount_api_refused_with_mqueue);
    printf("}\n");
    return held ? 0 : 1;
}
