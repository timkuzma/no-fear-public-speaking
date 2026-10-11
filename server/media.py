"""Lossless finalization of browser streaming WebM for finite, seekable playback."""
import asyncio
from contextlib import suppress
import os
import shutil
from pathlib import Path

from .ai import ProviderError


async def finalize_webm(path: Path):
    if path.suffix != '.webm':
        return
    import imageio_ffmpeg
    binary = os.getenv('FFMPEG_BINARY') or shutil.which('ffmpeg') or imageio_ffmpeg.get_ffmpeg_exe()
    target = path.with_name(path.stem + '.finalizing.webm')
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            binary, '-nostdin', '-v', 'error', '-protocol_whitelist', 'file,pipe',
            '-format_whitelist', 'matroska,webm', '-i', str(path.resolve()),
            '-map', '0:a:0', '-vn', '-t', '601', '-c:a', 'copy', '-y', str(target),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(process.wait(), timeout=45)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            raise
        if process.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
            raise ProviderError('MEDIA_INVALID', 'Не удалось подготовить запись для прослушивания. Попробуйте сохранить её ещё раз.')
        if target.stat().st_size > int(os.getenv('MAX_UPLOAD_BYTES', 32 * 1024 * 1024)) + 16384:
            raise ProviderError('MEDIA_TOO_LARGE', 'Файл слишком большой. Запишите более короткую тренировку.')
        os.chmod(target, 0o600)
        with target.open('rb') as recording:
            os.fsync(recording.fileno())
        target.replace(path)
    except (OSError, asyncio.TimeoutError):
        raise ProviderError('MEDIA_INVALID', 'Не удалось подготовить запись для прослушивания. Попробуйте сохранить её ещё раз.') from None
    finally:
        target.unlink(missing_ok=True)
