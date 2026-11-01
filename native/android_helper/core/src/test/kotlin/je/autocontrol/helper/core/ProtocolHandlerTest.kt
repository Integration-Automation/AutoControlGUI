package je.autocontrol.helper.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ProtocolHandlerTest {
    private val boot = "6f1cfc87-e569-d6ae-2d37-d14af9cf3f04"
    private val first = "a".repeat(32)
    private val second = "b".repeat(32)
    private val helper = "c".repeat(32)
    private val id = "1".repeat(32)
    private val tap = mapOf("kind" to "tap", "x" to 10, "y" to 20)

    private fun handler() = ProtocolHandler(FenceLedger(boot, first), boot, helper)

    @Test
    fun helloNamesTheProtocolBootAndEpochs() {
        assertEquals(mapOf("protocol" to 1, "boot_id" to boot, "helper_epoch" to helper, "epoch" to first),
            handler().handle(mapOf("op" to "hello")))
    }

    @Test
    fun aBegunCommandSettlesWithItsOwnAccount() {
        val protocol = handler()
        val begun = protocol.handle(mapOf("op" to "begin", "id" to id, "epoch" to first, "command" to tap))
        assertEquals(true, begun["accepted"])
        val settled = protocol.handle(mapOf("op" to "settle", "id" to id))
        assertEquals("queued", settled["status"])
        assertEquals(first, settled["epoch"])
        assertEquals(false, settled["queue_empty"])
    }

    @Test
    fun aFenceReplyListsWhatItStopped() {
        val protocol = handler()
        protocol.handle(mapOf("op" to "begin", "id" to id, "epoch" to first, "command" to tap))
        val fenced = protocol.handle(mapOf("op" to "fence", "epoch" to second))
        assertEquals(listOf(id), fenced["fenced"])
        assertNull(fenced["inflight"])
        assertEquals(true, fenced["queue_empty"])
        assertEquals("fenced", protocol.handle(mapOf("op" to "settle", "id" to id))["status"])
        val stale = protocol.handle(mapOf("op" to "begin", "id" to "2".repeat(32), "epoch" to first, "command" to tap))
        assertEquals(false, stale["accepted"])
        assertEquals("stale_epoch", stale["reason"])
    }

    @Test
    fun malformedRequestsGetAnErrorAndNeverReachTheLedger() {
        val protocol = handler()
        for (request in listOf(
            mapOf("op" to "launch"),
            mapOf("op" to "begin", "id" to id, "epoch" to first),
            mapOf("op" to "begin", "id" to id, "epoch" to first, "command" to mapOf("kind" to "shell", "cmd" to "rm")),
            mapOf("op" to "begin", "id" to "x", "epoch" to first, "command" to tap),
            mapOf("op" to "fence", "epoch" to first),
            mapOf("op" to "settle"),
        )) {
            assertTrue(protocol.handle(request).containsKey("error"))
        }
        assertEquals("rejected", protocol.handle(mapOf("op" to "settle", "id" to id))["status"])
    }

    @Test
    fun onlyClosedBoundedCommandShapesAreAccepted() {
        assertEquals(mapOf("kind" to "tap", "x" to 10, "y" to 20), checkCommand(tap))
        assertEquals(mapOf("kind" to "key", "keycode" to 66), checkCommand(mapOf("kind" to "key", "keycode" to 66)))
        val swipe = mapOf("kind" to "swipe", "x" to 0, "y" to 0, "to_x" to 5, "to_y" to 5, "duration_ms" to 300)
        assertEquals(swipe, checkCommand(swipe))
        for (bad in listOf(
            mapOf("kind" to "tap", "x" to 10),
            mapOf("kind" to "tap", "x" to 10, "y" to 20, "extra" to 1),
            mapOf("kind" to "tap", "x" to -1, "y" to 20),
            mapOf("kind" to "tap", "x" to 1.5, "y" to 20),
            mapOf("kind" to "tap", "x" to "10", "y" to 20),
            mapOf("kind" to "key", "keycode" to 100_000),
            swipe + ("duration_ms" to 60_000),
        )) {
            assertNull(checkCommand(bad))
        }
        assertFalse(checkCommand(mapOf("kind" to "tap", "x" to 100_000, "y" to 0)) == null)
    }
}
