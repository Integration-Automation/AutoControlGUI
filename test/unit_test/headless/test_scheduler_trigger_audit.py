"""Regression tests for the scheduler / trigger defects found in the 2026-09-23 audit.

Cron had three departures from the standard it names (day-of-month and
day-of-week ANDed when both are set, Sunday-as-7 rejected, ``a/n`` read as just
``a``) and a one-year search horizon that 29 February outruns — after which the
scheduler fired the job on every tick. ``AllOf`` spent an edge child's event
before a later level child failed, the IMAP fetch marked mail read, and a
webhook script failing with an unexpected type was recorded as a success.
"""
import datetime as _dt

import pytest

from je_auto_control.utils.scheduler import scheduler as scheduler_module
from je_auto_control.utils.scheduler.cron import next_match, parse_cron
from je_auto_control.utils.triggers.trigger_engine import (
    AllOfTrigger, CronTrigger,
)

_NOW = _dt.datetime(2026, 9, 23, 12, 0)   # a Wednesday


# --- cron ---------------------------------------------------------------------

def test_restricted_day_of_month_and_week_are_ored():
    # "the 1st, and every Monday": the next Monday comes first.
    assert next_match(parse_cron("0 0 1 * 1"), _NOW) == _dt.datetime(2026, 9, 28)


def test_an_unrestricted_day_field_still_ands():
    # dom '*' with dow 1 is "every Monday", not "every day".
    assert next_match(parse_cron("0 0 * * 1"), _NOW) == _dt.datetime(2026, 9, 28)


def test_sunday_may_be_written_as_seven():
    assert next_match(parse_cron("0 0 * * 7"), _NOW) == _dt.datetime(2026, 9, 27)
    assert parse_cron("0 0 * * 7").days_of_week == {0}


def test_a_start_with_a_step_runs_to_the_end_of_the_range():
    assert sorted(parse_cron("5/15 * * * *").minutes) == [5, 20, 35, 50]


def test_29_february_is_found_more_than_a_year_ahead():
    assert next_match(parse_cron("0 0 29 2 *"), _NOW) == _dt.datetime(2028, 2, 29)


def test_an_impossible_date_still_raises():
    with pytest.raises(ValueError):
        next_match(parse_cron("0 0 31 2 *"), _NOW)


# --- scheduler ----------------------------------------------------------------

@pytest.mark.parametrize("add", ["add_job", "add_cron_job"])
def test_max_runs_below_one_is_refused(add):
    schedule = scheduler_module.Scheduler()
    args = ("s.json", 60) if add == "add_job" else ("s.json", "* * * * *")
    with pytest.raises(ValueError, match="max_runs"):
        getattr(schedule, add)(*args, max_runs=0)


def test_a_cron_job_with_no_next_run_is_removed_not_refired(monkeypatch, tmp_path):
    script = tmp_path / "s.json"
    script.write_text('[["AC_noop_that_is_not_there"]]', encoding="utf-8")
    schedule = scheduler_module.Scheduler(executor=lambda actions: None)
    job = schedule.add_cron_job(str(script), "* * * * *")

    def nothing_left(*_args, **_kwargs):
        raise ValueError("no match")

    monkeypatch.setattr(scheduler_module, "next_match", nothing_left)
    schedule._fire(job, 0.0, _NOW.timestamp())
    assert schedule.list_jobs() == [], "a job with no future run must go"


# --- triggers -----------------------------------------------------------------

class _Flag:
    def __init__(self, value=False):
        self.value = value

    def is_fired(self):
        return self.value


def test_all_of_does_not_spend_the_cron_minute_on_a_false_condition(monkeypatch):
    cron = CronTrigger(trigger_id="c", script_path="s.json", cron="* * * * *")
    flag = _Flag(False)
    # Cron listed first: the order that used to lose the minute.
    trigger = AllOfTrigger(trigger_id="a", script_path="s.json", children=[cron, flag])
    assert trigger.is_fired() is False
    flag.value = True
    assert trigger.is_fired() is True, "the same minute must still fire"


def test_the_imap_fetch_does_not_mark_mail_read():
    from je_auto_control.utils.triggers import email_trigger

    class _Client:
        def __init__(self):
            self.fetched = []

        def uid(self, command, uid, spec):
            self.fetched.append(spec)
            return "OK", [(b"1 (UID 1 BODY[] {5}", b"Subject: x\r\n\r\nhi")]

    client = _Client()
    email_trigger._fetch_message(client, "1")
    assert client.fetched == ["(BODY.PEEK[])"]


def test_a_webhook_script_failing_with_any_type_is_recorded_as_an_error(tmp_path):
    """Only a tuple of four types was caught: a TypeError from the executor
    reached ``finally`` with the status still OK, and the connection dropped."""
    from je_auto_control.utils.triggers.webhook_server import WebhookTriggerServer

    def broken_executor(_actions, _payload):
        raise TypeError("executor bug")

    script = tmp_path / "s.json"
    script.write_text("[]", encoding="utf-8")
    server = WebhookTriggerServer(executor=broken_executor)
    trigger = server.add("/hook", str(script))
    assert server.fire(trigger, {}) is not None
    assert server.list_webhooks()[0].last_status == 500
