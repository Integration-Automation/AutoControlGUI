package je.autocontrol.helper

import android.app.Activity
import android.app.Instrumentation
import android.os.Bundle
import android.util.Log
import java.io.File
import java.security.SecureRandom
import je.autocontrol.helper.core.FenceLedger
import je.autocontrol.helper.core.ProtocolHandler

private const val TAG = "JeAutoControlHelper"

/** Random 32-hex identifier for this instrumentation run's helper epoch. */
internal fun randomToken(): String {
    val bytes = ByteArray(16).also { SecureRandom().nextBytes(it) }
    return bytes.joinToString("") { "%02x".format(it) }
}

/**
 * Entry point: `am instrument -w je.autocontrol.helper/.HelperInstrumentation`.
 *
 * Every request goes through one [FenceLedger]; the [Injector] is the only writer and asks the
 * ledger between events whether it may go on. The run ends when the server stops.
 */
class HelperInstrumentation : Instrumentation() {

    override fun onCreate(arguments: Bundle?) {
        super.onCreate(arguments)
        start()
    }

    override fun onStart() {
        val bootId = File("/proc/sys/kernel/random/boot_id").readText().trim()
        val helperEpoch = randomToken()
        val ledger = FenceLedger(bootId, helperEpoch)
        val injector = Injector(uiAutomation, ledger)
        injector.start()
        val result = Bundle()
        try {
            HelperServer(ProtocolHandler(ledger, bootId, helperEpoch)).serve()
        } catch (failure: Exception) {
            Log.e(TAG, "helper server stopped", failure)
            result.putString("error", failure.javaClass.simpleName)
        } finally {
            injector.stop()
        }
        finish(Activity.RESULT_OK, result)
    }
}
