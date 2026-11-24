"""Read-only VPN adapters. Never read traffic, credentials, routes or window content."""
from __future__ import annotations

import os
import re
import selectors
import subprocess
import sys
import time
from pathlib import Path
from legacy_compat import adapter_environment

UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")
COMMAND_TIMEOUT_SECONDS = 5
LOCAL_STATUS_SCRIPT = str(Path(__file__).resolve().parent / "local-adapters" / "status")
CISCO_PATHS = (
    "/opt/cisco/secureclient/bin/vpn",
    "/opt/cisco/anyconnect/bin/vpn",
)


def _command_environment(directory=None):
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C"}
    env.update(adapter_environment(directory, os.environ))
    return env


def command(args):
    """No shell and no raw command output in logs or persistent storage."""
    result = subprocess.run(args, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS,
                            env=_command_environment())
    if result.returncode:
        raise RuntimeError("VPN status unavailable")
    return result.stdout


def script_command(args, directory=None):
    """Read at most 1 KiB from a local script, with a single overall timeout."""
    deadline = time.monotonic() + COMMAND_TIMEOUT_SECONDS
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            env=_command_environment(directory))
    try:
        data = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise subprocess.TimeoutExpired(args, COMMAND_TIMEOUT_SECONDS)
                chunk = os.read(proc.stdout.fileno(), 1025 - len(data))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > 1024:
                    raise ValueError("状态脚本输出过长")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(args, COMMAND_TIMEOUT_SECONDS)
        if proc.wait(timeout=remaining):
            raise RuntimeError("状态脚本不可用")
        return data.decode("ascii")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        proc.stdout.close()


def parse_system_status(output):
    first = output.strip().splitlines()[0].strip() if output.strip() else ""
    return {"Connected": "connected", "Disconnected": "disconnected"}.get(first, "unknown")


def parse_cisco_status(output):
    states = re.findall(r"\bstate:\s*([^\r\n]+)", output, re.I)
    if not states:
        return "unknown"
    return {"connected": "connected", "disconnected": "disconnected"}.get(states[-1].strip().lower(), "unknown")


def validate_status_script(path):
    if not os.path.isabs(path) or "\x00" in path:
        raise ValueError("状态脚本路径须为绝对路径")
    return path


def detect(settings, runner=command, compatibility_dir=None):
    if not settings.get("tracking_enabled"):
        return "disabled", "采集尚未开启"
    if sys.platform != "darwin":
        return "unknown", "真实 VPN 采集仅支持 macOS"
    try:
        if settings["provider"] == "script":
            path = validate_status_script(settings.get("status_script_path", ""))
            output = script_command([path], compatibility_dir) if runner is command else runner([path])
            # A single token and at most one conventional line ending; never log output.
            if not re.fullmatch(r"(?:connected|disconnected|unknown)\n?", output):
                state = "unknown"
            else:
                state = output.removesuffix("\n")
        elif settings["provider"] in ("system", "verified_system"):
            service_id = settings.get("service_id", "")
            if not UUID.fullmatch(service_id):
                return "unknown", "请先选择系统中可识别的公司 VPN"
            state = parse_system_status(runner(["/usr/sbin/scutil", "--nc", "status", service_id]))
        elif settings["provider"] == "cisco":
            executable = next((p for p in CISCO_PATHS if os.path.isfile(p) and os.access(p, os.X_OK)), None)
            if not executable:
                return "unknown", "未找到 Cisco 客户端；未计入工作或休息时间"
            state = parse_cisco_status(runner([executable, "state"]))
        else:
            return "unknown", "尚未选择支持的 VPN 类型"
    except (OSError, subprocess.SubprocessError, RuntimeError, UnicodeError, ValueError, TypeError):
        return "unknown", "无法读取 VPN 状态；此时段标为未知"
    return state, {"connected": "公司 VPN 已连接", "disconnected": "公司 VPN 已断开",
                   "unknown": "连接中、重连中或状态不可识别；此时段标为未知"}[state]


def discover(runner=command):
    """Called only when the user explicitly requests local VPN discovery."""
    services = []
    if sys.platform == "darwin":
        try:
            output = runner(["/usr/sbin/scutil", "--nc", "list"])
            for line in output.splitlines():
                match = re.search(r'([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})\s+.*?"([^"]+)"', line)
                if match:
                    services.append({"id": match.group(1), "name": match.group(2)[:120]})
        except (OSError, subprocess.SubprocessError, RuntimeError, UnicodeError):
            pass
    return {"services": services, "cisco_available": any(os.path.isfile(p) for p in CISCO_PATHS),
            "notice": "仅查询本机 VPN 服务名称与状态，不改变连接。部分企业客户端不会出现在系统列表中。"}
