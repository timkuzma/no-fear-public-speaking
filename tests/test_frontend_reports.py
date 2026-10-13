"""Report rendering, export parity and selected focus integration without real AI calls."""
from pathlib import Path
import subprocess


def test_report_reading_export_and_repeat():
    result = subprocess.run(['node', str(Path(__file__).with_name('frontend_reports.mjs'))],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
