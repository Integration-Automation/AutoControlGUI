#define _GNU_SOURCE
/* Owner service manifest template. Copy to owner_manifest.c, replace every value
 * marked EDIT, review it, and build with build.sh. The service and the guardian are
 * compiled against this file: nothing in it can be changed by an argument, an
 * environment value or a request at run time. Keep the compiled copy root-owned. Keep the
 * _GNU_SOURCE line above first: guardian.h uses POSIX calls it declares. */
#include "guardian.h"

/* EDIT: accounts. Guardian is root. The service account runs the service. One client
 * account may open top-level leases. Helpers run as IDs from a payload range: each helper
 * gets PAYLOAD_UID + k and PAYLOAD_GID + k, for k below 128, so no two live helpers share
 * an account, even across retiring epochs and the current one. The range needs no
 * accounts, only 128 user and 128 group IDs at 1000 or above that nothing else uses: not
 * systemd-homed's 60001-60513 nor systemd's dynamic 61184-65519, nor any site allocation.
 * The guardian refuses to start if the host's user or group database knows any of them.
 * The socket group owns the listener and the client account is a supplementary member
 * of it; no helper ever is. Every client below is also named in the listener's ACL. */
#define SERVICE_UID 990u
#define SERVICE_GID 990u
#define PAYLOAD_UID 50000u
#define PAYLOAD_GID 50000u
#define SOCKET_GID 992u
#define CLIENT_UID 1000u
#define CLIENT_GID 1000u

/* EDIT: the client's namespaces, from `stat -L -c '%d %i' /proc/<client pid>/ns/{user,pid,mnt,cgroup}`
 * (the nsfs device, then the inode of each). */
#define NS_DEVICE 4ULL
#define NS_USER 4026531837ULL
#define NS_PID 4026531836ULL
#define NS_MOUNT 4026531841ULL
#define NS_CGROUP 4026531835ULL

/* EDIT: one policy per helper program. Each program's argv is fixed here and must
 * match, element for element, the argv listed for it in the client binding file
 * /etc/je_auto_control/owner_service.json. */
static const char *const worker_argv[] = {"/usr/bin/python3", "-I", "-u", "-m",
                                          "je_auto_control.utils.agent_runtime.native_worker"};
static const service_launch_policy policies[] = {{
    .id = 1, .executable = "/usr/bin/python3", .cwd = "/", .fixed_argv = worker_argv, .fixed_argc = 5,
    .env = NULL, .envc = 0, .max_client_arguments = 0, .payload_uid = PAYLOAD_UID, .payload_gid = PAYLOAD_GID,
}};

const service_policy service_manifest = {
    .guardian = {0, 0},
    .clients = {{CLIENT_UID, CLIENT_GID}},
    .client_count = 1,
    .policies = policies,
    .policy_count = sizeof(policies) / sizeof(policies[0]),
    .lease_lifetime_ns = 60000000000ULL,  /* Clients renew while a helper stays in use. */
    .lease_max_age_ns = 86400000000000ULL, /* No helper outlives a day. */
    .socket_gid = SOCKET_GID,
    /* Leases one client may use per epoch. When they are spent, or every record is used,
     * and no lease or connection is open, the service drains and the guardian grants a
     * fresh epoch. Until then a spent epoch answers new opens with CAPACITY, so one
     * long-lived helper delays the rollover: keep both at the maximum, 32. A policy that
     * may start nested children needs record_capacity above client_lease_quota, so a
     * spent epoch still has record slots for its helpers' children. */
    .client_lease_quota = 32,
    /* Child leases one helper may open per epoch, if its policy may start nested children. */
    .nested_lease_quota = 4,
    .record_capacity = 32,
    /* EDIT: per helper, including its nested children. The Python worker with OpenCV and
     * OCR loaded needs about 1 GiB; a fork bomb or leak stops here instead of the host. */
    .record_pids_max = 256,
    /* Connections one account may hold at once, at most 8: the client and the payload
     * account each keep at least half of the service's 16. */
    .connections_per_account = 8,
    .record_memory_max = 2ULL << 30,
};

static const guardian_client clients[] = {
    {CLIENT_UID, CLIENT_GID, {NS_DEVICE, NS_USER, NS_PID, NS_MOUNT, NS_CGROUP}, 1},
};

/* EDIT: paths and identity. The subtree must already exist beneath the cgroup2 mount,
 * root-owned and not writable by anyone else; the state directory is root's alone. */
const guardian_manifest guardian_compiled_manifest = {
    .state_directory = "/var/lib/je_auto_control/owner",
    .administrator = 0,
    .cgroup_mount = "/sys/fs/cgroup",
    .subtree = "je_auto_control.owner",
    .hierarchy_owner = 0,
    .service_uid = SERVICE_UID,
    .service_gid = SERVICE_GID,
    .service_executable = "/usr/libexec/je_auto_control/owner_service",
    .listener_path = "/run/je_auto_control/owner.sock",
    .listener_gid = SOCKET_GID,
    .installation = {0}, /* EDIT: 16 random bytes, fixed for this installation's lifetime. */
    .manifest_version = 1,
    .clients = clients,
    .client_count = sizeof(clients) / sizeof(clients[0]),
    .service = &service_manifest,
    /* EDIT: any other world-writable directory helpers could write, e.g. "/var/crash". */
    .purge_roots = NULL, .purge_root_count = 0,
    /* EDIT: caps on every running epoch together (up to four run at once); 0 leaves them to
     * the subtree's parent, e.g. a systemd slice with TasksMax and MemoryMax. */
    .subtree_pids_max = 0, .subtree_memory_max = 0,
};
