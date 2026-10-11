"""Validate browser capture PCM and upload lifecycle without real devices."""
from pathlib import Path
import subprocess


def test_incremental_audio_preserves_standalone_wav_and_fallback():
    script = Path(__file__).with_name('frontend_live_audio.mjs')
    result = subprocess.run(['node', str(script)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PCM WAV' in result.stdout
