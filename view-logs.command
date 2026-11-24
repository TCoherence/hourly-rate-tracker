#!/bin/zsh
cd "${0:A:h}" || exit 1
hourly_python=''
for hourly_candidate in /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 python3.12 python3 python3.14 python3.13 python3.11 python3.10; do
  if "$hourly_candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    hourly_python="$hourly_candidate"
    break
  fi
done
if [[ -z "$hourly_python" ]]; then
  print '需要 Python 3.10 或更高版本。请先安装，再打开此文件。'
  read -r '?按回车关闭。'
  exit 1
fi
hourly_dir=$("$hourly_python" data_directory.py --print)
if [[ $? -ne 0 ]]; then
  print '无法确定数据目录；请先检查目录迁移状态。'
  read -r '?按回车关闭。'
  exit 1
fi
hourly_logs=("$hourly_dir/service.log" "$hourly_dir/autostart-service.log")
if [[ ! -f "${hourly_logs[1]}" && ! -f "${hourly_logs[2]}" ]]; then
  print '日志尚未生成。请先运行 start-hourly-rate.command，再打开此文件。'
  read -r '?按回车关闭。'
  exit 1
fi
print '正在查看本机日志。采集首次检测或状态变化时会打印。'
print '按 Control+C 结束日志查看，不会停止计时或改变 VPN 连接。'
hourly_existing=()
for hourly_log in "${hourly_logs[@]}"; do
  [[ -f "$hourly_log" ]] && hourly_existing+=("$hourly_log")
done
tail -n 30 -F "${hourly_existing[@]}"
