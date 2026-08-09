"""R6 CLI tests. `run` is dispatched to a mocked pipeline (no network/LLM)."""
from __future__ import annotations

from resumaker.domain import ApplyDecision, JobPosting, PipelineResult


def test_costs_command_runs(capsys):
    from apps.cli.main import main
    assert main(["costs"]) == 0
    assert "_gemini_budget" in capsys.readouterr().out


def test_run_dispatches_to_pipeline(monkeypatch, capsys):
    from apps.cli import main as cli

    def fake_run(url, **kw):
        return PipelineResult(url=url, job=JobPosting(title="MLE", company="Acme"),
                              decision=ApplyDecision(recommend_apply=True))

    monkeypatch.setattr(cli, "run_pipeline", fake_run)
    rc = cli.main(["run", "https://x/y", "--plain", "--no-cover"])
    out = capsys.readouterr().out
    assert rc == 0 and "MLE @ Acme" in out and "APPLY: YES" in out


def test_run_returns_error_code(monkeypatch):
    from apps.cli import main as cli
    monkeypatch.setattr(cli, "run_pipeline",
                        lambda url, **kw: PipelineResult(url=url, error="boom"))
    assert cli.main(["run", "https://x/y", "--plain"]) == 1
