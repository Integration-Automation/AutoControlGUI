#define _GNU_SOURCE
/* Journal acceptance in a temporary directory owned by the test account, which stands
 * in for root. Nothing here creates a cgroup or starts a process. */
#include "guardian_journal.h"
#include <fcntl.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(expression) do { if (!(expression)) { \
    fprintf(stderr, "failed line %d: %s\n", __LINE__, #expression); abort(); } ++checks; } while (0)

static char root[64];
static const uint8_t install[GJ_INSTALLATION_BYTES] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16};
static const uint8_t stranger[GJ_INSTALLATION_BYTES] = {9};

static void path_of(char *out, size_t size, const char *name) { snprintf(out, size, "%s/%s", root, name); }

static void reset(void) {
    char path[128];
    const char *names[] = {"journal.a", "journal.b", "lock"};
    for (size_t i = 0; i < 3; ++i) { path_of(path, sizeof(path), names[i]); unlink(path); }
    CHECK(chmod(root, 0700) == 0);
}

static gj_error reopen(gj_journal *journal) { return gj_open(journal, root, getuid(), install); }

static bool read_record(const char *name, gj_record *record) {
    char path[128];
    path_of(path, sizeof(path), name);
    FILE *file = fopen(path, "rb");
    bool ok = file && fread(record, sizeof(*record), 1, file) == 1;
    if (file) fclose(file);
    return ok;
}

static void write_record(const char *name, gj_record record, bool fix_crc) {
    char path[128];
    path_of(path, sizeof(path), name);
    if (fix_crc) record.crc = gj_crc32(&record, offsetof(gj_record, crc));
    FILE *file = fopen(path, "wb");
    CHECK(file && fwrite(&record, sizeof(record), 1, file) == 1);
    fclose(file);
    CHECK(chmod(path, 0600) == 0);
}

static void case_lifecycle(void) {
    reset();
    gj_journal journal;
    CHECK(reopen(&journal) == GJ_ERROR_NONE && !journal.loaded);
    CHECK(gj_plan(&journal) == GJ_ERROR_DIRECTORY);
    CHECK(gj_initialize(&journal, install, 7) == GJ_ERROR_NONE && journal.current.phase == GJ_CLEAN);
    CHECK(gj_initialize(&journal, install, 7) == GJ_ERROR_PHASE);
    CHECK(gj_mark(&journal, GJ_ACTIVE) == GJ_ERROR_PHASE);
    CHECK(gj_plan(&journal) == GJ_ERROR_NONE && journal.current.counter == 1);
    CHECK(!strcmp(journal.current.epoch, "epoch-0000000000000001"));
    CHECK(!strcmp(journal.current.service, "service-0000000000000001"));
    CHECK(gj_plan(&journal) == GJ_ERROR_PHASE);
    CHECK(gj_mark(&journal, GJ_CLEAN) == GJ_ERROR_PHASE);
    CHECK(gj_mark(&journal, GJ_ACTIVE) == GJ_ERROR_NONE);
    CHECK(gj_mark(&journal, GJ_ACTIVE) == GJ_ERROR_PHASE);
    CHECK(gj_mark(&journal, GJ_RECOVERING) == GJ_ERROR_NONE);
    CHECK(gj_mark(&journal, GJ_CLEAN) == GJ_ERROR_NONE);
    CHECK(gj_plan(&journal) == GJ_ERROR_NONE && journal.current.counter == 2);
    CHECK(gj_mark(&journal, GJ_RECOVERING) == GJ_ERROR_NONE); /* Bootstrap failed before ACTIVE. */
    uint64_t sequence = journal.current.sequence;
    gj_close(&journal);
    CHECK(reopen(&journal) == GJ_ERROR_NONE && journal.loaded && journal.current.counter == 2);
    CHECK(journal.current.phase == GJ_RECOVERING && journal.current.sequence == sequence);
    CHECK(journal.current.manifest_version == 7);
    gj_close(&journal);
}

