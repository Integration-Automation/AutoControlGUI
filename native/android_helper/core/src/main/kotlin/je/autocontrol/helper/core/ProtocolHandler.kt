package je.autocontrol.helper.core

/** Commands the injector knows how to perform; anything else is refused at `begin`. */
private val COMMANDS = setOf("tap", "swipe", "key")
private const val MAX_COORDINATE = 100_000
private const val MAX_DURATION_MS = 10_000
private const val MAX_KEYCODE = 400

/**
 * Protocol version 1 over decoded JSON objects: one request map in, one reply map out.
 *
 * The app decodes each line with `org.json` and encodes the reply the same way; everything that
 * decides anything lives here so it is tested on the JVM. A malformed request gets an `error`
 * reply and never reaches the ledger.
 */
class ProtocolHandler(private val ledger: FenceLedger, private val bootId: String, private val helperEpoch: String) {

    /** Answer one request; never throws for bad input, only for a broken ledger invariant. */
    fun handle(request: Map<String, Any?>): Map<String, Any?> = try {
        when (request["op"]) {
            "hello" -> mapOf("protocol" to 1, "boot_id" to bootId, "helper_epoch" to helperEpoch,
                "epoch" to ledger.currentEpoch)
            "fence" -> fence(text(request, "epoch"))
            "begin" -> begin(request)
            "settle" -> settlement(ledger.settle(text(request, "id")))
            else -> error("unknown_op")
        }
    } catch (failure: IllegalArgumentException) {
        error(failure.message ?: "invalid_request")
    }

    private fun fence(epoch: String): Map<String, Any?> {
        val result = ledger.fence(epoch)
        return mapOf("epoch" to result.epoch, "fenced" to result.fenced, "inflight" to result.inflight,
            "queue_empty" to result.queueEmpty)
    }

    private fun begin(request: Map<String, Any?>): Map<String, Any?> {
        val command = request["command"] as? Map<*, *> ?: return error("command_required")
        val checked = checkCommand(command) ?: return error("invalid_command")
        val admission = ledger.begin(text(request, "id"), text(request, "epoch"), checked)
        return mapOf("id" to admission.id, "accepted" to admission.accepted, "reason" to admission.reason)
    }

    private fun settlement(value: Settlement): Map<String, Any?> = mapOf(
        "id" to value.id, "boot_id" to value.bootId, "epoch" to value.epoch,
        "status" to value.status.name.lowercase(), "input_released" to value.inputReleased,
        "queue_empty" to value.queueEmpty)

    private fun error(reason: String): Map<String, Any?> = mapOf("error" to reason)
}

private fun text(request: Map<String, Any?>, key: String): String =
    request[key] as? String ?: throw IllegalArgumentException("${key}_required")

private fun bounded(command: Map<*, *>, key: String, limit: Int): Int? {
    val value = command[key] as? Number ?: return null
    if (value.toDouble() != value.toLong().toDouble()) return null
    val whole = value.toLong()
    return if (whole in 0..limit.toLong()) whole.toInt() else null
}

/** Accept only a closed command shape with bounded integers; return the normalized command or null. */
fun checkCommand(command: Map<*, *>): Map<String, Any?>? {
    val kind = command["kind"] as? String ?: return null
    if (kind !in COMMANDS) return null
    val fields = when (kind) {
        "tap" -> listOf("x", "y")
        "swipe" -> listOf("x", "y", "to_x", "to_y", "duration_ms")
        else -> listOf("keycode")
    }
    if (command.keys != (fields + "kind").toSet()) return null
    val normalized = mutableMapOf<String, Any?>("kind" to kind)
    for (field in fields) {
        val limit = when (field) {
            "duration_ms" -> MAX_DURATION_MS
            "keycode" -> MAX_KEYCODE
            else -> MAX_COORDINATE
        }
        normalized[field] = bounded(command, field, limit) ?: return null
    }
    return normalized
}
