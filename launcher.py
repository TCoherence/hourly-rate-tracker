#!/usr/bin/env python3
"""Start or stop one local service; never install a login item."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser

from instance import AlreadyRunning, InstanceLock, is_locked

ROOT = Path(__file__).resolve().parent
DATA = Path.home() / "Library" / "Application Support" / "HourlyRateMVP"
# Ignore system proxy settings so even readiness checks stay on this Mac.
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def running(directory=DATA):
    """Return credentials only after the listening service has validated them."""
    try:
        access = json.loads((Path(directory) / "access.json").read_text())
        port = access["port"]
        token = access["session_token"]
        pair_token = access.get("pair_token", "")
        if type(port) is not int or not 0 < port < 65536 or not isinstance(token, str) or not token:
            return None
        url = f"http://127.0.0.1:{port}"
        with LOCAL.open(url + "/api/health", timeout=1) as response:
            health = json.load(response)
            if not isinstance(health, dict) or health.get("app") != "hourly-rate-local":
                return None
        request = urllib.request.Request(url + "/api/session", headers={"X-Session-Token": token})
        with LOCAL.open(request, timeout=1) as response:
            csrf = json.load(response)["csrf_token"]
        if not isinstance(csrf, str) or not csrf:
            return None
        if not isinstance(pair_token, str):
            return None
        return {"url": url, "session_token": token, "csrf_token": csrf, "pair_token": pair_token}
    except (OSError, ValueError, TypeError, KeyError):
        return None


def stop(directory=DATA):
    access = running(directory)
    if access is None:
        if is_locked(directory):
            raise SystemExit("本机服务尚未就绪或访问凭据不可用；请稍后重试 stop-hourly-rate.command。")
        print("本机采集工具没有运行。")
        return
    request = urllib.request.Request(access["url"] + "/api/stop", data=b"{}", method="POST",
        headers={"Content-Type": "application/json", "X-CSRF-Token": access["csrf_token"],
                 "X-Session-Token": access["session_token"], "Origin": access["url"]})
    try:
        with LOCAL.open(request, timeout=5):
            pass
    except OSError:
        raise SystemExit("停止请求未成功，请稍后重试 stop-hourly-rate.command。") from None
    for _ in range(150):
        if not is_locked(directory):
            print("已停止本机后台记录。已有数据保留在本机。")
            return
        time.sleep(0.1)
    raise SystemExit("服务仍在完成停止操作，请稍后重试；已有记录保留在本机。")


def start(directory, port):
    access = running(directory)
    if access is not None:
        return access
    process = None
    for _ in range(100):
        access = running(directory)
        if access is not None:
            return access
        locked = is_locked(directory)
        # A manual start/stop may still hold the lock. Wait for readiness or
        # for its exit, then launch only after the previous owner has left.
        if process is None and not locked:
            log_path = Path(directory) / "service.log"
            with log_path.open("ab") as log:
                log_path.chmod(0o600)
                process = subprocess.Popen([sys.executable, str(ROOT / "app.py"), "--data-dir", str(directory), "--port", str(port)],
                    cwd=str(ROOT), stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
        elif process is not None and process.poll() is not None and not locked:
            raise SystemExit("本机服务未启动，请检查端口是否被占用或查看本机 service.log。")
        time.sleep(0.1)
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Keep its lock and data intact; do not force-kill a writing process.
            raise SystemExit("服务启动超时，已请求停止；请稍后查看 service.log。") from None
    raise SystemExit("本机服务尚未就绪或访问凭据不可用，请查看本机 service.log。")


def open_browser(access, browser_app=None):
    """Open the private, one-use entry in the chosen macOS app without a shell."""
    pair = "&pair=" + access["pair_token"] if access.get("pair_token") else ""
    url = access["url"] + "/#access=" + access["session_token"] + pair
    if browser_app:
        if sys.platform != "darwin":
            raise SystemExit("指定浏览器应用目前仅支持 macOS。")
        try:
            result = subprocess.run(["/usr/bin/open", "-a", browser_app, url],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    check=False, timeout=15)
        except (OSError, subprocess.SubprocessError):
            raise SystemExit("未能打开指定浏览器，请检查应用名称。") from None
        if result.returncode:
            raise SystemExit("未能打开指定浏览器，请检查应用名称。")
    elif not webbrowser.open(url):
        raise SystemExit("未能打开默认浏览器，请检查系统浏览器设置。")


def main():
    parser = argparse.ArgumentParser(description="打开或停止本机时薪工具")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="启动服务，但不打开浏览器")
    parser.add_argument("--browser-app", metavar="APP", help="在指定 macOS 浏览器应用中打开本机入口")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("invalid port")
    if args.browser_app is not None and (not args.browser_app.strip() or args.no_browser or args.stop):
        parser.error("--browser-app 需指定应用名称，且不能与 --no-browser 或 --stop 同用")
    os.umask(0o077)
    directory = args.data_dir.expanduser().resolve()
    try:
        # Serialize launcher starts/stops so concurrent double-clicks reuse the
        # first service instead of launching competing child processes.
        with InstanceLock(directory, name="launcher.lock", timeout=20):
            if args.stop:
                return stop(directory)
            access = start(directory, args.port)
    except AlreadyRunning:
        raise SystemExit("另一次启动或停止仍在进行，请稍后重试。") from None
    if not args.no_browser:
        open_browser(access, args.browser_app)
    print("本机仪表盘已就绪；关闭浏览器后仍会记录。用 stop-hourly-rate.command 结束后台运行。")


if __name__ == "__main__":
    main()