static void case_lock_and_permissions(void) {
    reset();
    gj_journal first, second;
    CHECK(reopen(&first) == GJ_ERROR_NONE);
    CHECK(reopen(&second) == GJ_ERROR_LOCKED);
    CHECK(gj_initialize(&first, install, 1) == GJ_ERROR_NONE);
    gj_close(&first);
    CHECK(gj_open(&second, root, getuid() + 1, install) == GJ_ERROR_PERMISSIONS);
    CHECK(chmod(root, 0770) == 0);
    CHECK(reopen(&second) == GJ_ERROR_PERMISSIONS);
    CHECK(chmod(root, 0700) == 0);
    char path[128];
    path_of(path, sizeof(path), "journal.a");
    CHECK(chmod(path, 0620) == 0);
    CHECK(reopen(&second) == GJ_ERROR_PERMISSIONS);
    CHECK(chmod(path, 0600) == 0);
    CHECK(gj_open(&second, root, getuid(), stranger) == GJ_ERROR_INSTALLATION);
    /* A symlinked slot is never followed. */
    char target[128];
    path_of(target, sizeof(target), "journal.target");
    CHECK(rename(path, target) == 0 && symlink(target, path) == 0);
    CHECK(reopen(&second) == GJ_ERROR_DIRECTORY);
    CHECK(unlink(path) == 0 && rename(target, path) == 0);
    CHECK(reopen(&second) == GJ_ERROR_NONE);
    gj_close(&second);
}

/* An ancestor others may write is trusted only when sticky; a symlinked ancestor or a
 * relative path is never opened. */
static void case_ancestors(void) {
    char open_dir[128], state[160], link_dir[128], linked[160], lock[192];
    path_of(open_dir, sizeof(open_dir), "open");
    snprintf(state, sizeof(state), "%s/state", open_dir);
    path_of(link_dir, sizeof(link_dir), "link");
    snprintf(linked, sizeof(linked), "%s/state", link_dir);
    snprintf(lock, sizeof(lock), "%s/lock", state);
    CHECK(mkdir(open_dir, 0700) == 0 && chmod(open_dir, 0777) == 0);
    CHECK(mkdir(state, 0700) == 0);
    gj_journal journal;
    CHECK(gj_open(&journal, state, getuid(), install) == GJ_ERROR_PERMISSIONS);
    CHECK(chmod(open_dir, 01777) == 0);
    CHECK(gj_open(&journal, state, getuid(), install) == GJ_ERROR_NONE);
    gj_close(&journal);
    CHECK(symlink(open_dir, link_dir) == 0);
    CHECK(gj_open(&journal, linked, getuid(), install) == GJ_ERROR_DIRECTORY);
    CHECK(gj_open(&journal, "tmp/relative", getuid(), install) == GJ_ERROR_DIRECTORY);
    CHECK(unlink(link_dir) == 0 && unlink(lock) == 0 && rmdir(state) == 0 && rmdir(open_dir) == 0);
}

/* Leaves an older CLEAN record (counter 1) and a newer PLANNED record (counter 2); the
 * slots alternate, so which file holds which is recorded here. */
static const char *older_name, *newer_name;

static void two_slots(void) {
    reset();
    gj_journal journal;
    CHECK(reopen(&journal) == GJ_ERROR_NONE && gj_initialize(&journal, install, 1) == GJ_ERROR_NONE);
    CHECK(gj_plan(&journal) == GJ_ERROR_NONE && gj_mark(&journal, GJ_RECOVERING) == GJ_ERROR_NONE);
    CHECK(gj_mark(&journal, GJ_CLEAN) == GJ_ERROR_NONE && gj_plan(&journal) == GJ_ERROR_NONE);
    CHECK(journal.current.sequence == 5 && journal.current.counter == 2);
    newer_name = journal.slot ? "journal.b" : "journal.a";
    older_name = journal.slot ? "journal.a" : "journal.b";
    gj_close(&journal);
}

