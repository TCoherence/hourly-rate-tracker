# Mac app 后续计划

当前继续使用脚本启动、浏览器查看。本文件准备后续实现范围，不代表已创建、打包或发布 Mac 应用。

## 第一版做什么

做一个菜单栏小应用，提供今日工时、当前 VPN 状态、暂停/恢复记录、打开仪表盘、退出。关闭仪表盘窗口不停止后台采集；明确选择退出才停止。登录时启动是用户自选项，不默认安装。

先保留 Python 计算和 SQLite 数据格式，不把计时规则重写一遍。菜单栏使用 SwiftUI `MenuBarExtra`；界面先复用现有仪表盘，后续用 `WKWebView` 内嵌。把 Python 运行环境和采集组件随应用打包，让使用者不必自行安装 Python。

## 现有代码如何复用

- `core.py`：工时、薪资、手动补录和睡眠规则的唯一计算来源。
- `store.py`：继续使用当前数据库；沿用 `~/Library/Application Support/HourlyRate`，不因换成应用而另建空数据库。
- `vpn.py`：保留只读检测接口；不同 VPN 可通过系统适配器或本机脚本扩展。
- `power.py`：初版继续接收系统睡眠/唤醒事件；若未来换成原生监听，需替换现有监听，避免双重记录。
- `launcher.py`、`instance.py`：复用单实例控制与本机服务复用，菜单栏应用和脚本同时打开也不能启动两份采集。
- `static/`：继续作为仪表盘。应用负责把当前会话交给自己的页面，用户不用手动复制认证地址；不关闭现有认证保护。

## 分阶段验收

1. 稳定计时语义：实测合盖/唤醒、外接显示器时的合盖、长时间锁屏与 VPN 重连；把系统睡眠、熄屏、离开键鼠区分开。决定是否增加“锁屏暂停”或“结束今天”，不默认把键鼠空闲当休息。
2. 做菜单栏外壳：启动、复用已有服务、打开仪表盘、暂停、退出；后台异常能在菜单栏看见。
3. 打包运行环境并嵌入页面：在未安装 Python 的机器验证，测试应用路径含空格、重新打开和多次点击启动；保留原数据目录。
4. 自选登录启动与发布：验证登录启动、正常退出、升级和卸载后的数据保留，最后完成签名、公证与下载包。

## 开源准备

- 沿用已选择的 MIT 许可证；发布前确定公开署名和贡献方式，并补充面向新用户的安装说明。
- 用模拟数据制作演示和截图，不能提交个人数据库、薪资、访问凭据或真实工作记录。
- 明确定位为“本机工作占用与实际时薪”，VPN 连接是可替换的记录信号，不声称等同于工作专注程度。
- 先提供源码与脚本入口；面向普通用户的 `.app` 下载是另一项发布工作。
- 第一轮只聚焦 macOS。是否跨平台、进入 App Store、自动更新和额外数据导出，待核心体验稳定后决定。

## 官方参考

- [SwiftUI MenuBarExtra](https://developer.apple.com/documentation/swiftui/menubarextra)
- [WKWebView](https://developer.apple.com/documentation/webkit/wkwebview)
- [SMAppService](https://developer.apple.com/documentation/servicemanagement/smappservice)
- [Apple：商店外分发软件公证](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
