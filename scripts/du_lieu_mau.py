#!/usr/bin/env python3
"""Nạp dữ liệu MẪU (giả) để thử app: 10 lead như Sheet mẫu của bản AppSheet, 1 chủ, 6 sale.

    python scripts/du_lieu_mau.py                    # ngày gốc = hôm nay
    python scripts/du_lieu_mau.py --hom-nay 2026-11-02

Chỉ chạy trên máy thử. Từ chối chạy khi cơ sở dữ liệu đã có lead (không ghi đè dữ liệu thật).
Mật khẩu mọi tài khoản mẫu: `thu-app-123`.
"""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import auth, db, quy_tac_nhac as q  # noqa: E402
from app.dongho import ghi_gio, bay_gio  # noqa: E402

MAT_KHAU_MAU = "thu-app-123"


def nap(conn, hom_nay: date) -> None:
    if conn.execute("SELECT COUNT(*) FROM lead").fetchone()[0] or conn.execute("SELECT COUNT(*) FROM nguoi_dung").fetchone()[0]:
        raise SystemExit("Cơ sở dữ liệu đã có lead hoặc tài khoản: không nạp dữ liệu mẫu (tài khoản mẫu có "
                         "mật khẩu công khai, không được lẫn vào máy thật).")
    bam = auth.bam(MAT_KHAU_MAU)
    id_cua: dict[str, int] = {}
    for email, ten, co_so, vai, dang_lam in q.SALE_MAU:
        ten_dn = email.split("@")[0]
        cur = conn.execute(
            "INSERT INTO nguoi_dung (ten_dang_nhap, ten, co_so, vai_tro, dang_lam, mat_khau, tao_luc) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ten_dn, "Chủ (mẫu)" if vai == "Chủ" else ten, co_so, "chu" if vai == "Chủ" else "sale",
             1 if dang_lam == "TRUE" else 0, bam, ghi_gio(bay_gio())))
        id_cua[email] = cur.lastrowid
    with tempfile.TemporaryDirectory() as tmp:
        q.tao_mau(Path(tmp), hom_nay)
        ho_so = list(csv.DictReader(open(Path(tmp) / "ho-so-lead.csv", encoding="utf-8")))
        cham_soc = list(csv.DictReader(open(Path(tmp) / "cham-soc.csv", encoding="utf-8")))
    lead_id: dict[str, int] = {}
    for h in ho_so:
        cur = conn.execute(
            "INSERT INTO lead (ngay_nhan, ten_ph, ten_be, tuoi_be, sdt, co_so, nguon, chien_dich, ph_quan_tam, sale_id, "
            "customer_id, chat_luong, ly_do_chat_luong, ghi_chu, tam_dung, ngay_sinh_be, em_nho, ngay_sinh_em, tao_luc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (h["Ngày nhận"], h["Tên phụ huynh"], h["Tên bé"], h["Tuổi bé"], h["SĐT"], h["Cơ sở"], h["Nguồn"],
             h["Chiến dịch"], h["PH quan tâm"], id_cua.get(h["Sale phụ trách"]), h["Customer ID"], h["Chất lượng lead"],
             h["Lý do chất lượng"], h["Ghi chú"], 1 if h["Tạm dừng"] == "TRUE" else 0, h["Ngày sinh bé"] or None,
             h["Em nhỏ"], h["Ngày sinh em"] or None, h["Ngày nhận"]))
        lead_id[h["Mã lead"]] = cur.lastrowid
    for c in cham_soc:
        hen = c["Hẹn lại sau"]
        conn.execute(
            "INSERT INTO cham_soc (lead_id, thoi_gian, sale_id, phuong_thuc, tinh_trang, muc_quan_tam, phan_hoi, ly_do_tu_choi, "
            "hen_lai_sau, ngay_hen_goi_lai, ngay_hen_tham_quan, ph_chu_dong, da_gui_thu_moi, ngay_nhap_hoc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (lead_id[c["Mã lead"]], c["Thời gian"], id_cua.get(c["Sale"]), c["Phương thức"], c["Tình trạng"],
             c["Mức quan tâm"], c["Phản hồi"], c["Lý do từ chối"], hen,
             c["Ngày hẹn gọi lại"] or None, c["Ngày hẹn tham quan"] or None, 1 if c["PH chủ động"] == "TRUE" else 0,
             1 if c["Đã gửi thư mời"] == "TRUE" else 0, c["Ngày nhập học dự kiến"] or None))
    conn.commit()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--hom-nay", help="ngày gốc của dữ liệu mẫu (YYYY-MM-DD)")
    a = p.parse_args()
    conn = db.ket_noi()
    db.khoi_tao(conn)
    nap(conn, date.fromisoformat(a.hom_nay) if a.hom_nay else date.today())
    print(f"Đã nạp dữ liệu mẫu vào {db.duong_dan_db()}. Đăng nhập: chu / sale1…sale6, mật khẩu {MAT_KHAU_MAU}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
