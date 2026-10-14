from pathlib import Path

import pytest


def test_snapshot_matches_existing_file(
    snapshot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    snapshot("fixture-selftest", "hello\nworld\n")


def test_snapshot_mismatch_fails(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        test_x="""
def test_it(snapshot):
    snapshot("one", "actual")
"""
    )
    (pytester.path / "snapshots").mkdir()
    (pytester.path / "snapshots" / "one.txt").write_text("expected", "utf-8")
    result = pytester.runpytest("-p", "shared.testing.pytest_plugin", "-p", "no:cacheprovider")
    result.assert_outcomes(failed=1)
    pytester.runpytest("-p", "shared.testing.pytest_plugin", "--update-snapshots").assert_outcomes(
        passed=1
    )
    assert (pytester.path / "snapshots" / "one.txt").read_text("utf-8") == "actual"
