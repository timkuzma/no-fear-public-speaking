"""Guard Russian word boundaries, newlines and idempotent presentation formatting."""
from pathlib import Path
import subprocess


def test_russian_typography_boundaries():
    result = subprocess.run(['node', str(Path(__file__).with_name('frontend_typography.mjs'))],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
