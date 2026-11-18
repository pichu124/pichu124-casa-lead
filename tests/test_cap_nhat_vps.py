"""Lệnh tắt cập nhật VPS (scripts/cap-nhat-vps.sh): đúng cú pháp bash, đủ các chốt chặn (sao lưu trước, check.sh
trước khi khởi động lại, dừng khi lỗi)."""

import subprocess
from pathlib import Path

TEP = Path(__file__).resolve().parent.parent / "scripts" / "cap-nhat-vps.sh"


def test_cu_phap_bash():
    assert subprocess.run(["bash", "-n", str(TEP)], capture_output=True).returncode == 0


def test_thu_tu_cac_buoc():
    s = TEP.read_text()
    assert "set -euo pipefail" in s
    vi_tri = [s.index(x) for x in ("scripts/sao_luu.py", "git pull --ff-only", "./scripts/check.sh",
                                    "sudo systemctl restart casa-lead")]
    assert vi_tri == sorted(vi_tri)  # sao lưu -> pull -> kiểm -> khởi động lại
