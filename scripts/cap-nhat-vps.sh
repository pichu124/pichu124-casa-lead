#!/usr/bin/env bash
# Cập nhật Chăm sóc lead trên VPS bằng một lệnh (user casa).
#
# Làm một lần: chép ra ngoài kho mã (git pull mà sửa đúng tệp đang chạy thì bash đọc hỏng):
#   cp /opt/casa-lead/scripts/cap-nhat-vps.sh ~/cap-nhat-lead.sh && chmod +x ~/cap-nhat-lead.sh
# Từ đó mỗi lần: ~/cap-nhat-lead.sh
#
# Thứ tự: ghi bản đang chạy -> sao lưu -> git pull -> cài thư viện nếu requirements đổi -> check.sh
# -> khởi động lại -> kiểm dịch vụ và /healthz. Bước nào lỗi là dừng ngay: app vẫn chạy bản cũ
# (trừ khi đã tới bước khởi động lại). Quay lui: git checkout <mã "Bản đang chạy"> rồi khởi động lại.
set -euo pipefail

MA_NGUON="${MA_NGUON:-/opt/casa-lead}"
DU_LIEU="${DU_LIEU:-/var/lib/casa-lead}"
TEN_MIEN="${TEN_MIEN:-casa-lead.duckdns.org}"

cd "$MA_NGUON"
CU="$(git rev-parse HEAD)"
echo "▶ Bản đang chạy: $(git log --oneline -1)"

echo "▶ Sao lưu"
CASA_LEAD_DATA="$DU_LIEU" .venv/bin/python scripts/sao_luu.py

echo "▶ Lấy bản mới"
git pull --ff-only
if [ "$(git rev-parse HEAD)" = "$CU" ]; then
  echo "✔ Đã là bản mới nhất, không cần khởi động lại."
  exit 0
fi
if git diff --name-only "$CU" HEAD | grep -q '^requirements'; then
  echo "▶ Cài thư viện (requirements đổi)"
  .venv/bin/pip install -q -r requirements-dev.txt
fi

echo "▶ Kiểm tra (check.sh)"
if ! ./scripts/check.sh; then
  echo "✘ Kiểm tra ĐỎ: KHÔNG khởi động lại, app vẫn chạy bản cũ trong bộ nhớ."
  echo "  Quay mã về bản cũ: git checkout $CU   (rồi báo người viết phần mềm)"
  exit 1
fi

echo "▶ Khởi động lại"
sudo systemctl restart casa-lead
sleep 3
systemctl is-active casa-lead
curl -sI "https://${TEN_MIEN}/healthz" | head -1
if ! cmp -s scripts/cap-nhat-vps.sh "$0" 2>/dev/null; then
  echo "ℹ Lệnh tắt có bản mới: cp $MA_NGUON/scripts/cap-nhat-vps.sh ~/cap-nhat-lead.sh"
fi
echo "✔ Bản mới: $(git log --oneline -1)"
