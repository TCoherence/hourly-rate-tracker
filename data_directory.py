"""Choose a local data directory and explicitly migrate the legacy default.

The marker makes an interrupted migration fail closed. No SQLite file is
copied or opened; migration operates only while both application locks are held.
"""
import argparse
import ctypes
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import stat
import sys
import time

from instance import AlreadyRunning, InstanceLock

MARKER_CONTENT = b'hourly-rate-directory-migration-v1\n'


class DirectoryError(RuntimeError):
    pass


def default_paths(home=None):
    base = Path(home or Path.home()) / 'Library' / 'Application Support'
    return base / 'HourlyRateMVP', base / 'HourlyRate', base / '.hourly-rate-directory-migration'


def _exists(path):
    return os.path.lexists(path)


def _valid_alias(old, new):
    return old.is_symlink() and new.is_dir() and not new.is_symlink() and old.resolve() == new.resolve()


def _check_marker(marker):
    if _exists(marker):
        raise DirectoryError('数据目录迁移未完成；请停止服务并运行 python3 data_directory.py --recover。')



def _default_choice(directory, old, new):
    if directory is None:
        return None
    chosen = Path(os.path.abspath(os.path.expanduser(str(directory))))
    old, new = Path(os.path.abspath(old)), Path(os.path.abspath(new))
    if chosen in (old, new):
        return chosen
    # An explicit symlink to either default is also protected by the guard.
    resolved = chosen.resolve()
    for candidate in (new, old):
        # resolve(strict=False) also detects aliases during the interval when
        # the old name has been renamed but its compatibility link is absent.
        if resolved == candidate.resolve():
            return candidate
    return chosen


def resolve_data_directory(directory=None, *, home=None):
    """Use the legacy directory until explicitly migrated; never create a split."""
    old, new, marker = default_paths(home)
    chosen = _default_choice(directory, old, new)
    old, new = Path(os.path.abspath(old)), Path(os.path.abspath(new))
    # A suspended migration blocks all startups, including custom paths: an
    # apparent custom path could be a changed or temporarily dangling alias.
    _check_marker(marker)
    if chosen is not None and chosen not in (old, new):
        return chosen.resolve()
    old_exists, new_exists = _exists(old), _exists(new)
    if old_exists and new_exists:
        if not _valid_alias(old, new):
            raise DirectoryError('旧数据目录和新数据目录同时存在，已停止以免记录分叉；请先检查两者。')
        return new.resolve()
    if old.is_symlink() or new.is_symlink():
        raise DirectoryError('默认数据目录存在无法确认的符号链接，已停止以保护记录。')
    if old_exists and not old.is_dir() or new_exists and not new.is_dir():
        raise DirectoryError('默认数据路径不是目录，已停止以保护记录。')
    if chosen == new and old_exists:
        raise DirectoryError('旧数据目录尚未迁移；请先使用旧目录或运行迁移。')
    if chosen == old and new_exists:
        raise DirectoryError('新数据目录已存在但旧路径缺失；请检查目录以免记录分叉。')
    return (old if old_exists else new if chosen is None else chosen).resolve()



@contextmanager
def locked_data_directory(directory=None, *, name='instance.lock', timeout=0, home=None):
    """Guard resolution and lock acquisition; never wait for a lock inside the guard."""
    old, new, _ = default_paths(home)
    deadline = time.monotonic() + timeout
    while True:
        # Classify every path while holding the stable guard: a caller-supplied
        # symlink can change targets between classification and lock acquisition.
        with InstanceLock(old.parent, name='.hourly-rate-default.lock', timeout=20):
            selected = resolve_data_directory(directory, home=home)
            lock = InstanceLock(selected, name=name, timeout=0)
            try:
                lock.__enter__()
            except AlreadyRunning:
                lock = None
        if lock is not None:
            break
        if time.monotonic() >= deadline:
            raise AlreadyRunning('数据目录已有服务正在运行或启动。')
        time.sleep(0.05)
    try:
        yield lock
    finally:
        lock.__exit__(None, None, None)


