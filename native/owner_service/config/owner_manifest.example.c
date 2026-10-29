#define _GNU_SOURCE
/* Owner service manifest template. Copy to owner_manifest.c, replace every value
 * marked EDIT, review it, and build with build.sh. The service and the guardian are
 * compiled against this file: nothing in it can be changed by an argument, an
 * environment value or a request at run time. Keep the compiled copy root-owned. */
#include "guardian.h"

/* EDIT: accounts. Guardian is root. The service account runs the service, and the
 * payload account runs helpers. One client account may open top-level leases. Every
 * account and primary group must be distinct. The socket group owns the listener: the
 * client account is a supplementary member of it, and the service gives it only to
 * helpers whose policy may start nested children. The payload is never a member. */
#define SERVICE_UID 990u
#define SERVICE_GID 990u
#define PAYLOAD_UID 991u
#define PAYLOAD_GID 991u
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
     * long-lived helper delays the rollover: keep both at the maximum, 32. */
    .client_lease_quota = 32,
    .record_capacity = 32,
    /* EDIT: per helper, including its nested children. The Python worker with OpenCV and
     * OCR loaded needs about 1 GiB; a fork bomb or leak stops here instead of the host. */
    .record_pids_max = 256,
    .record_memory_max = 2ULL << 30,
};

static const guardian_client clients[] = {
    {CLIENT_UID, CLIENT_GID, {NS_DEVICE, NS_USER, NS_PID, NS_MOUNT, NS_CGROUP}},
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
};
