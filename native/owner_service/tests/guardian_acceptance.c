#define _GNU_SOURCE
/* Guardian acceptance without root: every refusal before a namespace exists, and the
 * create-fails path that must recover to CLEAN. The subtree is the cgroup2 root this
 * session sits in (root-owned, not writable), so no cgroup is ever created. */
#include "guardian.h"
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(expression) do { if (!(expression)) { \
    fprintf(stderr, "failed line %d: %s\n", __LINE__, #expression); abort(); } ++checks; } while (0)

static char root[64];
static guardian_manifest manifest;

static size_t entries(void) {
    DIR *directory = opendir(root);
    size_t count = 0;
    for (struct dirent *entry = readdir(directory); entry; entry = readdir(directory))
        if (entry->d_name[0] != '.') ++count;
    closedir(directory);
    return count;
}

static void reset(void) {
    char path[128];
    const char *names[] = {"journal.a", "journal.b", "lock"};
    for (size_t i = 0; i < 3; ++i) { snprintf(path, sizeof(path), "%s/%s", root, names[i]); unlink(path); }
    CHECK(chmod(root, 0700) == 0);
}

static gj_record journal_now(void) {
    gj_journal journal;
    CHECK(gj_open(&journal, root, getuid(), manifest.installation) == GJ_ERROR_NONE && journal.loaded);
    gj_record record = journal.current;
    gj_close(&journal);
    return record;
}

static guardian_result prepare(guardian_state *state) {
    guardian_result result = guardian_prepare(state, &manifest);
    guardian_close(state);
    return result;
}

static void case_state_directory(void) {
    guardian_state state;
    reset();
    manifest.administrator = getuid() + 1;
    CHECK(prepare(&state) == GUARDIAN_REFUSED && state.operation == 1 && state.system_errno == GJ_ERROR_PERMISSIONS);
    manifest.administrator = getuid();
    CHECK(entries() == 0); /* Refused before the lock file or any slot was written. */
    CHECK(chmod(root, 0770) == 0);
    CHECK(prepare(&state) == GUARDIAN_REFUSED && state.system_errno == GJ_ERROR_PERMISSIONS && entries() == 0);
    CHECK(chmod(root, 0700) == 0);
    const char *real = manifest.state_directory;
    manifest.state_directory = "/tmp/guardian-acceptance-absent";
    CHECK(prepare(&state) == GUARDIAN_REFUSED && state.system_errno == GJ_ERROR_DIRECTORY);
    manifest.state_directory = real;
    gj_journal held;
    CHECK(gj_open(&held, root, getuid(), manifest.installation) == GJ_ERROR_NONE);
    CHECK(prepare(&state) == GUARDIAN_REFUSED && state.system_errno == GJ_ERROR_LOCKED);
    gj_close(&held);
}

static void case_hierarchy(void) {
    guardian_state state;
    reset();
    manifest.cgroup_mount = "/tmp";
    CHECK(prepare(&state) == GUARDIAN_REFUSED && state.operation == 11);
    manifest.cgroup_mount = "/sys/fs/cgroup";
    manifest.subtree = "../../etc";
    CHECK(prepare(&state) == GUARDIAN_REFUSED && state.operation == 12 && state.system_errno == EXDEV);
    manifest.subtree = ".";
    manifest.hierarchy_owner = getuid();
    CHECK(prepare(&state) == GUARDIAN_REFUSED && state.operation == 13);
    manifest.hierarchy_owner = 0;
    gj_record record = journal_now();
    CHECK(record.phase == GJ_CLEAN && record.counter == 0); /* Nothing was planned. */
}

/* Planned, then creation fails: the counter is consumed and the journal is CLEAN. */
static void case_create_fails(void) {
    guardian_state state;
    reset();
    CHECK(prepare(&state) == GUARDIAN_REFUSED && state.operation == 4 && state.system_errno == EACCES);
    gj_record record = journal_now();
    CHECK(record.phase == GJ_CLEAN && record.counter == 1);
    char path[128];
    snprintf(path, sizeof(path), "/sys/fs/cgroup/%s", record.epoch);
    CHECK(access(path, F_OK) != 0 && errno == ENOENT);
}

/* A crash left the journal PLANNED or ACTIVE; its branches never existed. */
static void case_crash_recovery(void) {
    gj_phase crashed[] = {GJ_PLANNED, GJ_ACTIVE, GJ_RECOVERING};
    for (size_t i = 0; i < sizeof(crashed) / sizeof(crashed[0]); ++i) {
        gj_journal journal;
        CHECK(gj_open(&journal, root, getuid(), manifest.installation) == GJ_ERROR_NONE);
        uint64_t before = journal.current.counter;
        CHECK(gj_plan(&journal) == GJ_ERROR_NONE);
        if (crashed[i] != GJ_PLANNED) CHECK(gj_mark(&journal, crashed[i] == GJ_ACTIVE ? GJ_ACTIVE : GJ_RECOVERING) ==
                                            GJ_ERROR_NONE);
        if (crashed[i] == GJ_RECOVERING) CHECK(journal.current.phase == GJ_RECOVERING);
        gj_close(&journal);
        guardian_state state;
        CHECK(prepare(&state) == GUARDIAN_REFUSED && state.operation == 4);
        gj_record record = journal_now();
        CHECK(record.phase == GJ_CLEAN && record.counter == before + 2);
    }
}

int main(void) {
    snprintf(root, sizeof(root), "/tmp/guardian-acceptance-XXXXXX");
    CHECK(mkdtemp(root) != NULL);
    manifest = (guardian_manifest){.state_directory = root, .administrator = getuid(), .cgroup_mount = "/sys/fs/cgroup",
        .subtree = ".", .hierarchy_owner = 0, .service_uid = 65534, .service_gid = 65534,
        .service_executable = "/usr/bin/true", .listener_path = "/tmp/guardian-acceptance.sock",
        .installation = {4, 4, 4, 4}, .manifest_version = 1};
    CHECK(getuid() != 0); /* The create-fails path relies on an unprivileged account. */
    case_state_directory();
    case_hierarchy();
    case_create_fails();
    case_crash_recovery();
    reset();
    CHECK(rmdir(root) == 0);
    printf("{\"checks\": %u, \"evidence\": \"guardian refusals and nothing-created recovery, unprivileged\"}\n",
           checks);
    return 0;
}
