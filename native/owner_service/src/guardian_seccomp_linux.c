#define _GNU_SOURCE
/* The service's identity filter. CAP_SETUID and CAP_SETGID are what the service needs to
 * start payloads, and also what would let a compromised service become root, the client
 * or any group. The bounding set, NOROOT and no_new_privs only guard exec; this seccomp
 * filter guards the calls themselves, for the service and everything it starts:
 *  - setresuid / setresgid accept only the service's IDs and the manifest's payload ranges;
 *  - setgroups accepts only an empty list (the filter cannot read a list's contents);
 *  - keyctl, add_key and request_key fail: per-user keyrings outlive the IDs' processes;
 *  - no file gets a set-user-ID or set-group-ID bit (chmod family, a creating open, mknod):
 *    a payload file the purge missed could otherwise hand a payload ID to anyone who runs
 *    it; btrfs subvolume and snapshot creation and subvolume flags fail (a payload's own
 *    subvolume cannot be moved into the purge's quarantine, and a read-only one cannot be
 *    purged); openat2, whose mode a filter cannot read, and io_uring, whose operations never pass
 *    a filter, answer ENOSYS: setting a ring up, and entering or registering one another
 *    process made and passed over a socket;
 *  - the other set*id calls fail;
 *  - no user namespace can be created (a mapping written with CAP_SETUID would reach any
 *    account), so unshare / clone with CLONE_NEWUSER fail and clone3, whose flags a
 *    filter cannot read, answers ENOSYS, which glibc meets by falling back to clone. */
#include "guardian.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/btrfs.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <sched.h>
#include <stddef.h>
#include <sys/prctl.h>
#include <sys/syscall.h>

#if defined(__x86_64__)
#define FILTER_ARCH AUDIT_ARCH_X86_64
#elif defined(__aarch64__)
#define FILTER_ARCH AUDIT_ARCH_AARCH64
#else
#error "owner service identity filter: unsupported architecture"
#endif

#define FILTER_LIMIT 1024
#define RANGE_LIMIT 20
#define ARGUMENT(index) (uint32_t)offsetof(struct seccomp_data, args[index])

typedef struct { struct sock_filter code[FILTER_LIMIT]; unsigned short count; bool overflow; } program;
typedef struct { uint32_t low[RANGE_LIMIT], high[RANGE_LIMIT]; size_t count; } id_set;

static void emit(program *filter, struct sock_filter instruction) {
    if (filter->count < FILTER_LIMIT) filter->code[filter->count++] = instruction;
    else filter->overflow = true;
}

static void add_range(id_set *set, uint32_t low, uint32_t high) {
    for (size_t i = 0; i < set->count; ++i) if (set->low[i] == low && set->high[i] == high) return;
    if (set->count < RANGE_LIMIT) { set->low[set->count] = low; set->high[set->count++] = high; }
    else set->count = RANGE_LIMIT + 1;
}

static void deny(program *filter, long number, int error) {
    emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)number, 0, 1));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | (uint32_t)error));
}

/* Fails `number` when its first argument carries CLONE_NEWUSER. */
#ifndef SYS_fchmodat2
#define SYS_fchmodat2 452
#endif
#ifndef SYS_openat2
#define SYS_openat2 437
#endif
#ifndef SYS_io_uring_setup
#define SYS_io_uring_setup 425
#define SYS_io_uring_enter 426
#define SYS_io_uring_register 427
#endif
#define SET_ID_BITS 06000u
#define CREATING ((uint32_t)(O_CREAT | (O_TMPFILE & ~O_DIRECTORY)))

/* Fails `number` with EPERM when argument `mode` carries a set-ID bit; with `flags` at 0 or
 * above, only while that argument asks to create a file. */
static void deny_set_id_mode(program *filter, long number, int mode, int flags) {
    emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)number, 0, flags < 0 ? 4 : 6));
    if (flags >= 0) {
        emit(filter, (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, ARGUMENT(flags)));
        emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, CREATING, 0, 3));
    }
    emit(filter, (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, ARGUMENT(mode)));
    emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, SET_ID_BITS, 0, 1));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW));
}

/* Fails ioctl with EPERM for each request in `requests` (argument 1, a 32-bit command). */
static void deny_ioctls(program *filter, const uint32_t *requests, size_t count) {
    emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)SYS_ioctl, 0,
                                              (unsigned char)(count + 3))); /* Past both returns. */
    emit(filter, (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, ARGUMENT(1)));
    for (size_t i = 0; i < count; ++i)
        emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, requests[i],
                                                  (unsigned char)(count - i), 0));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM));
}

static void deny_subvolumes(program *filter) {
    static const uint32_t requests[] = {BTRFS_IOC_SNAP_CREATE, BTRFS_IOC_SUBVOL_CREATE, BTRFS_IOC_SNAP_CREATE_V2,
                                        BTRFS_IOC_SUBVOL_CREATE_V2, BTRFS_IOC_SUBVOL_SETFLAGS};
    deny_ioctls(filter, requests, sizeof(requests) / sizeof(requests[0]));
}

