import pytest

from hermes_harness.change_pipeline import (
    ChangePipeline,
    ChangeRequest,
    GateFailure,
    Owner,
    RiskLevel,
    Stage,
)


def test_r0_routes_to_owner_runs_gates_and_records_patch_metadata():
    calls = []
    pipeline = ChangePipeline(
        run_tests=lambda _: calls.append("tests") or True,
        health_check=lambda _: True,
        rollback_ready=lambda _: True,
    )
    result = pipeline.execute(ChangeRequest("fix bug", RiskLevel.R0, project="app"))
    assert result.status == "promoted"
    assert result.owner in {Owner.ENGINEER, Owner.CODER}
    assert result.stages == (Stage.IMPLEMENT, Stage.TEST, Stage.CHANGE_EVENT, Stage.DOCUMENT)
    assert result.metadata["worktree"] and result.metadata["patch_queue"]
    assert calls == ["tests"]


def test_r1_includes_architect_and_coder_is_denied_harness_paths():
    pipeline = ChangePipeline(
        run_tests=lambda _: True, health_check=lambda _: True, rollback_ready=lambda _: True
    )
    planned = pipeline.plan(ChangeRequest("feature", RiskLevel.R1, project="external"))
    assert planned.stages[:2] == (Stage.ARCHITECT, Stage.IMPLEMENT)
    assert planned.owner is Owner.CODER
    with pytest.raises(PermissionError):
        pipeline.validate_path(Owner.CODER, "src/hermes_harness/control_plane/router.py")


def test_r2_requires_research_sol_medium_replay_checkpoint_and_confirmation():
    req = ChangeRequest("security", RiskLevel.R2, project="harness", critical=True)
    pipeline = ChangePipeline(
        run_tests=lambda _: True,
        health_check=lambda _: True,
        rollback_ready=lambda _: True,
        sol_review=lambda _: True,
        replay=lambda _: True,
    )
    result = pipeline.execute(req, confirmed=False)
    assert result.status == "waiting_confirmation"
    assert result.sol_effort == "medium"
    approved = pipeline.execute(req, confirmed=True)
    assert approved.status == "promoted"
    assert Stage.RESEARCH in approved.stages and Stage.REPLAY in approved.stages


def test_failed_readiness_gate_does_not_promote():
    pipeline = ChangePipeline(
        run_tests=lambda _: True, health_check=lambda _: False, rollback_ready=lambda _: True
    )
    with pytest.raises(GateFailure, match="health"):
        pipeline.execute(ChangeRequest("x", RiskLevel.R0, project="app"))


def test_coder_path_ownership_is_enforced_before_gates():
    pipeline = ChangePipeline(
        run_tests=lambda _: True, health_check=lambda _: True, rollback_ready=lambda _: True
    )
    request = ChangeRequest(
        "x", RiskLevel.R0, project="external", changed_paths=("config/routing.yaml",)
    )
    with pytest.raises(PermissionError):
        pipeline.execute(request)


def test_coder_path_ownership_normalizes_parent_components():
    with pytest.raises(PermissionError):
        ChangePipeline.validate_path(Owner.CODER, "x/../src/hermes_harness/secret.py")


def test_coder_rejects_windows_absolute_paths():
    with pytest.raises(PermissionError):
        ChangePipeline.validate_path(Owner.CODER, "C:/outside.txt")
