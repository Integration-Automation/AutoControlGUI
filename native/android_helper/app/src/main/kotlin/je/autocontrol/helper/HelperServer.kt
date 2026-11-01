package je.autocontrol.helper

import android.net.LocalServerSocket
import android.net.LocalSocket
import android.util.Log
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import je.autocontrol.helper.core.ProtocolHandler
import org.json.JSONObject

private const val TAG = "JeAutoControlHelper"
const val SOCKET_NAME = "je_auto_control_helper"
private const val MAX_LINE = 64 * 1024
private const val SHELL_UID = 2000
private const val ROOT_UID = 0

/**
 * Serve protocol version 1 on the abstract socket [SOCKET_NAME], one client at a time.
 *
 * An abstract socket has no file permissions, so any app could connect: only a peer running as
 * shell (what `adb forward` connections arrive as) or root is served; anything else is closed
 * before a line is read. A line over 64 KiB ends that connection.
 */
class HelperServer(private val protocol: ProtocolHandler) {

    fun serve() {
        // Closed explicitly: LocalServerSocket only implements Closeable on newer API levels.
        val server = LocalServerSocket(SOCKET_NAME)
        try {
            while (true) {
                val client = server.accept()
                try {
                    serveClient(client)
                } finally {
                    client.close()
                }
            }
        } finally {
            server.close()
        }
    }

    private fun serveClient(client: LocalSocket) {
        val uid = client.peerCredentials.uid
        if (uid != SHELL_UID && uid != ROOT_UID) {
            Log.w(TAG, "refused a peer running as uid $uid")
            return
        }
        val reader = BufferedReader(InputStreamReader(client.inputStream, Charsets.UTF_8))
        val writer = OutputStreamWriter(client.outputStream, Charsets.UTF_8)
        while (true) {
            val line = readBoundedLine(reader) ?: return
            val reply = try {
                protocol.handle(decodeObject(JSONObject(line)))
            } catch (failure: org.json.JSONException) {
                mapOf("error" to "invalid_json")
            }
            writer.write(encodeObject(reply).toString())
            writer.write("\n")
            writer.flush()
        }
    }

    private fun readBoundedLine(reader: BufferedReader): String? {
        val line = StringBuilder()
        while (true) {
            val next = reader.read()
            if (next < 0) return if (line.isEmpty()) null else line.toString()
            if (next == '\n'.code) return line.toString()
            if (line.length >= MAX_LINE) return null
            line.append(next.toChar())
        }
    }
}
