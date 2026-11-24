#!/bin/zsh
cd "${0:A:h}" || exit 1
for hourly_python in /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 python3.12 python3 python3.14 python3.13 python3.11 python3.10; do
  if "$hourly_python" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    "$hourly_python" launcher.py --stop "$@"
    hourly_status=$?
    if [ $hourly_status -ne 0 ]; then read -r '?按回车关闭。'; fi
    exit $hourly_status
  fi
done
print '需要 Python 3.10 或更高版本。请先安装，再打开此文件。'
read -r '?按回车关闭。'
exit 1
