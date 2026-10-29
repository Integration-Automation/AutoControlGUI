#define _GNU_SOURCE
/* The service's identity filter. CAP_SETUID and CAP_SETGID are what the service needs to
 * start payloads, and also what would let a compromised service become root, the client
 * or any group. The bounding set, NOROOT and no_new_privs only guard exec; this seccomp
 * filter guards the calls themselves, for the service and everything it starts:
 *  - setresuid / setresgid accept only the service's and the manifest's payload IDs;
 *  - setgroups accepts only an empty list (the filter cannot read a list's contents);
 *  - the other set*id calls fail;
 *  - no user namespace can be created (a mapping written with CAP_SETUID would reach any
 *    account), so unshare / clone with CLONE_NEWUSER fail and clone3, whose flags a
 *    filter cannot read, answers ENOSYS, which glibc meets by falling back to clone. */
#include "guardian.h"
#include <errno.h>
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
#define ID_LIMIT 40
#define ARGUMENT(index) (uint32_t)offsetof(struct seccomp_data, args[index])

typedef struct { struct sock_filter code[FILTER_LIMIT]; unsigned short count; bool overflow; } program;
typedef struct { uint32_t values[ID_LIMIT]; size_t count; } id_set;

static void emit(program *filter, struct sock_filter instruction) {
    if (filter->count < FILTER_LIMIT) filter->code[filter->count++] = instruction;
    else filter->overflow = true;
}

static void add_id(id_set *set, uint32_t value) {
    for (size_t i = 0; i < set->count; ++i) if (set->values[i] == value) return;
    if (set->count < ID_LIMIT) set->values[set->count++] = value;
}

static void deny(program *filter, long number, int error) {
    emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)number, 0, 1));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | (uint32_t)error));
}

/* Fails `number` when its first argument carries CLONE_NEWUSER. */
static void deny_new_user(program *filter, long number) {
    emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)number, 0, 4));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, ARGUMENT(0)));
    emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, CLONE_NEWUSER, 0, 1));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM));
    emit(filter, (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW));
}

/* Allows `number` only when each of its three arguments is in `set` or -1 (unchanged). */
static void only_ids(program *filter, long number, const id_set *set) {
    unsigned matches = (unsigned)set->count + 1, block = matches + 2;
    emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (uint32_t)number, 0,
                                              (unsigned char)(3 * block + 1)));
    for (unsigned argument = 0; argument < 3; ++argument) {
        emit(filter, (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS, ARGUMENT(argument)));
        for (unsigned i = 0; i < matches; ++i) {
            uint32_t value = i < set->count ? set->values[i] : UINT32_MAX;
            emit(filter, (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, value,
                                                      (unsigned char)(matches - i), 0));
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
    add_id(&users, service_uid);
    add_id(&groups, service_gid);
    for (size_t i = 0; i < policy->policy_count; ++i) {
        add_id(&users, policy->policies[i].payload_uid);
        add_id(&groups, policy->policies[i].payload_gid);
    }
    if (users.count >= ID_LIMIT || groups.count >= ID_LIMIT) { errno = E2BIG; return false; }
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
