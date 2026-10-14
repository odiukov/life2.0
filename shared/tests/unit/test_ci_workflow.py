from pathlib import Path

import yaml


def test_integration_gate_runs_independently_of_failed_unit_job() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    jobs = workflow["jobs"]
    integration_jobs = [
        job
        for job in jobs.values()
        if any(step.get("run") == "make test-integration" for step in job["steps"])
    ]
    assert len(integration_jobs) == 1
    job = integration_jobs[0]
    assert not job.get("needs"), "A failed unit job must not suppress the integration gate"
    commands = [step.get("run") for step in job["steps"]]
    assert "uv sync --all-packages --all-extras --frozen" in commands
    assert "make test" not in commands, "Fail-fast unit failures must not skip integration"
    assert not job.get("continue-on-error", False)
