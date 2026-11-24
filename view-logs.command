#!/bin/zsh
hourly_dir="$HOME/Library/Application Support/HourlyRateMVP"
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
