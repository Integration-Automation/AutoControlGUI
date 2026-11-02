#define _GNU_SOURCE
/* Worker side of the application relay: moves bytes between a record's relay
 * buffers and its child's fd 0 and fd 1 without ever blocking. */
#include "owner_internal.h"
#include <errno.h>
#include <string.h>
#include <unistd.h>

#define RELAY_CHUNK 4096

static void relay_requests(owner_record *record, uint8_t *chunk) {
    pthread_mutex_lock(&record->relay.lock);
    size_t pending = record->relay.request_length < RELAY_CHUNK ? record->relay.request_length : RELAY_CHUNK;
    memcpy(chunk, record->relay.request, pending);
    pthread_mutex_unlock(&record->relay.lock);
    if (!pending || record->lifetime_write.state != FD_OWNED) return;
    ssize_t written = write(record->lifetime_write.number, chunk, pending);
    if (written < 0 && (errno == EAGAIN || errno == EINTR)) return;
    pthread_mutex_lock(&record->relay.lock);
    /* EPIPE: the child stopped reading, so queued requests can never be delivered. */
    size_t consumed = written > 0 ? (size_t)written : record->relay.request_length;
    memmove(record->relay.request, record->relay.request + consumed, record->relay.request_length - consumed);
    record->relay.request_length -= consumed;
    pthread_mutex_unlock(&record->relay.lock);
}

static bool relay_replies(owner_record *record, uint8_t *chunk) {
    pthread_mutex_lock(&record->relay.lock);
    size_t room = record->relay.reply_eof ? 0 : NO_RELAY_BYTES - record->relay.reply_length;
    pthread_mutex_unlock(&record->relay.lock);
    if (!room || record->reply_read.state != FD_OWNED) return false;
    ssize_t count = read(record->reply_read.number, chunk, room < RELAY_CHUNK ? room : RELAY_CHUNK);
    if (count < 0 && (errno == EAGAIN || errno == EINTR)) return false;
    pthread_mutex_lock(&record->relay.lock);
    if (count > 0) {
        memcpy(record->relay.reply + record->relay.reply_length, chunk, (size_t)count);
        record->relay.reply_length += (size_t)count;
    } else {
        record->relay.reply_eof = true;
    }
    pthread_mutex_unlock(&record->relay.lock);
    return count > 0;
}

/* Worker thread only, never blocking. Writing to a pipe whose reader died raises
 * SIGPIPE, so the owning process ignores it (service_main does). */
void owner_relay_pump(owner_record *record) {
    if (!record->relay_enabled) return;
    uint8_t chunk[RELAY_CHUNK];
    relay_requests(record, chunk);
    for (unsigned turn = 0; turn < NO_RELAY_BYTES / RELAY_CHUNK && relay_replies(record, chunk); ++turn) continue;
}

/* After the child is gone: collect what it wrote, then end delivery. Bounded,
 * because a descendant that inherited fd 1 can keep the pipe open. */
void owner_relay_drain(owner_record *record) {
    for (unsigned turn = 0; turn < 64 && record->relay_enabled; ++turn) {
        owner_relay_pump(record);
        pthread_mutex_lock(&record->relay.lock);
        bool done = record->relay.reply_eof || record->relay.reply_length == NO_RELAY_BYTES;
        pthread_mutex_unlock(&record->relay.lock);
        if (done) break;
    }
}

void owner_relay_close(owner_record *record) {
    pthread_mutex_lock(&record->relay.lock);
    record->relay.closed = true;
    record->relay.request_length = 0;
    pthread_mutex_unlock(&record->relay.lock);
}
