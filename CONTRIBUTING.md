# 参与贡献

欢迎提出问题、修正文档或改进这个小工具。项目还在打磨中，涉及新的记录来源、计时规则或数据导出的较大改动，建议先描述使用场景和预期行为，再开始实现。

## 本地开发

项目主要面向 macOS，运行需要 Python 3.10 或更新版本，运行时只使用标准库。前端测试需要 Node.js。

```sh
python3 launcher.py
python3 -m unittest discover -s tests -v
node --test tests/*.cjs
```

修改 `static/i18n.js`、`static/dashboard-translations.js`、`static/draft-undo.js` 或 `static/history-calendar-core.js` 后，运行 `python3 scripts/build_frontend.py` 重新生成浏览器兼容包；测试会检查生成结果是否与源码一致。这个入口兼容尚未重启的旧版本服务。

独立的 `preview.html` 只展示模拟数据；修改页面后可用 `python3 build_preview.py` 重新生成。更完整的运行、计算与数据说明见[使用指南](docs/USER_GUIDE.md)。

## 数据与测试

- 测试和演示使用虚构数据、临时目录与模拟状态来源；不要提交或分享实际数据库、薪资、工时、日志、授权凭据、导出文件或个人状态脚本。
- 自动测试不能改变真实 VPN 的连接状态。新增状态来源时，无法确认连接的情况应保留为“未知”，不能猜作已断开或已连接。
- 修改历史记录、薪资计算、睡眠或暂停规则时，请说明对已有数据的影响，并验证旧数据仍可读取；原始状态采样应可追溯。
- 截图和录屏也请使用模拟数据，确认没有个人信息、组织信息或其他非公开内容。

有意提交内容即表示你有权按项目的 [MIT 许可证](LICENSE)提供该贡献。请先检查适用于你和所用设备的规定；不要分享无权公开的材料。
