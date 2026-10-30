#define _GNU_SOURCE
/* Protected acceptance probe, run as root: installs the service's identity filter exactly
 * as the guardian does, then tries every way back to root or out of the payload accounts.
 * Running as root makes each refusal the filter's alone, never a missing capability.
 * Prints one JSON object of errno values (0 = the call succeeded). */
#include "guardian.h"
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
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
           "\"open_setuid\": %d, \"mknod_setuid\": %d}\n",
           setresuid_root, setresgid_root, setuid_root, setgroups_root, setgroups_empty, unshare_user, clone_user,
           clone3, keyring, payload_switch(PAYLOAD_UID, PAYLOAD_GID),
           payload_switch(PAYLOAD_UID + SERVICE_PAYLOAD_IDS - 1, PAYLOAD_GID + SERVICE_PAYLOAD_IDS - 1),
           payload_switch(PAYLOAD_UID + SERVICE_PAYLOAD_IDS, PAYLOAD_GID + SERVICE_PAYLOAD_IDS), chmod_plain,
           fchmod_setuid, fchmodat_setgid, open_setuid, mknod_setuid);
    return 0;
}
