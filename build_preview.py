"""Generate a self-contained, read-only demo. No user data or network access."""
import json
from pathlib import Path
import tempfile

from app import Application
from scripts.build_frontend import TARGET as BROWSER_BUNDLE, expected_bundle

ROOT = Path(__file__).resolve().parent


def build():
    if not BROWSER_BUNDLE.exists() or BROWSER_BUNDLE.read_text(encoding="utf-8") != expected_bundle():
        raise SystemExit("Browser bundle is stale; run python3 scripts/build_frontend.py")
    with tempfile.TemporaryDirectory(prefix="hourly-demo-build-") as tmp:
        application = Application(tmp)
        try:
            # Keep the distributed synthetic preview independent of the
            # machine's local timezone and any personal settings.
            application.store.save_settings({"timezone": "UTC"})
            snapshots = {}
            for period in ("today", "week", "month", "quarter", "half", "year", "rolling_year"):
                data = application.dashboard(period, demo=True)
                data["privacy"]["storage_path"] = "独立离线演示：本文件不保存、不采集任何真实数据"
                data["csrf_token"] = "offline-demo"
                data["collector"] = {"state": "disabled", "message": "独立离线演示，不读取 VPN，不保存设置",
                    "last_checked_at": None, "last_synced_at": None, "next_sync_at": None, "pending_count": 0}
                snapshots[period] = data
        finally:
            application.close()
    payload = json.dumps(snapshots, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    bridge = """
const demoSnapshots = SNAPSHOTS;
window.fetch = async function(url, options) {
  const q = new URL(url, 'http://127.0.0.1');
  if ((!options || !options.method || options.method === 'GET') && q.pathname === '/api/dashboard') {
    const value = demoSnapshots[q.searchParams.get('period') || 'week'];
    return {ok:true,status:200,json:async()=>value};
  }
  return {ok:false,status:405,json:async()=>({error:'这是只读离线演示，请启动本机应用后配置。'})};
};
""".replace("SNAPSHOTS", payload)
    script = (ROOT / "static" / "app.js").read_text()
    script = script.replace('let sessionToken = hash.get("access") || "";', 'let sessionToken = "offline-demo";')
    script = script.replace('if (sessionToken) sessionStorage.setItem("hourly-access", sessionToken);', 'if (sessionToken) { /* Offline demo has no persistent session. */ }')
    script = script.replace('let mode = query.get("demo") === "1" ? "demo" : "live";', 'let mode = "demo";')
    script = script.replace('history.replaceState(null, "", "?" + params.toString());', '/* Read-only file preview does not change browser history. */')
    lock = """
document.querySelector('[data-mode="live"]').disabled = true;
document.getElementById('open-settings').disabled = true;
document.getElementById('open-settings').title = '离线演示不保存设置；请打开start-hourly-rate.command';
document.getElementById('open-manual').disabled = true;
document.getElementById('open-manual').title = '离线演示不能补录真实工时';
"""
    html = (ROOT / "static" / "index.html").read_text()
    html = html.replace('<link rel="stylesheet" href="/style.css">', '<style>' + (ROOT / "static" / "style.css").read_text() + '</style>')
    html = html.replace('<link rel="stylesheet" href="/manual.css">', '<style>' + (ROOT / "static" / "manual.css").read_text() + '</style>')
    html = html.replace('<link rel="stylesheet" href="/timeline.css">', '<style>' + (ROOT / "static" / "timeline.css").read_text() + '</style>')
    html = html.replace('  <script src="/app.js" defer></script>\n', '')
    html = html.replace('<script src="/history-calendar.js" defer></script>', '<script>' + (ROOT / "static" / "history-calendar.js").read_text() + '</script>')
    html = html.replace('  <script src="/manual.js" defer></script>\n', '')
    html = html.replace('<script src="/theme.js"></script>', '<script>' + (ROOT / "static" / "theme.js").read_text() + '</script>')
    html = html.replace('href="/logs.html"', 'href="#" aria-disabled="true" title="实时日志仅在本机应用中可用"')
    html = html.replace('<title>工作占用 · 时薪仪表盘</title>', '<title>工作占用 · 离线演示（模拟数据）</title>')
    html = html.replace('href="/" aria-label="工作占用首页"', 'href="#" aria-label="工作占用首页"')
    html = html.replace('</body>', '<script>' + bridge + '\n' + script + '\n' + lock + '</script></body>')
    destination = ROOT / "preview.html"
    destination.write_text(html, encoding="utf-8")
    print(f"Built synthetic-only preview: {destination.name} ({destination.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
