"""Real browser-style WebM upload retains camera video and seekable audio."""

import asyncio
import subprocess

from fastapi.testclient import TestClient
import imageio_ffmpeg
import pytest

from server.ai import _ffmpeg, probe_media
from server.app import create_app


def make_streaming_webm(path, with_video):
    command = [_ffmpeg(), '-nostdin', '-v', 'error']
    if with_video:
        command += ['-f', 'lavfi', '-i', 'testsrc=size=320x180:rate=10']
    command += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-t', '1']
    if with_video:
        command += ['-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libvpx',
                    '-pix_fmt', 'yuv420p', '-b:v', '150k']
    command += ['-c:a', 'libopus', '-live', '1', '-y', str(path)]
    subprocess.run(command, check=True, capture_output=True, timeout=15)


def first_video_frame(path):
    frames = imageio_ffmpeg.read_frames(str(path), pix_fmt='rgb24')
    try:
        metadata = next(frames)
        return metadata, next(frames)
    finally:
        frames.close()


@pytest.mark.parametrize('with_video', [True, False])
def test_real_webm_upload_preserves_video_and_audio(with_video, tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.delenv('APP_ORIGIN', raising=False)
    monkeypatch.delenv('REQUIRE_INVITE', raising=False)
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    source = tmp_path / 'browser-recording.webm'
    make_streaming_webm(source, with_video)
    original_frame = first_video_frame(source)[1] if with_video else None
    app = create_app(tmp_path / 'private', start_worker=False)

    with TestClient(app) as client:
        registration = client.post('/api/auth/register', json={
            'email': 'media-fixture@example.test', 'name': 'Media fixture',
            'password': 'SyntheticMediaPassword123', 'role': 'other', 'consent': True,
        })
        assert registration.status_code == 200
        headers = {'X-CSRF-Token': registration.json()['csrf_token']}
        practice = client.post('/api/practices', headers=headers, json={
            'scenario': 'speech', 'topic': 'Media fixture', 'duration': 1,
            'questions': False, 'criteria': '',
        })
        assert practice.status_code == 200
        uploaded = client.post(f"/api/practices/{practice.json()['id']}/segments", headers=headers,
                               data={'kind': 'speech', 'index': 0},
                               files={'file': ('recording.webm', source.read_bytes(),
                                               'video/webm' if with_video else 'audio/webm')})
        assert uploaded.status_code == 200, uploaded.text
        segment = uploaded.json()
        assert segment['has_video'] is with_video
        media = client.get(segment['media_url'])
        assert media.status_code == 200
        row = app.state.store.one('SELECT filename FROM segments WHERE id=?', (segment['id'],))
        saved = app.state.store.media / row['filename']
        assert media.content == saved.read_bytes()
        assert saved.stat().st_mode & 0o777 == 0o600
        assert not list(app.state.store.media.glob('*.finalizing.webm'))
        # Both file variants retain a real, decodable audio track after finalization.
        assert asyncio.run(probe_media(saved))['duration_seconds'] == pytest.approx(1, abs=0.03)
        if with_video:
            metadata, copied_frame = first_video_frame(saved)
            assert metadata['size'] == (320, 180)
            assert metadata['duration'] > 0
            assert copied_frame == original_frame
        else:
            video_probe = subprocess.run(
                [_ffmpeg(), '-nostdin', '-v', 'error', '-i', str(saved),
                 '-map', '0:v:0', '-frames:v', '1', '-f', 'null', '-'],
                capture_output=True, timeout=15,
            )
            assert video_probe.returncode != 0
