#define _GNU_SOURCE
/* Protected acceptance probe, run as root: installs the service's identity filter exactly
 * as the guardian does, then tries every way back to root or out of the payload accounts.
 * Running as root makes each refusal the filter's alone, never a missing capability.
 * Prints one JSON object of errno values (0 = the call succeeded). */
#include "guardian.h"
#include <errno.h>
#include <linux/btrfs.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <linux/sched.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

static int outcome(long rc) { return rc == -1 ? errno : 0; }

/* A clone that must fail; if the filter let it through, the child leaves at once. */
static int clone_outcome(long rc) {
    if (rc == 0) _exit(0);
    if (rc > 0) waitpid((pid_t)rc, NULL, 0);
    return outcome(rc);
}

/* 0 when a child can become `uid`/`gid`, else the errno it met. */
static int payload_switch(uint32_t uid, uint32_t gid) {
    pid_t child = fork();
    if (child == 0) {
        if (syscall(SYS_setresgid, gid, gid, gid) != 0 || syscall(SYS_setresuid, uid, uid, uid) != 0) _exit(errno);
        _exit(0);
    }
    int status = 0;
    return child > 0 && waitpid(child, &status, 0) == child && WIFEXITED(status) ? WEXITSTATUS(status) : -1;
}

int main(void) {
    /* Controls before the filter: the kernel has openat2 and io_uring, and a ring made here
     * stands for one another process passes in. */
    char control_dir[] = "/tmp/autocontrol-control-XXXXXX";
    if (!mkdtemp(control_dir)) return 1;
    int control = open(control_dir, O_RDONLY | O_DIRECTORY);
    struct { unsigned long long flags, mode, resolve; } control_how = {O_CREAT | O_WRONLY, 0600, 0};
    long control_file = syscall(437 /* openat2 */, control, "control", &control_how, sizeof(control_how));
    int openat2_control = outcome(control_file);
    if (control_file >= 0) close((int)control_file);
    unlinkat(control, "control", 0);
    close(control);
    rmdir(control_dir);
    /* Off btrfs a subvolume request is ENOTTY: the filter's EPERM shows it never got there. */
    struct btrfs_ioctl_vol_args volume;
    memset(&volume, 0, sizeof(volume));
    snprintf(volume.name, sizeof(volume.name), "sub");
    int tmp = open("/tmp", O_RDONLY | O_DIRECTORY);
    int subvolume_control = outcome(ioctl(tmp, BTRFS_IOC_SUBVOL_CREATE, &volume));
    unsigned char control_params[120] = {0};
    long passed_ring = syscall(425 /* io_uring_setup */, 1, control_params);
    int io_uring_control = outcome(passed_ring);
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0 ||
        !guardian_confine_identities(&service_manifest, SERVICE_UID, SERVICE_GID)) {
        printf("{\"installed\": false, \"errno\": %d}\n", errno);
        return 1;
    }
    gid_t root_group = 0;
    struct clone_args args = {.exit_signal = SIGCHLD};
    int setresuid_root = outcome(syscall(SYS_setresuid, 0, 0, 0));
    int setresgid_root = outcome(syscall(SYS_setresgid, 0, 0, 0));
    int setuid_root = outcome(syscall(SYS_setuid, 0));
    int setgroups_root = outcome(syscall(SYS_setgroups, 1, &root_group));
    int setgroups_empty = outcome(syscall(SYS_setgroups, 0, NULL));
    int unshare_user = outcome(syscall(SYS_unshare, CLONE_NEWUSER));
    int clone_user = clone_outcome(syscall(SYS_clone, CLONE_NEWUSER | SIGCHLD, 0, 0, 0, 0));
    int clone3 = clone_outcome(syscall(SYS_clone3, &args, sizeof(args)));
    int keyring = outcome(syscall(SYS_keyctl, 0 /* KEYCTL_GET_KEYRING_ID */, -4 /* user keyring */, 0));
    /* No set-ID bit by any call; ordinary modes still work. */
    char directory[] = "/tmp/autocontrol-setid-XXXXXX";
    if (!mkdtemp(directory)) return 1;
    int dir = open(directory, O_RDONLY | O_DIRECTORY);
    int plain = openat(dir, "plain", O_CREAT | O_WRONLY, 0600);
    int chmod_plain = outcome(fchmod(plain, 0755));
    int fchmod_setuid = outcome(fchmod(plain, 04755));
    int fchmodat_setgid = outcome(fchmodat(dir, "plain", 02755, 0));
    int open_setuid = outcome(openat(dir, "created", O_CREAT | O_WRONLY, 04700));
    int mknod_setuid = outcome(mknodat(dir, "node", S_IFREG | 04700, 0));
    int fchmodat2_setuid = outcome(syscall(452 /* fchmodat2 */, dir, "plain", 04755, 0));
    int tmpfile_setuid = outcome(openat(dir, ".", O_TMPFILE | O_WRONLY, 04700));
    struct { unsigned long long flags, mode, resolve; } how = {O_CREAT | O_WRONLY, 0600, 0};
    int openat2_any = outcome(syscall(437 /* openat2 */, dir, "other", &how, sizeof(how)));
    unsigned char params[120] = {0};
    long ring = syscall(425 /* io_uring_setup */, 1, params);
    int io_uring = outcome(ring);
    if (ring >= 0) close((int)ring);
    int subvolume = outcome(ioctl(tmp, BTRFS_IOC_SUBVOL_CREATE, &volume));
    int setflags = outcome(ioctl(tmp, BTRFS_IOC_SUBVOL_SETFLAGS, &(unsigned long long){0}));
    int pipe_ends[2];
    int ordinary_ioctl = pipe(pipe_ends) == 0 ? outcome(ioctl(pipe_ends[0], FIONREAD, &(int){0})) : -1;
    close(tmp);
    int ring_enter = passed_ring >= 0 ?
        outcome(syscall(426 /* io_uring_enter */, (int)passed_ring, 0, 0, 0, NULL, 0)) : -1;
    int ring_register = passed_ring >= 0 ? outcome(syscall(427 /* io_uring_register */, (int)passed_ring,
                                                           9 /* IORING_REGISTER_PROBE */, NULL, 0)) : -1;
    close(plain);
    unlinkat(dir, "plain", 0);
    unlinkat(dir, "created", 0);
    unlinkat(dir, "node", 0);
    close(dir);
    rmdir(directory);
    printf("{\"installed\": true, \"setresuid_root\": %d, \"setresgid_root\": %d, \"setuid_root\": %d, "
           "\"setgroups_root\": %d, \"setgroups_empty\": %d, \"unshare_user\": %d, \"clone_user\": %d, "
           "\"clone3\": %d, \"keyring\": %d, \"payload_switch\": %d, \"payload_last\": %d, "
           "\"beyond_range\": %d, \"chmod_plain\": %d, \"fchmod_setuid\": %d, \"fchmodat_setgid\": %d, "
           "\"open_setuid\": %d, \"mknod_setuid\": %d, \"fchmodat2_setuid\": %d, \"tmpfile_setuid\": %d, "
           "\"openat2\": %d, \"io_uring\": %d, \"openat2_control\": %d, \"io_uring_control\": %d, "
           "\"ring_enter\": %d, \"ring_register\": %d, \"subvolume_control\": %d, \"subvolume\": %d, "
           "\"setflags\": %d, \"ordinary_ioctl\": %d}\n",
           setresuid_root, setresgid_root, setuid_root, setgroups_root, setgroups_empty, unshare_user, clone_user,
           clone3, keyring, payload_switch(PAYLOAD_UID, PAYLOAD_GID),
           payload_switch(PAYLOAD_UID + SERVICE_PAYLOAD_IDS - 1, PAYLOAD_GID + SERVICE_PAYLOAD_IDS - 1),
           payload_switch(PAYLOAD_UID + SERVICE_PAYLOAD_IDS, PAYLOAD_GID + SERVICE_PAYLOAD_IDS), chmod_plain,
           fchmod_setuid, fchmodat_setgid, open_setuid, mknod_setuid, fchmodat2_setuid, tmpfile_setuid, openat2_any,
           io_uring, openat2_control, io_uring_control, ring_enter, ring_register, subvolume_control, subvolume,
           setflags, ordinary_ioctl);
    return 0;
}
