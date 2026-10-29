#define _GNU_SOURCE
/* Protected acceptance manifests for the WSL distro. Every value is fixed at build
 * time by the builder (accounts, paths, the client's namespaces); none is read at run
 * time. Never linked into an installed service or guardian. */
#include "guardian.h"

/* The delegated-subtree scenario builds a second guardian with its own subtree and state. */
#ifndef PROTECTED_SUBTREE
#define PROTECTED_SUBTREE "autocontrol-test"
#endif
#ifndef PROTECTED_STATE
#define PROTECTED_STATE "/var/lib/autocontrol-test"
#endif

static const char *const payload_argv[] = {PAYLOAD_EXECUTABLE, "--owned-child", "rpc"};
static const char *const parent_argv[] = {"/usr/bin/python3", "-I", NESTED_PARENT, REPOSITORY, ENDPOINT};
/* The package's real native worker. -I ignores PYTHONPATH, so the repository is put on the
 * path explicitly; an installed package would use `-m je_auto_control...native_worker`. */
static const char *const worker_argv[] = {"/usr/bin/python3", "-I", "-B", "-c",
    "import sys; sys.path.insert(0, '" REPOSITORY "'); "
    "from je_auto_control.utils.agent_runtime.native_worker import main; main()"};
/* 1: a top-level rpc helper. 2: the same helper, nested only. 3: a top-level parent that
 * may start policy 2 children through its own child leases. */
static const service_launch_policy protected_policies[] = {{
    .id = 1, .executable = PAYLOAD_EXECUTABLE, .cwd = "/", .fixed_argv = payload_argv, .fixed_argc = 3,
    .env = NULL, .envc = 0, .max_client_arguments = 0, .payload_uid = PAYLOAD_UID, .payload_gid = PAYLOAD_GID,
}, {
    .id = 2, .nested = true, .executable = PAYLOAD_EXECUTABLE, .cwd = "/", .fixed_argv = payload_argv,
    .fixed_argc = 3, .payload_uid = PAYLOAD_UID, .payload_gid = PAYLOAD_GID,
}, {
    .id = 3, .executable = "/usr/bin/python3", .cwd = "/", .fixed_argv = parent_argv, .fixed_argc = 5,
    .payload_uid = PAYLOAD_UID, .payload_gid = PAYLOAD_GID, .child_policies = UINT32_C(1) << 2,
}, {
    .id = 4, .executable = "/usr/bin/python3", .cwd = "/", .fixed_argv = worker_argv, .fixed_argc = 5,
    .payload_uid = PAYLOAD_UID, .payload_gid = PAYLOAD_GID,
}};

const service_policy service_manifest = {
    .guardian = {0, 0},
    .clients = {{CLIENT_UID, CLIENT_GID}},
    .client_count = 1,
    .policies = protected_policies,
    .policy_count = 4,
    /* Short enough that every session longer than a few seconds proves renewal works. */
    .lease_lifetime_ns = 4000000000ULL,
    .lease_max_age_ns = 600000000000ULL,
    .socket_gid = SOCKET_GID,
    .client_lease_quota = 8,
    .nested_lease_quota = 4,
    .record_capacity = 8,
    .record_pids_max = 32,
    .connections_per_account = 8,
    .record_memory_max = 128ULL << 20,
};

/* The payload account is forwarded too: a nested parent connects as itself (the service
 * gives it the socket group), and the service admits it only for OPEN_CHILD inside its
 * own payload. */
static const guardian_client protected_clients[] = {
    {CLIENT_UID, CLIENT_GID, {NS_DEVICE, NS_USER, NS_PID, NS_MOUNT, NS_CGROUP}, 1},
    {PAYLOAD_UID, PAYLOAD_GID, {NS_DEVICE, NS_USER, NS_PID, NS_MOUNT, NS_CGROUP}, SERVICE_PAYLOAD_IDS},
};

const guardian_manifest guardian_compiled_manifest = {
    .state_directory = PROTECTED_STATE,
    .administrator = 0,
    .cgroup_mount = "/sys/fs/cgroup",
    .subtree = PROTECTED_SUBTREE,
    .hierarchy_owner = 0,
    .service_uid = SERVICE_UID,
    .service_gid = SERVICE_GID,
    .service_executable = "/opt/autocontrol-test/service_main",
    .listener_path = "/run/autocontrol-test/owner.sock",
    .listener_gid = SOCKET_GID,
    .installation = {0x41, 0x43, 0x15, 0x00, 0x77, 0x53, 0x4c, 0x01},
    .manifest_version = 1,
    .clients = protected_clients,
    .client_count = 2,
    .service = &service_manifest,
};