static void case_torn_and_corrupt(void) {
    gj_journal journal;
    gj_record older, newer;
    two_slots();
    char path[128];
    path_of(path, sizeof(path), newer_name);
    CHECK(truncate(path, sizeof(gj_record) / 2) == 0); /* Torn newer write. */
    CHECK(reopen(&journal) == GJ_ERROR_NONE && journal.current.phase == GJ_CLEAN);
    CHECK(journal.current.counter == 1 && journal.current.sequence == 4);
    /* The torn plan created nothing, so planning again reuses counter 2. */
    CHECK(gj_plan(&journal) == GJ_ERROR_NONE && journal.current.counter == 2 && journal.current.sequence == 5);
    gj_close(&journal);

    two_slots();
    CHECK(read_record(newer_name, &newer));
    newer.manifest_version ^= 0x100; /* Bit flip in a field only the CRC covers. */
    write_record(newer_name, newer, false);
    CHECK(reopen(&journal) == GJ_ERROR_NONE && journal.current.sequence == 4);
    gj_close(&journal);

    two_slots();
    CHECK(read_record(older_name, &older) && read_record(newer_name, &newer));
    older.sequence = newer.sequence; /* Same sequence, different content. */
    write_record(older_name, older, true);
    CHECK(reopen(&journal) == GJ_ERROR_AMBIGUOUS);

    two_slots();
    CHECK(read_record(older_name, &older) && read_record(newer_name, &newer));
    older.counter = 9; /* An older record that already used a higher counter: rollback. */
    older.phase = GJ_CLEAN;
    snprintf(older.epoch, sizeof(older.epoch), "epoch-%016llx", 9ULL);
    snprintf(older.service, sizeof(older.service), "service-%016llx", 9ULL);
    write_record(older_name, older, true);
    CHECK(reopen(&journal) == GJ_ERROR_CORRUPT);

    two_slots();
    CHECK(read_record(older_name, &older));
    memcpy(older.installation, stranger, sizeof(older.installation));
    write_record(older_name, older, true);
    CHECK(reopen(&journal) == GJ_ERROR_INSTALLATION);

    two_slots();
    CHECK(read_record(newer_name, &newer));
    snprintf(newer.epoch, sizeof(newer.epoch), "epoch-elsewhere"); /* A name the counter does not derive. */
    write_record(newer_name, newer, true);
    CHECK(reopen(&journal) == GJ_ERROR_NONE && journal.current.sequence == 4);
    gj_close(&journal);

    reset();
    write_record("journal.a", newer, false); /* Present but invalid, nothing else: refuse. */
    CHECK(reopen(&journal) == GJ_ERROR_CORRUPT);
}

static void case_overflow(void) {
    two_slots();
    gj_record newer;
    CHECK(read_record(newer_name, &newer));
    newer.counter = UINT64_MAX;
    newer.phase = GJ_CLEAN;
    newer.sequence += 10;
    snprintf(newer.epoch, sizeof(newer.epoch), "epoch-%016llx", (unsigned long long)UINT64_MAX);
    snprintf(newer.service, sizeof(newer.service), "service-%016llx", (unsigned long long)UINT64_MAX);
    write_record(newer_name, newer, true);
    gj_journal journal;
    CHECK(reopen(&journal) == GJ_ERROR_NONE && journal.current.counter == UINT64_MAX);
    CHECK(gj_plan(&journal) == GJ_ERROR_OVERFLOW && journal.current.counter == UINT64_MAX);
    gj_close(&journal);
}

int main(void) {
    snprintf(root, sizeof(root), "/tmp/guardian-journal-XXXXXX");
    CHECK(mkdtemp(root) != NULL);
    case_lifecycle();
    case_lock_and_permissions();
    case_torn_and_corrupt();
    case_overflow();
    case_ancestors();
    reset();
    CHECK(rmdir(root) == 0);
    printf("{\"checks\": %u, \"evidence\": \"journal only, unprivileged temporary directory\"}\n", checks);
    return 0;
}