static void deny_set_id_files(program *filter) {
#ifdef SYS_chmod
    deny_set_id_mode(filter, SYS_chmod, 1, -1);
    deny_set_id_mode(filter, SYS_creat, 1, -1);
    deny_set_id_mode(filter, SYS_open, 2, 1);
    deny_set_id_mode(filter, SYS_mknod, 1, -1);
#endif
    deny_set_id_mode(filter, SYS_fchmod, 1, -1);
    deny_set_id_mode(filter, SYS_fchmodat, 2, -1);
    deny_set_id_mode(filter, SYS_fchmodat2, 2, -1);
    deny_set_id_mode(filter, SYS_openat, 3, 2);
    deny_set_id_mode(filter, SYS_mknodat, 2, -1);
    deny(filter, SYS_openat2, ENOSYS);
    deny(filter, SYS_io_uring_setup, ENOSYS);
    deny(filter, SYS_io_uring_enter, ENOSYS);
    deny(filter, SYS_io_uring_register, ENOSYS);
}

static void deny_new_user(program *filter, long number) {
    emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)number, 0, 4));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, ARGUMENT(0)));
    emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, CLONE_NEWUSER, 0, 1));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW));
}

/* Allows `number` only when each of its three arguments lies in one of `set`'s ranges or
 * is -1 (unchanged). Per argument: load; -1 passes; each range is three instructions
 * (below low: next range; above high: next range; else on to the next argument); then
 * EPERM. */
static void only_ids(program *filter, long number, const id_set *set) {
    unsigned ranges = (unsigned)set->count, block = 3 + 3 * ranges, after = block;
    emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)number, 0,
                                              (unsigned char)(3 * block + 1)));
    for (unsigned argument = 0; argument < 3; ++argument) {
        emit(filter, (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, ARGUMENT(argument)));
        emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, UINT32_MAX,
                                                  (unsigned char)(after - 2), 0));
        for (unsigned i = 0; i < ranges; ++i) {
            unsigned at = 2 + 3 * i;
            emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JGE | BPF_K, set->low[i], 0, 2));
            emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JGT | BPF_K, set->high[i], 1, 0));
            emit(filter, (struct sock_filter)BPF_STMT(BPF_JMP | BPF_JA, after - (at + 2) - 1));
        }
        emit(filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM));
    }
    emit(filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW));
}

static void empty_groups_only(program *filter) {
    emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)SYS_setgroups, 0, 4));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, ARGUMENT(0)));
    emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 0, 1, 0));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW));
}

bool guardian_confine_identities(const service_policy *policy, uint32_t service_uid, uint32_t service_gid) {
    id_set users = {.count = 0}, groups = {.count = 0};
    add_range(&users, service_uid, service_uid);
    add_range(&groups, service_gid, service_gid);
    for (size_t i = 0; i < policy->policy_count; ++i) {
        const service_launch_policy *entry = &policy->policies[i];
        add_range(&users, entry->payload_uid, entry->payload_uid + SERVICE_PAYLOAD_IDS - 1);
        add_range(&groups, entry->payload_gid, entry->payload_gid + SERVICE_PAYLOAD_IDS - 1);
    }
    if (users.count > RANGE_LIMIT || groups.count > RANGE_LIMIT) { errno = E2BIG; return false; }
    static program filter;
    filter.count = 0;
    filter.overflow = false;
    emit(&filter, (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, (uint32_t)offsetof(struct seccomp_data, arch)));
    emit(&filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, FILTER_ARCH, 1, 0));
    emit(&filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS));
    emit(&filter, (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, (uint32_t)offsetof(struct seccomp_data, nr)));
#if defined(__x86_64__)
    /* x32 numbers carry this bit and would reach the same calls under other numbers. */
    emit(&filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JGE | BPF_K, 0x40000000u, 0, 1));
    emit(&filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS));
#endif
    static const long refused[] = {SYS_setuid, SYS_setreuid, SYS_setfsuid, SYS_setgid, SYS_setregid, SYS_setfsgid};
    for (size_t i = 0; i < sizeof(refused) / sizeof(refused[0]); ++i) deny(&filter, refused[i], EPERM);
    deny(&filter, SYS_clone3, ENOSYS);
    /* Per-user kernel keyrings outlive every process of an ID: a later helper with the same
     * ID would find them. Nothing here needs a keyring. */
    deny(&filter, SYS_keyctl, EPERM);
    deny(&filter, SYS_add_key, EPERM);
    deny(&filter, SYS_request_key, EPERM);
    deny_set_id_files(&filter);
    deny_subvolumes(&filter);
    deny_new_user(&filter, SYS_clone);
    deny_new_user(&filter, SYS_unshare);
    empty_groups_only(&filter);
    only_ids(&filter, SYS_setresuid, &users);
    only_ids(&filter, SYS_setresgid, &groups);
    emit(&filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW));
    if (filter.overflow) { errno = E2BIG; return false; }
    struct sock_fprog program_view = {.len = filter.count, .filter = filter.code};
    return prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program_view, 0, 0) == 0;
}
