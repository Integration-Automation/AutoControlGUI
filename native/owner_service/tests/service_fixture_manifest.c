/* Acceptance stand-in for the provisioned service_manifest.c. The guardian is
 * the test account (FIXTURE_UID/FIXTURE_GID, set by the runner); no client of
 * this build ever connects. Never linked into an installed service. */
#include "native_service.h"

static const char *const fixture_argv[] = {"/usr/bin/true"};
static const char *const fixture_env[] = {"LANG=C"};
static const service_launch_policy fixture_policies[] = {{
    .id = 1, .executable = "/usr/bin/true", .cwd = "/", .fixed_argv = fixture_argv, .fixed_argc = 1,
    .env = fixture_env, .envc = 1, .max_client_arguments = 1, .argument_alphabet = "abcdefghijklmnopqrstuvwxyz",
    .payload_uid = 65534, .payload_gid = 65534,
}};

const service_policy service_manifest = {
    .guardian = {FIXTURE_UID, FIXTURE_GID},
    .clients = {{FIXTURE_UID + 2, FIXTURE_GID + 2}},
    .client_count = 1,
    .policies = fixture_policies,
    .policy_count = 1,
    .lease_lifetime_ns = 30000000000ULL,
    .client_lease_quota = 8,
    .lease_max_age_ns = 300000000000ULL,
    .record_capacity = 4,
};
