package je.autocontrol.helper.core

/** Lifecycle of one begun command; only [COMPLETED] with released input certifies an effect. */
enum class CommandStatus { QUEUED, INJECTING, COMPLETED, REJECTED, FENCED, FAILED }

/** The answer to `begin`: refused commands are never queued. */
data class Admission(val id: String, val accepted: Boolean, val reason: String = "")

/** The answer to `fence`. */
data class FenceResult(val epoch: String, val fenced: List<String>, val inflight: String?, val queueEmpty: Boolean)

/** The answer to `settle`: the device's own account of one command. */
data class Settlement(
    val id: String,
    val bootId: String,
    val epoch: String,
    val status: CommandStatus,
    val inputReleased: Boolean,
    val queueEmpty: Boolean,
)

private val TOKEN = Regex("[0-9a-f]{32}")

private fun requireToken(value: String, name: String): String {
    require(TOKEN.matches(value)) { "$name must be 32 lowercase hexadecimal characters" }
    return value
}

private class Record(val epoch: String, val command: Map<String, Any?>) {
    var status = CommandStatus.QUEUED
    var released = true
}

/**
 * Every helper request goes through this ledger, so the fence holds however requests interleave.
 *
 * A command runs only under the epoch it was begun with; [fence] moves the epoch forward for good,
 * fences queued older commands and tells an injecting one to stop. The injector asks [stillCurrent]
 * between events and reports through [finish]; [settle] answers from this record alone.
 */
class FenceLedger(private val bootId: String, initialEpoch: String, private val capacity: Int = 64) {
    private val lock = Any()
    private var epoch = requireToken(initialEpoch, "epoch")
    private val records = LinkedHashMap<String, Record>()
    private val queue = ArrayDeque<String>()
    private var injecting: String? = null

    init {
        require(bootId.isNotBlank()) { "boot id is required" }
        require(capacity in 1..4096) { "capacity must be between 1 and 4096" }
    }

    /** The epoch commands currently run under. */
    val currentEpoch: String get() = synchronized(lock) { epoch }

    /** Queue a command under [commandEpoch]; refuse a stale epoch, a reused id or a full queue. */
    fun begin(id: String, commandEpoch: String, command: Map<String, Any?>): Admission = synchronized(lock) {
        requireToken(id, "request id")
        requireToken(commandEpoch, "epoch")
        when {
            commandEpoch != epoch -> Admission(id, false, "stale_epoch")
            records.containsKey(id) -> Admission(id, false, "duplicate_id")
            queue.size >= capacity -> Admission(id, false, "queue_full")
            records.size >= capacity * 64 -> Admission(id, false, "ledger_full")
            else -> {
                records[id] = Record(commandEpoch, command.toMap())
                queue.addLast(id)
                Admission(id, true)
            }
        }
    }

    /** Move to [newEpoch] for good: fence queued older commands and flag the injecting one to stop. */
    fun fence(newEpoch: String): FenceResult = synchronized(lock) {
        requireToken(newEpoch, "epoch")
        require(newEpoch != epoch) { "a fence must move to a new epoch" }
        epoch = newEpoch
        val fenced = queue.filter { records.getValue(it).epoch != newEpoch }
        fenced.forEach { records.getValue(it).status = CommandStatus.FENCED }
        queue.removeAll(fenced.toSet())
        FenceResult(newEpoch, fenced, injecting, queue.isEmpty())
    }

    /** Hand the injector the next command, only if it was begun under the current epoch. */
    fun claimNext(): Pair<String, Map<String, Any?>>? = synchronized(lock) {
        if (injecting != null) return null
        while (queue.isNotEmpty()) {
            val id = queue.removeFirst()
            val record = records.getValue(id)
            if (record.epoch != epoch) {
                record.status = CommandStatus.FENCED
                continue
            }
            record.status = CommandStatus.INJECTING
            record.released = false
            injecting = id
            return id to record.command
        }
        null
    }

    /** Asked by the injector between events: false once a fence has moved past this command. */
    fun stillCurrent(id: String): Boolean = synchronized(lock) {
        injecting == id && records[id]?.epoch == epoch
    }

    /** Report how an injection ended; a command a fence overtook can never become completed. */
    fun finish(id: String, succeeded: Boolean, inputReleased: Boolean) {
        synchronized(lock) {
            val record = records[id] ?: throw IllegalArgumentException("unknown request id")
            check(injecting == id) { "only the injecting command can finish" }
            injecting = null
            record.released = inputReleased
            record.status = when {
                record.epoch != epoch -> CommandStatus.FENCED
                succeeded -> CommandStatus.COMPLETED
                else -> CommandStatus.FAILED
            }
        }
    }

    /** The device's account of one command; an unknown id is reported as rejected. */
    fun settle(id: String): Settlement = synchronized(lock) {
        requireToken(id, "request id")
        val record = records[id]
        val queueEmpty = queue.isEmpty() && injecting == null
        if (record == null) {
            return Settlement(id, bootId, epoch, CommandStatus.REJECTED, true, queueEmpty)
        }
        Settlement(id, bootId, record.epoch, record.status, record.released, queueEmpty)
    }
}
