"""Kiểm tra sao lưu đêm qua (cron mỗi sáng 7:05) và báo Telegram khi thiếu, để không phải tự kiểm mỗi ngày.

    python -m app.kiem_tra_sao_luu          # kiểm và báo (nhóm quản lý; chưa nối nhóm thì chủ)
    python -m app.kiem_tra_sao_luu --thu    # chỉ in ra, không gửi

Mỗi nơi kiểm (casa-lead, CASA Mầm non) phải có tệp mang ngày hôm nay (YYYYMMDD trong tên) ở thư mục sao lưu trên VPS
và trên Drive (`rclone lsf <remote>`). Kiểm kết quả chứ không sửa lệnh sao lưu: bắt được cả cron không chạy, script
lỗi, rclone không đẩy lên được. Đủ thì im lặng. Danh sách nơi kiểm đổi bằng biến SAO_LUU_KIEM_TRA
("tên=thư mục=remote;…"). Tin không chứa dữ liệu phụ huynh.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

from . import db, dongho, telegram

log = logging.getLogger("casa_lead.kiem_tra_sao_luu")
MAMNON_MAC_DINH = "/var/lib/casa-mamnon/backups"


def cac_noi_kiem() -> list[tuple[str, Path, str]]:
    """(tên, thư mục sao lưu trên VPS, remote rclone) của từng app."""
    bien = (os.environ.get("SAO_LUU_KIEM_TRA") or "").strip()
    if bien:
        ds = []
        for phan in bien.split(";"):
            ten, thu_muc, remote = (x.strip() for x in phan.split("=", 2))
            ds.append((ten, Path(thu_muc), remote))
        return ds
    return [("casa-lead", db.duong_dan_db().parent / "backups", "mahoa:casa-lead"),
            ("casa-mamnon", Path(MAMNON_MAC_DINH), "mahoa:casa-mamnon")]


def _tren_drive(remote: str, ngay: str) -> bool | None:
    """Có tệp mang `ngay` trên remote không; None khi không đọc được Drive (rclone lỗi, không có rclone)."""
    try:
        r = subprocess.run(["rclone", "lsf", remote, "--files-only"], capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("Không chạy được rclone: %s", type(e).__name__)
        return None
    if r.returncode != 0:
        log.warning("rclone lsf %s lỗi (mã %s)", remote, r.returncode)
        return None
    return any(ngay in dong for dong in r.stdout.splitlines())


def kiem(hom_nay: date) -> list[str]:
    """Các vấn đề của bản sao lưu đêm qua ([] là đủ)."""
    ngay = hom_nay.strftime("%Y%m%d")
    loi = []
    for ten, thu_muc, remote in cac_noi_kiem():
        if not thu_muc.is_dir() or not any(ngay in t.name for t in thu_muc.iterdir()):
            loi.append(f"{ten}: không thấy bản sao lưu đêm qua trên VPS ({thu_muc})")
        tren = _tren_drive(remote, ngay)
        if tren is None:
            loi.append(f"{ten}: không đọc được Drive ({remote}): rclone lỗi hoặc mất quyền")
        elif not tren:
            loi.append(f"{ten}: chưa lên Drive ({remote})")
    return loi


def chay(conn: sqlite3.Connection, hom_nay: date, thu: bool = False) -> list[str]:
    loi = kiem(hom_nay)
    if not loi or thu:
        return loi
    tin = "\n".join([f"⚠ Sao lưu đêm qua ({hom_nay:%d/%m/%Y}) có vấn đề:", *[f"- {x}" for x in loi], "",
                     "Kiểm tra trên VPS (user casa): tail -20 /home/casa/sao-luu-lead.log, "
                     "tail -20 /home/casa/backup-casa.log, rclone listremotes."])
    nhan = telegram.nguoi_nhan_quan_ly(conn)
    if not nhan:
        log.warning("Sao lưu có vấn đề nhưng chưa có nơi nhận Telegram (chưa nối nhóm, chủ chưa nối)")
    for chat in nhan:
        if not telegram.gui_tin(chat, tin):
            log.warning("Không gửi được cảnh báo sao lưu vào Telegram")
    return loi


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(description="Kiểm tra sao lưu đêm qua, báo Telegram khi thiếu")
    p.add_argument("--thu", action="store_true", help="chỉ in ra, không gửi")
    a = p.parse_args(argv)
    hom_nay = dongho.hom_nay()
    conn = db.ket_noi()
    try:
        loi = chay(conn, hom_nay, thu=a.thu)
    finally:
        conn.close()
    print(f"{hom_nay:%d/%m/%Y}: " + ("sao lưu đủ." if not loi else "; ".join(loi)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