def _sync_directory(directory):
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _rename_exclusive(source, destination):
    """Atomic no-replace rename; never overwrite an independently created dir."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        fn, args = libc.renamex_np, (os.fsencode(source), os.fsencode(destination), 0x4)
    elif sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
        fn, args = libc.renameat2, (-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    else:
        raise DirectoryError('当前系统不支持安全的目录迁移。')
    if fn(*args) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(source), str(destination))


def _write_marker(marker):
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(MARKER_CONTENT)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        # Leave a partial marker in place: recovery must not assume success.
        raise
    _sync_directory(marker.parent)


def _remove_marker(marker):
    marker.unlink()
    _sync_directory(marker.parent)


def _validate_marker(marker):
    try:
        info = marker.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or marker.read_bytes() != MARKER_CONTENT:
            raise DirectoryError('迁移标记无法安全验证，请手动检查数据目录。')
    except OSError as error:
        raise DirectoryError('迁移标记无法读取，请手动检查数据目录。') from error


def _migrate_default_directory(*, home=None):
    """Move a stopped legacy directory and preserve old paths as an alias."""
    old, new, marker = default_paths(home)
    _check_marker(marker)
    if _valid_alias(old, new):
        return 'already-migrated'
    if _exists(new):
        raise DirectoryError('新数据目录已存在；不会覆盖或合并。')
    if not old.is_dir() or old.is_symlink():
        raise DirectoryError('旧数据目录不存在或不是普通目录；没有进行迁移。')
    try:
        # launcher -> instance matches launcher startup ordering. Both are
        # nonblocking: a running or starting collector must never be moved.
        with InstanceLock(old, name='launcher.lock'), InstanceLock(old):
            if _exists(new):
                raise DirectoryError('新数据目录已存在；不会覆盖或合并。')
            _write_marker(marker)
            try:
                _rename_exclusive(old, new)
                _sync_directory(new.parent)
                os.symlink(new.name, old, target_is_directory=True)
                _sync_directory(old.parent)
            except BaseException:
                # Marker stays in place; --recover handles all disk states,
                # including interruption between individual operations.
                raise
            _remove_marker(marker)
    except AlreadyRunning:
        raise DirectoryError('服务正在运行或启动；请先停止服务，再迁移数据目录。') from None
    return 'migrated'


def _recover_default_directory(*, home=None):
    """Finish an interrupted migration only when the disk state is unambiguous."""
    old, new, marker = default_paths(home)
    if not _exists(marker):
        raise DirectoryError('没有发现待恢复的迁移。')
    _validate_marker(marker)
    if old.is_symlink():
        if not _valid_alias(old, new):
            raise DirectoryError('迁移路径存在未知链接，请手动检查，未修改数据。')
        lock_dir = new
        state = 'completed'
    elif old.is_dir() and not _exists(new):
        lock_dir = old
        state = 'not-started'
    elif not _exists(old) and new.is_dir() and not new.is_symlink():
        lock_dir = new
        state = 'needs-alias'
    else:
        raise DirectoryError('旧目录与新目录状态有冲突，请手动检查，未修改数据。')
    try:
        with InstanceLock(lock_dir, name='launcher.lock'), InstanceLock(lock_dir):
            # Recheck all paths once locks are held to reject concurrent changes.
            if state == 'completed':
                if not _valid_alias(old, new):
                    raise DirectoryError('迁移路径已变化，请重试。')
            elif state == 'not-started':
                if not old.is_dir() or old.is_symlink() or _exists(new):
                    raise DirectoryError('迁移路径已变化，请重试。')
            else:
                if _exists(old) or not new.is_dir() or new.is_symlink():
                    raise DirectoryError('迁移路径已变化，请重试。')
                os.symlink(new.name, old, target_is_directory=True)
                _sync_directory(old.parent)
            _remove_marker(marker)
    except AlreadyRunning:
        raise DirectoryError('服务正在运行或启动；请先停止服务，再恢复迁移。') from None
    return state



def migrate_default_directory(*, home=None):
    old, _, _ = default_paths(home)
    try:
        with InstanceLock(old.parent, name='.hourly-rate-default.lock', timeout=20):
            return _migrate_default_directory(home=home)
    except AlreadyRunning:
        raise DirectoryError('另一项数据目录操作尚未完成，请稍后重试。') from None


def recover_default_directory(*, home=None):
    old, _, _ = default_paths(home)
    try:
        with InstanceLock(old.parent, name='.hourly-rate-default.lock', timeout=20):
            return _recover_default_directory(home=home)
    except AlreadyRunning:
        raise DirectoryError('另一项数据目录操作尚未完成，请稍后重试。') from None


def main():
    parser = argparse.ArgumentParser(description='选择或迁移本机数据目录')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--print', action='store_true', dest='print_path')
    group.add_argument('--migrate', action='store_true')
    group.add_argument('--recover', action='store_true')
    args = parser.parse_args()
    try:
        if args.print_path:
            print(resolve_data_directory())
        elif args.migrate:
            print(migrate_default_directory())
        else:
            print(recover_default_directory())
    except (DirectoryError, OSError) as error:
        raise SystemExit(str(error)) from None


if __name__ == '__main__':
    main()
