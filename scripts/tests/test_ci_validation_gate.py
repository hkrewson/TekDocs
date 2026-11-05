from __future__ import annotations

from scripts.ci_validation_gate import (
    CODE_JOBS,
    INTEGRATION_JOBS,
    RELEASE_JOBS,
    validate,
)


ALL_JOBS = (*CODE_JOBS, *INTEGRATION_JOBS, *RELEASE_JOBS)


def state(*, lane: str, code: bool, integration: bool, release: bool):
    enabled = {
        **{job: code for job in CODE_JOBS},
        **{job: integration for job in INTEGRATION_JOBS},
        **{job: release for job in RELEASE_JOBS},
    }
    return {
        "prepare": {
            "result": "success",
            "outputs": {
                "lane": lane,
                "code": str(code).lower(),
                "integration": str(integration).lower(),
                "release": str(release).lower(),
            },
        },
        **{
            job: {"result": "success" if enabled[job] else "skipped", "outputs": {}}
            for job in ALL_JOBS
        },
    }


def test_documentation_lane_accepts_intentional_skips():
    assert validate(state(lane="documentation", code=False, integration=False, release=False)) == []


def test_pull_request_lane_requires_only_code_jobs():
    assert validate(state(lane="pull-request", code=True, integration=False, release=False)) == []


def test_main_integration_lane_requires_full_runtime_without_release_jobs():
    assert validate(state(lane="integration", code=True, integration=True, release=False)) == []


def test_release_lane_requires_every_group():
    assert validate(state(lane="integration", code=True, integration=True, release=True)) == []


def test_failed_required_job_fails_the_stable_gate():
    needs = state(lane="pull-request", code=True, integration=False, release=False)
    needs["frontend"]["result"] = "failure"
    assert "frontend concluded 'failure'" in "\n".join(validate(needs))


def test_unexpected_execution_fails_the_stable_gate():
    needs = state(lane="documentation", code=False, integration=False, release=False)
    needs["backend"]["result"] = "success"
    assert "backend concluded 'success', expected 'skipped'" in "\n".join(validate(needs))


def test_release_cannot_bypass_integration():
    errors = validate(state(lane="pull-request", code=True, integration=False, release=True))
    assert "release jobs require the integration lane" in errors
