package je.autocontrol.helper

import org.json.JSONArray
import org.json.JSONObject

/** Decode a JSON object into plain Kotlin maps, lists and scalars for the protocol handler. */
internal fun decodeObject(value: JSONObject): Map<String, Any?> =
    value.keys().asSequence().associateWith { decodeValue(value.opt(it)) }

private fun decodeValue(value: Any?): Any? = when (value) {
    is JSONObject -> decodeObject(value)
    is JSONArray -> (0 until value.length()).map { decodeValue(value.opt(it)) }
    JSONObject.NULL -> null
    else -> value
}

/** Encode a protocol reply; lists and nested maps become JSON arrays and objects. */
internal fun encodeObject(value: Map<String, Any?>): JSONObject {
    val result = JSONObject()
    for ((key, item) in value) {
        result.put(key, encodeValue(item))
    }
    return result
}

private fun encodeValue(value: Any?): Any? = when (value) {
    null -> JSONObject.NULL
    is Map<*, *> -> encodeObject(value.entries.associate { (key, item) -> key.toString() to item })
    is List<*> -> JSONArray().also { array -> value.forEach { array.put(encodeValue(it)) } }
    else -> value
}
