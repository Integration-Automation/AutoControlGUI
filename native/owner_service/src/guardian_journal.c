#define _GNU_SOURCE
#include "guardian_journal.h"
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

static const char *const slot_names[2] = {"journal.a", "journal.b"};
typedef enum { SLOT_ABSENT, SLOT_INVALID, SLOT_VALID } slot_state;

uint32_t gj_crc32(const void *data, size_t size) {
    const uint8_t *bytes = data;
    uint32_t crc = 0xffffffffu;
    for (size_t i = 0; i < size; ++i) {
        crc ^= bytes[i];
        for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static uint32_t record_crc(const gj_record *record) { return gj_crc32(record, offsetof(gj_record, crc)); }

/* The names belong to the counter alone; recovery never acts on any other name. */
static void derive_names(gj_record *record) {
    memset(record->epoch, 0, sizeof(record->epoch));
    memset(record->service, 0, sizeof(record->service));
    if (!record->counter) return;
    snprintf(record->epoch, sizeof(record->epoch), "epoch-%016llx", (unsigned long long)record->counter);
    snprintf(record->service, sizeof(record->service), "service-%016llx", (unsigned long long)record->counter);
}

static bool record_valid(const gj_record *record) {
    if (record->magic != GJ_MAGIC || record->version != GJ_VERSION || record->crc != record_crc(record) ||
        record->phase < GJ_CLEAN || record->phase > GJ_RECOVERING || (!record->counter && record->phase != GJ_CLEAN))
        return false;
    gj_record expected = *record;
    derive_names(&expected);
    return !memcmp(expected.epoch, record->epoch, sizeof(record->epoch)) &&
        !memcmp(expected.service, record->service, sizeof(record->service));
}

static bool trusted(const struct stat *status, uid_t administrator, bool directory) {
    return (directory ? S_ISDIR(status->st_mode) : S_ISREG(status->st_mode)) &&
        status->st_uid == administrator && !(status->st_mode & (S_IWGRP | S_IWOTH));
}

static slot_state read_slot(const gj_journal *journal, int slot, gj_record *record, gj_error *error) {
    int number = openat(journal->directory, slot_names[slot], O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (number < 0) {
        if (errno == ENOENT) return SLOT_ABSENT;
        *error = errno == ELOOP ? GJ_ERROR_DIRECTORY : GJ_ERROR_IO;
        return SLOT_INVALID;
    }
    struct stat status;
    ssize_t count = -1;
    if (fstat(number, &status) == 0 && trusted(&status, journal->administrator, false))
        count = pread(number, record, sizeof(*record), 0);
    else *error = GJ_ERROR_PERMISSIONS;
    close(number);
    return count == (ssize_t)sizeof(*record) && record_valid(record) ? SLOT_VALID : SLOT_INVALID;
}

/* Two valid slots: the newer sequence wins, it may not lower the counter, and equal
 * sequences must agree byte for byte. */
static gj_error choose(gj_journal *journal, const gj_record records[2], const slot_state states[2]) {
    if (states[0] == SLOT_VALID && states[1] == SLOT_VALID) {
        if (memcmp(records[0].installation, records[1].installation, GJ_INSTALLATION_BYTES))
            return GJ_ERROR_INSTALLATION;
        if (records[0].sequence == records[1].sequence) {
            if (memcmp(&records[0], &records[1], sizeof(records[0]))) return GJ_ERROR_AMBIGUOUS;
            journal->slot = 0;
        } else {
            int newer = records[1].sequence > records[0].sequence;
            if (records[newer].counter < records[!newer].counter) return GJ_ERROR_CORRUPT;
            journal->slot = newer;
        }
    } else if (states[0] == SLOT_VALID || states[1] == SLOT_VALID) {
        journal->slot = states[1] == SLOT_VALID;
    } else {
        /* No valid slot: a fresh installation only when nothing exists at all. */
        return states[0] == SLOT_ABSENT && states[1] == SLOT_ABSENT ? GJ_ERROR_NONE : GJ_ERROR_CORRUPT;
    }
    journal->current = records[journal->slot];
    journal->loaded = true;
    return GJ_ERROR_NONE;
}

/* Walks from "/" one component at a time without following links and returns the last
 * descriptor. Every directory on the way is root's or `owner`'s, and one that others may
 * write is sticky, so no other account can rename or replace anything below it. */
int gj_open_trusted_directory(const char *path, uid_t owner) {
    char copy[4096];
    if (!path || path[0] != '/' || strlen(path) >= sizeof(copy)) { errno = EINVAL; return -1; }
    strcpy(copy, path);
    int current = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    char *cursor = copy + 1;
    for (;;) {
        struct stat status;
        if (current < 0) return -1;
        if (fstat(current, &status) != 0 || !S_ISDIR(status.st_mode) ||
            (status.st_uid != 0 && status.st_uid != owner) ||
            ((status.st_mode & (S_IWGRP | S_IWOTH)) && !(status.st_mode & S_ISVTX))) {
            close(current);
            errno = EPERM;
            return -1;
        }
        while (*cursor == '/') ++cursor;
        if (!*cursor) return current;
        char *end = strchr(cursor, '/');
        if (end) *end = 0;
        if (!strcmp(cursor, "..")) { close(current); errno = EINVAL; return -1; }
        int next = openat(current, cursor, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        int saved = errno;
        close(current);
        errno = saved;
        current = next;
        cursor = end ? end + 1 : cursor + strlen(cursor);
    }
}

gj_error gj_open(gj_journal *journal, const char *path, uid_t administrator,
                 const uint8_t installation[GJ_INSTALLATION_BYTES]) {
    *journal = (gj_journal){.directory = -1, .lock = -1, .administrator = administrator, .slot = -1};
    struct stat status;
    journal->directory = gj_open_trusted_directory(path, administrator);
    if (journal->directory < 0) return errno == EPERM ? GJ_ERROR_PERMISSIONS : GJ_ERROR_DIRECTORY;
    gj_error error = GJ_ERROR_NONE;
    if (fstat(journal->directory, &status) != 0 || !trusted(&status, administrator, true))
        error = GJ_ERROR_PERMISSIONS;
    if (!error) {
        journal->lock = openat(journal->directory, "lock", O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
        if (journal->lock < 0) error = GJ_ERROR_IO;
        else if (flock(journal->lock, LOCK_EX | LOCK_NB) != 0)
            error = errno == EWOULDBLOCK ? GJ_ERROR_LOCKED : GJ_ERROR_IO;
    }
    gj_record records[2];
    slot_state states[2] = {SLOT_ABSENT, SLOT_ABSENT};
    for (int slot = 0; slot < 2 && !error; ++slot) states[slot] = read_slot(journal, slot, &records[slot], &error);
    if (!error) error = choose(journal, records, states);
    if (!error && journal->loaded && memcmp(journal->current.installation, installation, GJ_INSTALLATION_BYTES))
        error = GJ_ERROR_INSTALLATION;
    if (error) gj_close(journal);
    return error;
}

/* Into the slot not holding the current record: write, fsync the file, fsync the
 * directory. Only then does the record become current in memory. */
static gj_error commit(gj_journal *journal, gj_record *next) {
    next->magic = GJ_MAGIC;
    next->version = GJ_VERSION;
    next->sequence = journal->loaded ? journal->current.sequence + 1 : 1;
    next->reserved = 0;
    next->crc = record_crc(next);
    int slot = journal->slot < 0 ? 0 : !journal->slot;
    int number = openat(journal->directory, slot_names[slot], O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC,
                        0600);
    if (number < 0) return errno == ELOOP ? GJ_ERROR_DIRECTORY : GJ_ERROR_IO;
    bool durable = pwrite(number, next, sizeof(*next), 0) == (ssize_t)sizeof(*next) && fsync(number) == 0;
    durable &= close(number) == 0;
    if (!durable || fsync(journal->directory) != 0) return GJ_ERROR_IO;
    journal->current = *next;
    journal->slot = slot;
    journal->loaded = true;
    return GJ_ERROR_NONE;
}

gj_error gj_initialize(gj_journal *journal, const uint8_t installation[GJ_INSTALLATION_BYTES],
                       uint32_t manifest_version) {
    if (journal->directory < 0) return GJ_ERROR_DIRECTORY;
    if (journal->loaded) return GJ_ERROR_PHASE;
    gj_record first;
    memset(&first, 0, sizeof(first));
    memcpy(first.installation, installation, GJ_INSTALLATION_BYTES);
    first.manifest_version = manifest_version;
    first.phase = GJ_CLEAN;
    return commit(journal, &first);
}

gj_error gj_plan(gj_journal *journal) {
    if (journal->directory < 0 || !journal->loaded) return GJ_ERROR_DIRECTORY;
    if (journal->current.phase != GJ_CLEAN) return GJ_ERROR_PHASE;
    if (journal->current.counter == UINT64_MAX) return GJ_ERROR_OVERFLOW;
    gj_record next = journal->current;
    next.counter += 1;
    next.phase = GJ_PLANNED;
    derive_names(&next);
    return commit(journal, &next);
}

static bool allowed(gj_phase from, gj_phase to) {
    return (from == GJ_PLANNED && (to == GJ_ACTIVE || to == GJ_RECOVERING)) ||
        (from == GJ_ACTIVE && to == GJ_RECOVERING) || (from == GJ_RECOVERING && to == GJ_CLEAN);
}

gj_error gj_mark(gj_journal *journal, gj_phase next_phase) {
    if (journal->directory < 0 || !journal->loaded) return GJ_ERROR_DIRECTORY;
    if (!allowed((gj_phase)journal->current.phase, next_phase)) return GJ_ERROR_PHASE;
    gj_record next = journal->current;
    next.phase = next_phase;
    return commit(journal, &next);
}

void gj_close(gj_journal *journal) {
    if (journal->lock >= 0) close(journal->lock);
    if (journal->directory >= 0) close(journal->directory);
    journal->lock = journal->directory = -1;
}
