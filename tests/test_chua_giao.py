"""Lead chưa giao sale không được để sót: giao lead Messenger bắt buộc chọn sale; lead chưa giao bị cảnh báo
ở hồ sơ, danh sách, Quản trị và tin nhắc sáng. Dữ liệu mẫu (giả)."""

import re
from datetime import date

from app import db, messenger, nhac_sang
from tests.conftest import csrf, dang_nhap
from tests.test_messenger import sheet  # noqa: F401 — fixture Sheet giả


def _bo_giao(ten):
    conn = db.ket_noi()
    conn.execute("UPDATE lead SET sale_id = NULL WHERE ten_ph = ?", (ten,))
    conn.commit()
    return conn.execute("SELECT id FROM lead WHERE ten_ph = ?", (ten,)).fetchone()[0]


def test_giao_lead_messenger_bat_buoc_chon_sale(sheet):  # noqa: F811
    messenger.dong_bo(db.ket_noi())
    c = dang_nhap("chu")
    r = c.post("/lead-moi", data={"csrf": csrf(c, "/lead-moi?messenger=1001"), "ten_ph": "Mai Thử",
                                  "sdt": "0911000001", "customer_id": "1001", "sale_id": ""})
    assert r.status_code == 400 and "Chọn sale phụ trách" in r.text
    assert not db.ket_noi().execute("SELECT 1 FROM lead WHERE customer_id = '1001'").fetchone()
    assert 'name="customer_id" value="1001"' in r.text  # biểu mẫu giữ nguyên để chọn sale rồi lưu lại


def test_ho_so_chua_giao_canh_bao_to(du_lieu):
    lead = _bo_giao("Đào Thử")
    html = dang_nhap("chu").get(f"/lead/{lead}").text
    assert 'class="canh-bao"' in html and "Chưa giao sale" in html and f'href="/lead/{lead}/sua"' in html


def test_danh_sach_va_quan_tri_dem_lead_chua_giao(du_lieu):
    _bo_giao("Đào Thử")
    _bo_giao("Hoa Thử")
    c = dang_nhap("chu")
    tat_ca = c.get("/tat-ca").text
    assert "2 lead chưa giao sale" in tat_ca
    assert tat_ca.count("nhan-chua-giao") == 2
    assert re.search(r"Lead chưa giao.*?<strong class=\"dem-do\">2</strong>", c.get("/chu").text, re.S)


def test_tin_nhac_sang_bao_lead_chua_giao(du_lieu):
    _bo_giao("Đào Thử")
    conn = db.ket_noi()
    db.dat_he_thong(conn, "telegram_nhom", "-1")
    conn.commit()
    gui = []
    nhac_sang.chay(conn, date(2026, 11, 4), gui=lambda chat, tin: gui.append(tin) or True)
    assert "Lead chưa giao sale: 1" in gui[0]


def test_chu_them_hoac_sua_lead_khong_chon_sale_thi_khong_luu(du_lieu):
    c = dang_nhap("chu")
    r = c.post("/lead-moi", data={"csrf": csrf(c, "/lead-moi"), "ten_ph": "Tay Thử", "sdt": "0912000009", "sale_id": ""})
    assert r.status_code == 400 and "Chọn sale phụ trách" in r.text
    assert not db.ket_noi().execute("SELECT 1 FROM lead WHERE ten_ph = 'Tay Thử'").fetchone()
    conn = db.ket_noi()
    lead = conn.execute("SELECT * FROM lead WHERE ten_ph = 'Đào Thử'").fetchone()
    r = c.post(f"/lead/{lead['id']}/sua", data={"csrf": csrf(c, "/lead-moi"), "ten_ph": "Đào Thử", "sdt": lead["sdt"],
                                                "sale_id": ""})
    assert r.status_code == 400
    assert conn.execute("SELECT sale_id FROM lead WHERE id = ?", (lead["id"],)).fetchone()[0] == lead["sale_id"]
    form = c.get("/lead-moi").text
    assert re.search(r'<select name="sale_id" required>', form)
