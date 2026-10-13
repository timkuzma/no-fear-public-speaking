"""One application instance; shared runtime access and exclusive offline operations."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path


@contextmanager
def _lock(directory, filename, shared):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / filename, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Data is in use by another application or offline operation') from None
        yield
    finally:
        os.close(fd)


@contextmanager
def data_lock(directory, shared=False):
    with _lock(directory, '.application.lock', shared):
        yield


@contextmanager
def instance_lock(directory):
    with _lock(directory, '.instance.lock', False):
        yield
