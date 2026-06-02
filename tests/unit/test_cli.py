"""Tests for tethering.cli"""

from __future__ import annotations

import pytest

from tethering.cli import build_parser, validate_args, dispatch, main


@pytest.fixture
def mock_run(mocker):
    """A mock ModelRun instance with all methods stubbed."""
    run = mocker.MagicMock()
    run.run_id = "member_0001"
    run.root = "/tmp/run"
    run.submit.return_value = "12345.pbs"
    run.submit_advance.return_value = "12345.pbs"
    run.advance.return_value = "12345.pbs"
    run.retry.return_value = "12345.pbs"
    run.format_status.return_value = "Run: member_0001"
    return run


@pytest.fixture
def mock_load(mocker, mock_run):
    """Patch ModelRun.load to return mock_run."""
    return mocker.patch("tethering.cli.ModelRun.load", return_value=mock_run)


@pytest.fixture
def mock_create(mocker, mock_run):
    """Patch ModelRun.create to return mock_run."""
    return mocker.patch("tethering.cli.ModelRun.create", return_value=mock_run)


def test_create_with_config_passes():
    """Test that create with a config passes"""
    parser = build_parser()
    args = parser.parse_args(["--create", "--config", "run.yaml"])
    validate_args(args, parser)


def test_create_without_config_raises():
    """Test that create without a config raises an error"""
    parser = build_parser()
    args = parser.parse_args(["--create"])
    with pytest.raises(SystemExit) as exc:
        validate_args(args, parser)
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "action", ["--submit", "--advance", "--fail", "--retry", "--print-status"]
)
def test_validate_args_action_without_root_raises(action):
    """Test that actions which require a root fail when root not supplied"""
    parser = build_parser()
    extra = ["--stage", "spinup_ad"] if action in ("--advance", "--fail") else []
    args = parser.parse_args([action] + extra)
    with pytest.raises(SystemExit) as exc:
        validate_args(args, parser)
    assert exc.value.code == 2


def test_validate_args_submit_advance_with_all_args_passes():
    """Test that submit-advance with correct arguments passes"""
    parser = build_parser()
    args = parser.parse_args(
        [
            "--submit-advance",
            "--root",
            "/tmp/run",
            "--stage",
            "spinup_ad",
            "--cime-job-id",
            "12345.pbs",
        ]
    )
    validate_args(args, parser)


def test_validate_args_submit_advance_without_stage_raises():
    """Test that submit-advance without stage fails"""
    parser = build_parser()
    args = parser.parse_args(
        ["--submit-advance", "--root", "/tmp/run", "--cime-job-id", "12345.pbs"]
    )
    with pytest.raises(SystemExit) as exc:
        validate_args(args, parser)
    assert exc.value.code == 2


def test_validate_args_submit_advance_without_cime_job_id_raises():
    """Test that submit-advance without cime job id fails"""
    parser = build_parser()
    args = parser.parse_args(
        ["--submit-advance", "--root", "/tmp/run", "--stage", "spinup_ad"]
    )
    with pytest.raises(SystemExit) as exc:
        validate_args(args, parser)
    assert exc.value.code == 2


def test_validate_args_advance_with_stage_passes():
    """Test that advance with stage passes"""
    parser = build_parser()
    args = parser.parse_args(
        ["--advance", "--root", "/tmp/run", "--stage", "spinup_ad"]
    )
    validate_args(args, parser)


def test_validate_args_advance_without_stage_raises():
    """Test that advance without stage fails"""
    parser = build_parser()
    args = parser.parse_args(["--advance", "--root", "/tmp/run"])
    with pytest.raises(SystemExit) as exc:
        validate_args(args, parser)
    assert exc.value.code == 2


def test_validate_args_fail_with_stage_passes():
    """Test that fail with a stage passes"""
    parser = build_parser()
    args = parser.parse_args(["--fail", "--root", "/tmp/run", "--stage", "spinup_ad"])
    validate_args(args, parser)


