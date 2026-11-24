"""Process locks for a local data directory; never unlink a lock file."""
import errno
import fcntl
import os
from pathlib import Path
import time


class AlreadyRunning(RuntimeError):
    pass


class InstanceLock:
    def __init__(self, directory, name="instance.lock", timeout=0):
        self.directory = Path(directory).expanduser().resolve()
        self.name = name
        self.timeout = timeout
        self.fd = None

    def __enter__(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.directory / self.name, os.O_CREAT | os.O_RDWR, 0o600)
        deadline = time.monotonic() + self.timeout
        try:
            os.fchmod(fd, 0o600)
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.fd = fd
                    return self
                except OSError as error:
                    if error.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
                    if time.monotonic() >= deadline:
                        raise AlreadyRunning("此数据目录已有服务正在运行或启动。") from None
                    time.sleep(0.05)
        except BaseException:
            os.close(fd)
            raise

    def __exit__(self, *_):
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)
                self.fd = None


def is_locked(directory):
    try:
        with InstanceLock(directory):
            return False
    except AlreadyRunning:
        return True
