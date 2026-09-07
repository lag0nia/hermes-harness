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
    assert result.owner is Owner.ENGINEER
    assert result.stages == (Stage.IMPLEMENT, Stage.TEST, Stage.CHANGE_EVENT, Stage.DOCUMENT)
    assert result.metadata["worktree"] and result.metadata["patch_queue"]
    assert calls == ["tests"]


def test_external_r1_uses_engineer_but_preserves_harness_path_boundary():
    pipeline = ChangePipeline(
        run_tests=lambda _: True, health_check=lambda _: True, rollback_ready=lambda _: True
    )
    planned = pipeline.plan(ChangeRequest("feature", RiskLevel.R1, project="external"))
    assert planned.stages[:2] == (Stage.RESEARCH, Stage.IMPLEMENT)
    assert planned.owner is Owner.ENGINEER
    with pytest.raises(PermissionError):
        pipeline.validate_path(Owner.ENGINEER, "src/hermes_harness/control_plane/router.py")


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


def test_external_engineer_path_boundary_is_enforced_before_gates():
    pipeline = ChangePipeline(
        run_tests=lambda _: True, health_check=lambda _: True, rollback_ready=lambda _: True
    )
    request = ChangeRequest(
        "x", RiskLevel.R0, project="external", changed_paths=("config/routing.yaml",)
    )
    with pytest.raises(PermissionError):
        pipeline.execute(request)


def test_external_engineer_path_boundary_normalizes_parent_components():
    with pytest.raises(PermissionError):
        ChangePipeline.validate_path(Owner.ENGINEER, "x/../src/hermes_harness/secret.py")


def test_engineer_rejects_windows_absolute_paths():
    with pytest.raises(PermissionError):
        ChangePipeline.validate_path(Owner.ENGINEER, "C:/outside.txt")
