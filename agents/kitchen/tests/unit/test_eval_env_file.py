"""Offline check that the documented eval command loads provider settings."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("process_key", "expected"),
    [(None, "synthetic-file-key"), ("synthetic-process-key", "synthetic-process-key")],
)
def test_make_evals_loads_dotenv_without_overriding_exported_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, process_key: str | None, expected: str
) -> None:
    project = Path(__file__).resolve().parents[4]
    uv = shutil.which("uv")
    assert uv is not None
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=synthetic-file-key\n", encoding="utf-8")
    if process_key is None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENROUTER_API_KEY", process_key)
    monkeypatch.setenv("EVAL_EXPECTED_KEY", expected)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "uv"
    shim.write_text(
        "#!/usr/bin/env python3\n"
        "import os, subprocess, sys\n"
        "assert sys.argv[1:] == "
        "['run', '--env-file', '.env', 'pytest', '-m', 'evals', '-q']\n"
        "code = 'from kitchen.settings import KitchenSettings; import os; ' "
        "+ 'settings = KitchenSettings.model_validate({' "
        '+ \'"database": {"dsn": "postgresql://unused@localhost/unused"}}); \' '
        "+ 'assert settings.openrouter_api_key.get_secret_value() == ' "
        "+ 'os.environ[\"EVAL_EXPECTED_KEY\"]'\n"
        f"sys.exit(subprocess.run([{uv!r}, 'run', '--project', {str(project)!r}, "
        "'--env-file', '.env', 'python', '-c', code], check=False).returncode)\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir), prepend=":")
    result = subprocess.run(
        ["make", "-f", str(project / "Makefile"), "evals"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_make_evals_without_dotenv_propagates_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = Path(__file__).resolve().parents[4]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "uv"
    shim.write_text(
        "#!/bin/sh\n[ \"$*\" = 'run pytest -m evals -q' ] || exit 98\nexit 23\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir), prepend=":")
    result = subprocess.run(
        ["make", "-f", str(project / "Makefile"), "evals"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Error 23" in result.stderr
