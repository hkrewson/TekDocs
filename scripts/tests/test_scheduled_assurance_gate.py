from datetime import datetime, timezone

from scripts.scheduled_assurance_gate import should_run


NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)


def decide(**overrides):
    values = {
        "event_name": "schedule",
        "current_sha": "current",
        "prior_sha": "current",
        "prior_conclusion": "success",
        "now": NOW,
    }
    values.update(overrides)
    return should_run(**values)


def test_recent_unchanged_schedule_is_deduplicated():
    run, reason = decide()
    assert run is False
    assert "same commit" in reason


def test_changed_commit_runs():
    run, reason = decide(prior_sha="previous")
    assert run is True
    assert "changed" in reason


def test_unchanged_commit_gets_monthly_refresh():
    run, reason = decide(now=datetime(2026, 12, 2, tzinfo=timezone.utc))
    assert run is True
    assert "monthly refresh" in reason


def test_prior_failure_is_retried():
    run, reason = decide(prior_conclusion="failure")
    assert run is True
    assert "failure" in reason


def test_manual_and_called_workflows_always_run():
    assert decide(event_name="workflow_dispatch")[0] is True
    assert decide(event_name="workflow_call")[0] is True


def test_missing_history_fails_open():
    assert decide(prior_sha=None, prior_conclusion=None)[0] is True