def test_validate_args_fail_without_stage_raises():
    """Test that fail without a stage fails"""
    parser = build_parser()
    args = parser.parse_args(["--fail", "--root", "/tmp/run"])
    with pytest.raises(SystemExit) as exc:
        validate_args(args, parser)
    assert exc.value.code == 2


def test_validate_args_retry_without_stage_passes():
    """Test that fail without a stage passes"""
    parser = build_parser()
    args = parser.parse_args(["--retry", "--root", "/tmp/run"])
    validate_args(args, parser)


def test_validate_args_retry_with_stage_passes():
    """Test that fail with a stage passes"""
    parser = build_parser()
    args = parser.parse_args(["--retry", "--root", "/tmp/run", "--stage", "spinup_ad"])
    validate_args(args, parser)


def test_dispatch_create_calls_model_run_create(mock_create):
    """Test that create actually calls model_run.create"""
    parser = build_parser()
    args = parser.parse_args(["--create", "--config", "run.yaml"])
    dispatch(args)
    mock_create.assert_called_once_with("run.yaml")


def test_dispatch_create_returns_zero(mock_create):
    """Test that create returns 0"""
    parser = build_parser()
    args = parser.parse_args(["--create", "--config", "run.yaml"])
    assert dispatch(args) == 0


def test_dispatch_print_status_calls_format_status(mock_load, mock_run):
    """Test that print-status actually calls model_run.format_status"""
    parser = build_parser()
    args = parser.parse_args(["--print-status", "--root", "/tmp/run"])
    dispatch(args)
    mock_run.format_status.assert_called_once()


def test_dispatch_print_status_returns_zero(mock_load, mock_run):
    """Test that print-status returns zero"""
    parser = build_parser()
    args = parser.parse_args(["--print-status", "--root", "/tmp/run"])
    assert dispatch(args) == 0


def test_dispatch_submit_calls_submit(mock_load, mock_run):
    """Test that submit actually calls model_run.submit"""
    parser = build_parser()
    args = parser.parse_args(["--submit", "--root", "/tmp/run"])
    dispatch(args)
    mock_run.submit.assert_called_once_with(dry_run=False)


def test_dispatch_submit_dry_run_passed_through(mock_load, mock_run):
    """Test that submit with a dry run is passed through"""
    parser = build_parser()
    args = parser.parse_args(["--submit", "--root", "/tmp/run", "--dry-run"])
    dispatch(args)
    mock_run.submit.assert_called_once_with(dry_run=True)


def test_dispatch_submit_returns_zero(mock_load, mock_run):
    """Test that submit returns zero"""
    parser = build_parser()
    args = parser.parse_args(["--submit", "--root", "/tmp/run"])
    assert dispatch(args) == 0


def test_dispatch_submit_advance_calls_submit_advance(mock_load, mock_run):
    """Test that submit-advance actually calls model_run.submit_advance"""
    parser = build_parser()
    args = parser.parse_args(
        [
            "--submit-advance",
            "--root",
            "/tmp/run",
            "--stage",
            "spinup_ad",
            "--cime-job-id",
            "55555.pbs",
        ]
    )
    dispatch(args)
    mock_run.submit_advance.assert_called_once_with(
        "spinup_ad", "55555.pbs", dry_run=False
    )


def test_dispatch_submit_advance_dry_run_passed_through(mock_load, mock_run):
    """Test that submit-advance with a dry run is passed through"""
    parser = build_parser()
    args = parser.parse_args(
        [
            "--submit-advance",
            "--root",
            "/tmp/run",
            "--stage",
            "spinup_ad",
            "--cime-job-id",
            "55555.pbs",
            "--dry-run",
        ]
    )
    dispatch(args)
    mock_run.submit_advance.assert_called_once_with(
        "spinup_ad", "55555.pbs", dry_run=True
    )


