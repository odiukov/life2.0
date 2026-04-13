import subprocess
import shutil


def run_claude(prompt: str, timeout: int = 120) -> str:
    """Run claude CLI with --print flag and return stdout."""
    claude_bin = shutil.which("claude")
    if claude_bin is None:
        raise RuntimeError("claude CLI not found in PATH")

    result = subprocess.run(
        [claude_bin, "--print", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {result.stderr[:500]}")

    return result.stdout.strip()
