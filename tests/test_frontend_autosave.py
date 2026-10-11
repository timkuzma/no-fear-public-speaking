"""Exercise recording completion, automatic upload, retry and guest persistence."""
from pathlib import Path
import subprocess


def test_recording_lifecycle_autosaves_speech_and_preserves_failed_upload():
    script = Path(__file__).with_name('frontend_autosave.mjs')
    result = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '5 recording lifecycle cases passed' in result.stdout
