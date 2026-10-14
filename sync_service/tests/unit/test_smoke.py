from sync.application.sync_user import Preview, ServiceResult
from sync.smoke import _format_preview, _format_result, _parse


def test_preview_output_has_counts_and_failure_count_without_failure_names() -> None:
    line = _format_preview(
        "garmin", Preview("partial", {"daily_stats": 7, "activity": 2}, ("sensitive item",))
    )
    assert line == "garmin: partial (activity=2, daily_stats=7); failed parts=1"
    assert "sensitive item" not in line


def test_smoke_parser_requires_a_user_and_accepts_services() -> None:
    args = _parse(
        ["--user", "00000000-0000-0000-0000-000000000001", "--service", "garmin", "--dry-run"]
    )
    assert args.service == ["garmin"]
    assert args.dry_run is True


def test_sync_output_has_status_and_counts_only() -> None:
    assert _format_result(ServiceResult("yazio", "ok", written=3, unchanged=2)) == (
        "yazio: ok (written=3, unchanged=2)"
    )