def test_dispatch_submit_advance_returns_zero(mock_load, mock_run):
    """Test that submit-advance returns zero"""
    parser = build_parser()
    args = parser.parse_args(
        [
            "--submit-advance",
            "--root",
            "/tmp/run",
            "--stage",
            "spinup_ad",
            "--cime-job-id",
            "55555.pbs",
        ]
    )
    assert dispatch(args) == 0


def test_dispatch_advance_calls_advance(mock_load, mock_run):
    """Test that advance actually calles model_run.advance"""
    parser = build_parser()
    args = parser.parse_args(
        ["--advance", "--root", "/tmp/run", "--stage", "spinup_ad"]
    )
    dispatch(args)
    mock_run.advance.assert_called_once_with("spinup_ad", dry_run=False)


def test_dispatch_advance_dry_run_passed_through(mock_load, mock_run):
    """Test that advance with a dry run is passed through"""
    parser = build_parser()
    args = parser.parse_args(
        ["--advance", "--root", "/tmp/run", "--stage", "spinup_ad", "--dry-run"]
    )
    dispatch(args)
    mock_run.advance.assert_called_once_with("spinup_ad", dry_run=True)


def test_dispatch_advance_returns_zero(mock_load, mock_run):
    """Test that advance returns zero"""
    parser = build_parser()
    args = parser.parse_args(
        ["--advance", "--root", "/tmp/run", "--stage", "spinup_ad"]
    )
    assert dispatch(args) == 0


def test_dispatch_fail_calls_fail(mock_load, mock_run):
    """Test that fail actually calls model_run.fail"""
    parser = build_parser()
    args = parser.parse_args(["--fail", "--root", "/tmp/run", "--stage", "spinup_ad"])
    dispatch(args)
    mock_run.fail.assert_called_once_with("spinup_ad")


def test_dispatch_fail_returns_zero(mock_load, mock_run):
    """Test that fail actually returns zero"""
    parser = build_parser()
    args = parser.parse_args(["--fail", "--root", "/tmp/run", "--stage", "spinup_ad"])
    assert dispatch(args) == 0


def test_dispatch_retry_calls_retry_with_stage(mock_load, mock_run):
    """Test that retry with stage actually calls model_run.stage"""
    parser = build_parser()
    args = parser.parse_args(["--retry", "--root", "/tmp/run", "--stage", "spinup_ad"])
    dispatch(args)
    mock_run.retry.assert_called_once_with("spinup_ad", dry_run=False, skip_script=False)


def test_dispatch_retry_calls_retry_without_stage(mock_load, mock_run):
    """Test that retry without stage actually calls model_run.stage"""
    parser = build_parser()
    args = parser.parse_args(["--retry", "--root", "/tmp/run"])
    dispatch(args)
    mock_run.retry.assert_called_once_with(None, dry_run=False, skip_script=False)


def test_dispatch_retry_dry_run_passed_through(mock_load, mock_run):
    """Test that retry with dry-run is passed through"""
    parser = build_parser()
    args = parser.parse_args(["--retry", "--root", "/tmp/run", "--dry-run"])
    dispatch(args)
    mock_run.retry.assert_called_once_with(None, dry_run=True, skip_script=False)
    
def test_dispatch_retry_skip_script_passed_through(mock_load, mock_run):
    """Test that retry with skip-script is passed through"""
    parser = build_parser()
    args = parser.parse_args(["--retry", "--root", "/tmp/run", "--skip-script"])
    dispatch(args)
    mock_run.retry.assert_called_once_with(None, dry_run=False, skip_script=True)


def test_dispatch_retry_returns_zero(mock_load, mock_run):
    """Test that retry with stage returns zero"""
    parser = build_parser()
    args = parser.parse_args(["--retry", "--root", "/tmp/run", "--stage", "spinup_ad"])
    assert dispatch(args) == 0
    
