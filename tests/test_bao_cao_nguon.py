"""Báo cáo tháng chia theo Nguồn và Chiến dịch (bước 4). Dữ liệu giả."""

import re

from app import chu, db, quy_tac_nhac as q
from tests.conftest import dang_nhap


def _them(conn, ten, ngay, nguon, chien_dich="", tinh_trang=None):
    cur = conn.execute("INSERT INTO lead (ngay_nhan, ten_ph, sdt, nguon, chien_dich, tao_luc) VALUES (?, ?, ?, ?, ?, ?)",
                       (ngay, ten, "0913" + str(abs(hash(ten)) % 10**6).zfill(6), nguon, chien_dich, ngay))
    if tinh_trang:
        conn.execute("INSERT INTO cham_soc (lead_id, thoi_gian, tinh_trang) VALUES (?, ?, ?)",
                     (cur.lastrowid, ngay, tinh_trang))


def _hang(html, ten):
    m = re.search(r"<tr><td>" + re.escape(ten) + r"</td>(.*?)</tr>", html)
    return re.findall(r"<td>([^<]*)</td>", m.group(1)) if m else None


def test_bao_cao_theo_nguon_va_chien_dich(du_lieu):
    conn = db.ket_noi()
    _them(conn, "Một Nguồn Thử", "2027-01-05 09:00:00", "Google Maps", "google-maps", q.DAT_COC)
    _them(conn, "Hai Nguồn Thử", "2027-01-06 09:00:00", "Google Maps", "google-maps")
    _them(conn, "Ba Nguồn Thử", "2027-01-07 09:00:00", "", "")
    _them(conn, "Bốn Nguồn Thử", "2027-02-01 09:00:00", "Google Maps", "google-maps", q.DAT_COC)  # tháng khác
    conn.commit()
    html = dang_nhap("chu").get("/chu/bao-cao?thang=2027-01").text
    assert "Theo nguồn" in html and "Theo chiến dịch" in html
    # Lead mới, Đã tư vấn, Đã tham quan, Đã đặt cọc, Đã nhập học, tỷ lệ đặt cọc / lead mới
    assert _hang(html, "Google Maps") == ["2", "1", "1", "1", "0", "50%"]
    assert _hang(html, chu.CHUA_GHI) == ["1", "0", "0", "0", "0", "0%"]
    assert _hang(html, "google-maps") == ["2", "1", "1", "1", "0", "50%"]
    assert _hang(html, "Zalo") is None  # nguồn không có lead mới trong tháng thì không hiện


def test_nhom_trong_danh_muc_truoc_ngoai_danh_muc_sau_o_trong_cuoi():
    ho_so = [{"Mã lead": str(i), "Ngày nhận": "2027-01-01", "Cơ sở": "", "Nguồn": n, "Chiến dịch": ""}
             for i, n in enumerate(["", "Lạ", "Zalo", "Lạ", "Facebook"])]
    ten = [h["ten"] for h in chu._theo_nhom(ho_so, [], "2027-01", "Nguồn", ["Facebook", "Zalo"])]
    assert ten == ["Facebook", "Zalo", "Lạ", chu.CHUA_GHI]
