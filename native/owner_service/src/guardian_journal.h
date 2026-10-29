#ifndef AUTOCONTROL_GUARDIAN_JOURNAL_H
#define AUTOCONTROL_GUARDIAN_JOURNAL_H
/* Durable guardian state: installation identity, monotone epoch counter, the exact
 * namespace names an epoch owns, and the recovery phase. Private to the guardian. */
#include <stdbool.h>
#include <stdint.h>
#include <sys/types.h>

#define GJ_MAGIC 0x414a4e4cu
#define GJ_VERSION 1
#define GJ_INSTALLATION_BYTES 16
#define GJ_COMPONENT_BYTES 32

/* CLEAN: no epoch owns anything. PLANNED: counter and names are durable, creation may
 * be partial. ACTIVE: a service bootstrapped. RECOVERING: the old epoch is reclaimed. */
typedef enum { GJ_CLEAN = 1, GJ_PLANNED, GJ_ACTIVE, GJ_RECOVERING } gj_phase;

typedef struct {
    uint32_t magic, version;
    uint64_t sequence;
    uint8_t installation[GJ_INSTALLATION_BYTES];
    uint64_t counter;
    char epoch[GJ_COMPONENT_BYTES], service[GJ_COMPONENT_BYTES];
    uint32_t manifest_version, phase;
    uint32_t crc; /* CRC-32 of every byte before this field. */
    uint32_t reserved;
} gj_record;

typedef enum {
    GJ_ERROR_NONE, GJ_ERROR_DIRECTORY, GJ_ERROR_PERMISSIONS, GJ_ERROR_LOCKED, GJ_ERROR_IO, GJ_ERROR_CORRUPT,
    GJ_ERROR_AMBIGUOUS, GJ_ERROR_INSTALLATION, GJ_ERROR_PHASE, GJ_ERROR_OVERFLOW
} gj_error;

typedef struct {
    int directory, lock;  /* Owned descriptors; -1 when closed. */
    uid_t administrator;
    bool loaded;          /* A current record exists; false only for a fresh installation. */
    int slot;             /* Slot holding the current record, -1 when none. */
    gj_record current;
} gj_journal;

/* Opens the state directory without following links, checks its owner and mode, takes
 * the exclusive lock without waiting, and loads the current record. `installation`
 * comes from the provisioned manifest; a journal of another installation refuses. */
/* Opens an absolute directory whose every ancestor is root's or `owner`'s and not writable
 * by others unless sticky. EPERM names an untrusted directory on the way. */
int gj_open_trusted_directory(const char *path, uid_t owner);
gj_error gj_open(gj_journal *journal, const char *path, uid_t administrator,
                 const uint8_t installation[GJ_INSTALLATION_BYTES]);
/* Fresh installation only: the first durable record, CLEAN with counter 0. */
gj_error gj_initialize(gj_journal *journal, const uint8_t installation[GJ_INSTALLATION_BYTES],
                       uint32_t manifest_version);
/* CLEAN -> PLANNED: the next counter and its names are durable before anything exists. */
gj_error gj_plan(gj_journal *journal);
/* PLANNED -> ACTIVE, PLANNED or ACTIVE -> RECOVERING, RECOVERING -> CLEAN. */
gj_error gj_mark(gj_journal *journal, gj_phase next);
void gj_close(gj_journal *journal);
uint32_t gj_crc32(const void *data, size_t size);
#endif
