"""Registration completion and bounded recovery from stalled browser requests."""
from pathlib import Path
import subprocess


def test_registration_recovery_and_required_account():
    result = subprocess.run(['node', str(Path(__file__).with_name('frontend_auth.mjs'))],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
