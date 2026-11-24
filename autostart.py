"""Per-user macOS login item; no shell, no launchd process detachment."""
from pathlib import Path
import os
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
import threading
from legacy_compat import adapter_environment

LABEL = "org.hourlyrate.local.collector"
ROOT = Path(__file__).resolve().parent
_LOCK = threading.RLock()


class AutostartError(Exception):
    pass


class LoginItem:
    def __init__(self, directory, port, *, home=None, root=None, executable=None,
                 runner=None, platform=None, environment=None, uid=None):
        self.directory = Path(directory).expanduser().resolve()
        self.port = int(port)
        self.home = Path(home or Path.home())
        self.root = Path(root or ROOT).resolve()
        self.executable = str(Path(executable or sys.executable).resolve())
        self.runner = runner or subprocess.run
        self.platform = platform or sys.platform
        self.environment = dict(os.environ if environment is None else environment)
        self.domain = f"gui/{os.getuid() if uid is None else uid}"
        self.path = self.home / "Library" / "LaunchAgents" / (LABEL + ".plist")

    def _call(self, *args):
        try:
            return self.runner(["/bin/launchctl", *args], capture_output=True, text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise AutostartError("无法读取或修改 macOS 登录项状态，请检查系统设置。") from error

    def _read(self):
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise AutostartError("登录项文件不是当前用户的普通文件，未修改。")
        try:
            with self.path.open("rb") as stream:
                job = plistlib.load(stream)
        except (OSError, ValueError, plistlib.InvalidFileException):
            raise AutostartError("登录项文件无法读取，未修改。") from None
        args = job.get("ProgramArguments") if isinstance(job, dict) else None
        if (not isinstance(job, dict) or job.get("Label") != LABEL or not isinstance(args, list)
                or len(args) != 6 or not all(isinstance(a, str) for a in args)
                or Path(args[1]).name != "app.py" or args[2] != "--data-dir" or args[4] != "--port"):
            raise AutostartError("已有同名登录项不属于本项目，未修改。")
        return job

    def _system_disabled(self):
        result = self._call("print-disabled", self.domain)
        if result.returncode or "{" not in (result.stdout or "") or "}" not in (result.stdout or ""):
            raise AutostartError("无法确认 macOS 登录项状态，请检查系统设置。")
        pattern = r'"?' + re.escape(LABEL) + r'"?\s*=>\s*(enabled|disabled)\b'
        match = re.search(pattern, result.stdout or "")
        return bool(match and match.group(1) == "disabled")

    def _matches(self, job):
        args = job["ProgramArguments"]
        return (args[0] == self.executable and args[1] == str(self.root / "app.py")
                # Legacy login items can retain a compatibility symlink to
                # the migrated directory; they still target the same data.
                and Path(args[3]).expanduser().resolve() == self.directory and args[5] == str(self.port)
                and job.get("RunAtLoad") is True and job.get("WorkingDirectory") == str(self.root)
                and not job.get("Disabled", False))

    def _target_available(self):
        script = self.root / "app.py"
        return script.is_file() and os.access(script, os.R_OK) and os.path.isfile(self.executable) and os.access(self.executable, os.X_OK)

    def status(self):
        if self.platform != "darwin":
            return {"supported": False, "enabled": None, "message": "登录后启动目前仅支持 macOS。"}
        try:
            with _LOCK:
                job = self._read()
                if job is None:
                    return {"supported": True, "enabled": False, "message": "未设置登录后启动。"}
                if not self._matches(job):
                    return {"supported": True, "enabled": False, "message": "已有登录项指向其他项目或数据目录；可重新开启以更新。"}
                if not self._target_available():
                    return {"supported": True, "enabled": False, "message": "登录项的程序路径不可用，请检查项目位置并重新设置。"}
                if self._system_disabled():
                    return {"supported": True, "enabled": False, "message": "登录项被 macOS 禁用，请在系统设置中检查。"}
                return {"supported": True, "enabled": True, "message": "已设置登录后启动，下次登录时生效。"}
        except (AutostartError, OSError) as error:
            return {"supported": True, "enabled": None, "message": str(error) if isinstance(error, AutostartError) else "无法读取本机登录项状态。"}

    def set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise AutostartError("请选择开启或关闭登录后启动。")
        if self.platform != "darwin":
            raise AutostartError("登录后启动目前仅支持 macOS。")
        with _LOCK:
            old = self._read()  # Never replace an unrelated file or symlink.
            if enabled:
                if not self._target_available():
                    raise AutostartError("登录启动程序不可用，请检查项目和 Python 路径。")
                was_disabled = self._system_disabled()
                self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                log = self.directory / "autostart-diagnostics.log"
                startup_log = self.directory / "autostart-startup.log"
                flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
                for path in (log, startup_log):
                    fd = os.open(path, flags, 0o600)
                    try:
                        os.fchmod(fd, 0o600)
                    finally:
                        os.close(fd)
                job = {"Label": LABEL,
                       "ProgramArguments": [self.executable, str(self.root / "app.py"), "--data-dir", str(self.directory), "--port", str(self.port)],
                       "WorkingDirectory": str(self.root), "RunAtLoad": True,
                       "StandardOutPath": str(startup_log), "StandardErrorPath": str(log), "Umask": 63}
                job["EnvironmentVariables"] = {"HOURLY_RATE_LOGIN_ITEM": "1"}
                try:
                    job["EnvironmentVariables"].update(adapter_environment(self.directory, self.environment, strict=True))
                except ValueError as error:
                    raise AutostartError(str(error)) from None
                fd, temporary = tempfile.mkstemp(prefix=".hourly-rate-", dir=self.path.parent)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        plistlib.dump(job, stream)
                    result = self._call("enable", self.domain + "/" + LABEL)
                    if result.returncode:
                        raise AutostartError("macOS 未能启用登录项，请检查系统设置。")
                    try:
                        os.replace(temporary, self.path)
                    except OSError as error:
                        if was_disabled:
                            try:
                                rollback = self._call("disable", self.domain + "/" + LABEL)
                            except AutostartError:
                                raise AutostartError("登录项写入失败，系统状态恢复失败；请检查系统设置。") from error
                            if rollback.returncode:
                                raise AutostartError("登录项写入失败，系统状态恢复失败；请检查系统设置。") from error
                        raise
                finally:
                    Path(temporary).unlink(missing_ok=True)
            elif old is not None:
                result = self._call("disable", self.domain + "/" + LABEL)
                if result.returncode:
                    raise AutostartError("macOS 未能关闭登录项，请检查系统设置。")
                self.path.unlink()
            return self.status()
