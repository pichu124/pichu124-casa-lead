#!/usr/bin/env python3
"""Tạo tài khoản chủ đầu tiên trên máy chủ thật (các tài khoản khác chủ tạo trong app).

    python scripts/tao_tai_khoan.py chu "Tên chủ"

Mật khẩu hỏi ở dòng lệnh, không hiện ra màn hình và không lưu vào lịch sử lệnh.
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import auth, db  # noqa: E402
from app.dongho import bay_gio, ghi_gio  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    ten_dn, ten = sys.argv[1].lower(), sys.argv[2]
    conn = db.ket_noi()
    db.khoi_tao(conn)
    if conn.execute("SELECT 1 FROM nguoi_dung WHERE ten_dang_nhap = ?", (ten_dn,)).fetchone():
        print("Tên đăng nhập này đã có.")
        return 1
    mk = getpass.getpass("Mật khẩu (ít nhất 8 ký tự): ")
    if len(mk) < auth.MAT_KHAU_TOI_THIEU or mk != getpass.getpass("Nhập lại: "):
        print("Mật khẩu quá ngắn hoặc hai lần nhập khác nhau.")
        return 1
    conn.execute("INSERT INTO nguoi_dung (ten_dang_nhap, ten, vai_tro, mat_khau, tao_luc) VALUES (?, ?, 'chu', ?, ?)",
                 (ten_dn, ten, auth.bam(mk), ghi_gio(bay_gio())))
    conn.commit()
    print(f"Đã tạo tài khoản chủ {ten_dn} trong {db.duong_dan_db()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
