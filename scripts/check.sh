#!/usr/bin/env bash
# Kiểm tra trước khi báo xong hay commit: cú pháp, không có dữ liệu thật trong kho, toàn bộ kiểm thử.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
echo "== Cú pháp"
$PY -m compileall -q app scripts tests
echo "== Không có dữ liệu thật trong kho"
if git ls-files 2>/dev/null | grep -E '\.(db|sqlite[0-9]*)$|(^|/)data/|(^|/)backups/|\.env$|khoa-phien\.txt$'; then
  echo "Có tệp dữ liệu hoặc bí mật trong kho mã: gỡ ra trước khi commit." >&2
  exit 1
fi
echo "== Kiểm thử"
$PY -m pytest -q
echo "check.sh XANH"
