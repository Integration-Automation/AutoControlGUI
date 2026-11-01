package je.autocontrol.helper.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class FenceLedgerTest {
    private val boot = "6f1cfc87-e569-d6ae-2d37-d14af9cf3f04"
    private val first = "a".repeat(32)
    private val second = "b".repeat(32)
    private val tap = mapOf<String, Any?>("kind" to "tap", "x" to 10, "y" to 20)

    private fun id(n: Int) = n.toString(16).padStart(32, '0')

    @Test
    fun aCommandRunsOnlyUnderTheEpochItWasBegunWith() {
        val ledger = FenceLedger(boot, first)
        assertTrue(ledger.begin(id(1), first, tap).accepted)
        assertEquals(id(1) to tap, ledger.claimNext())
        assertTrue(ledger.stillCurrent(id(1)))
        ledger.finish(id(1), succeeded = true, inputReleased = true)
        val settled = ledger.settle(id(1))
        assertEquals(CommandStatus.COMPLETED, settled.status)
        assertTrue(settled.inputReleased && settled.queueEmpty)
        assertEquals(first, settled.epoch)
        assertEquals(boot, settled.bootId)
    }

    @Test
    fun aStaleEpochAReusedIdAndAFullQueueAreRefused() {
        val ledger = FenceLedger(boot, first, capacity = 1)
        assertEquals("stale_epoch", ledger.begin(id(1), second, tap).reason)
        assertTrue(ledger.begin(id(1), first, tap).accepted)
        assertEquals("duplicate_id", ledger.begin(id(1), first, tap).reason)
        assertEquals("queue_full", ledger.begin(id(2), first, tap).reason)
    }

    @Test
    fun aFenceStopsQueuedOlderCommandsForGood() {
        val ledger = FenceLedger(boot, first)
        ledger.begin(id(1), first, tap)
        ledger.begin(id(2), first, tap)
        val result = ledger.fence(second)
        assertEquals(listOf(id(1), id(2)), result.fenced)
        assertTrue(result.queueEmpty)
        assertNull(result.inflight)
        assertNull(ledger.claimNext())
        assertEquals(CommandStatus.FENCED, ledger.settle(id(1)).status)
        assertEquals("stale_epoch", ledger.begin(id(3), first, tap).reason)
        assertTrue(ledger.begin(id(3), second, tap).accepted)
    }

    @Test
    fun anInjectingCommandIsToldToStopAndCanNeverBecomeCompleted() {
        val ledger = FenceLedger(boot, first)
        ledger.begin(id(1), first, tap)
        ledger.claimNext()
        val result = ledger.fence(second)
        assertEquals(id(1), result.inflight)
        assertFalse(result.queueEmpty || ledger.stillCurrent(id(1)))
        ledger.finish(id(1), succeeded = true, inputReleased = true)
        val settled = ledger.settle(id(1))
        assertEquals(CommandStatus.FENCED, settled.status)
        assertTrue(settled.queueEmpty)
    }

    @Test
    fun unreleasedInputIsReportedAndFailureIsNotCompletion() {
        val ledger = FenceLedger(boot, first)
        ledger.begin(id(1), first, tap)
        ledger.claimNext()
        ledger.finish(id(1), succeeded = false, inputReleased = false)
        val settled = ledger.settle(id(1))
        assertEquals(CommandStatus.FAILED, settled.status)
        assertFalse(settled.inputReleased)
    }

    @Test
    fun onlyOneCommandInjectsAtATime() {
        val ledger = FenceLedger(boot, first)
        ledger.begin(id(1), first, tap)
        ledger.begin(id(2), first, tap)
        ledger.claimNext()
        assertNull(ledger.claimNext())
        assertFalse(ledger.settle(id(2)).queueEmpty)
        assertThrows(IllegalStateException::class.java) { ledger.finish(id(2), true, true) }
    }

    @Test
    fun anUnknownIdSettlesAsRejectedAndTheEpochNeverMovesBack() {
        val ledger = FenceLedger(boot, first)
        assertEquals(CommandStatus.REJECTED, ledger.settle(id(9)).status)
        ledger.fence(second)
        assertThrows(IllegalArgumentException::class.java) { ledger.fence(second) }
        assertEquals(second, ledger.currentEpoch)
    }

    @Test
    fun malformedIdentifiersAreRefused() {
        assertThrows(IllegalArgumentException::class.java) { FenceLedger(boot, "short") }
        val ledger = FenceLedger(boot, first)
        assertThrows(IllegalArgumentException::class.java) { ledger.begin("A".repeat(32), first, tap) }
        assertThrows(IllegalArgumentException::class.java) { ledger.settle("../x") }
    }
}