def test_dispatch_unhandled_action_raises(mock_load, mock_run):
    """Test that dispatch raises if no action branch matches"""
    parser = build_parser()
    args = parser.parse_args(["--print-status", "--root", "/tmp/run"])
    args.print_status = False  # force all branches to be False
    with pytest.raises(RuntimeError):
        dispatch(args)
        
@pytest.mark.parametrize(
    "argv",
    [
        ["--create"],  # missing --config
        ["--submit"],  # missing --root
        ["--advance", "--root", "/tmp/run"],  # missing --stage
        ["--fail", "--root", "/tmp/run"],  # missing --stage
        [
            "--submit-advance",
            "--root",
            "/tmp/run",
            "--stage",
            "spinup_ad",
        ],  # missing --cime-job-id
    ],
)
def test_main_argument_errors_exit_with_code_2(argv):
    """Test that missing arguments error with code 2"""
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2


def test_main_create_exits_zero(mock_create):
    """Test that main with create and correct args returns 0"""
    assert main(["--create", "--config", "run.yaml"]) == 0


def test_main_status_exits_zero(mock_load):
    """Test that main with print-status and correct args returns 0"""
    assert main(["--print-status", "--root", "/tmp/run"]) == 0


def test_main_submit_exits_zero(mock_load):
    """Test that main with submit and correct args returns 0"""
    assert main(["--submit", "--root", "/tmp/run"]) == 0


def test_main_submit_advance_exits_zero(mock_load):
    """Test that main with submit-advance and correct args returns 0"""
    assert (
        main(
            [
                "--submit-advance",
                "--root",
                "/tmp/run",
                "--stage",
                "spinup_ad",
                "--cime-job-id",
                "2003.desched1",
            ]
        )
        == 0
    )


def test_main_advance_exits_zero(mock_load):
    """Test that main with advance and correct args returns 0"""
    assert main(["--advance", "--root", "/tmp/run", "--stage", "spinup_ad"]) == 0


def test_main_fail_exits_zero(mock_load):
    """Test that main with fail and correct args returns 0"""
    assert main(["--fail", "--root", "/tmp/run", "--stage", "spinup_ad"]) == 0


def test_main_retry_exits_zero(mock_load):
    """Test that main with retry and correct args returns 0"""
    assert main(["--retry", "--root", "/tmp/run"]) == 0


def test_main_load_missing_root_exits_one(tmp_path):
    """Test that main load with a missing root gives exit status 1"""
    result = main(["--print-status", "--root", str(tmp_path / "nonexistent")])
    assert result == 1


def test_main_runtime_error_prints_to_stderr(tmp_path, capsys):
    """Test that main with a runtime error prints output to stderr"""
    main(["--print-status", "--root", str(tmp_path / "nonexistent")])
    assert "ERROR" in capsys.readouterr().err


def test_main_keyboard_interrupt_exits_130(mocker):
    """Test that main with a keyboard interrupt exist with status 130"""
    mocker.patch("tethering.cli.dispatch", side_effect=KeyboardInterrupt)
    result = main(["--print-status", "--root", "/tmp/run"])
    assert result == 130


def test_main_unexpected_exception_exits_one(mocker):
    """Test that main with some unexpected exception exist with status 1"""
    mocker.patch("tethering.cli.dispatch", side_effect=RuntimeError("boom"))
    result = main(["--print-status", "--root", "/tmp/run"])
    assert result == 1


def test_main_unexpected_exception_prints_to_stderr(mocker, capsys):
    """Test that main with some unexpected exception prints to stderr"""
    mocker.patch("tethering.cli.dispatch", side_effect=RuntimeError("boom"))
    main(["--print-status", "--root", "/tmp/run"])
    assert "ERROR: boom" in capsys.readouterr().err

def test_main_debug_flag_reraises_exception(mocker):
    """Test that --debug causes exceptions to propagate rather than being caught"""
    mocker.patch("tethering.cli.dispatch", side_effect=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        main(["--print-status", "--root", "/tmp/run", "--debug"])
        
