import os
import subprocess
import shutil


def run_claude(prompt: str, timeout: int = 120) -> str:
    """Run claude CLI with --print flag and return stdout.

    Uses --bare mode when ANTHROPIC_API_KEY is set (e.g. inside Docker containers
    where macOS Keychain is unavailable). Run scripts/export-auth.sh to populate
    the token from Keychain before starting containers.
    """
    claude_bin = shutil.which("claude")
    if claude_bin is None:
        raise RuntimeError("claude CLI not found in PATH")

    cmd = [claude_bin, "--print"]
    if os.environ.get("ANTHROPIC_API_KEY"):
        cmd.append("--bare")
    cmd.append(prompt)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {result.stderr[:500]}")

    return result.stdout.strip()
