"""Lý do từ chối "Khác" phải ghi rõ chi tiết; chi tiết hiện ở lịch sử và file xuất. Dữ liệu mẫu (giả)."""

from app import db
from tests.conftest import csrf, dang_nhap, id_lead


def _gui(c, lid, **them):
    data = {"csrf": csrf(c, f"/lead/{lid}/ghi-nhan"), "phuong_thuc": "Gọi điện", "tinh_trang": "Từ chối", **them}
    return c.post(f"/lead/{lid}/ghi-nhan", data=data, follow_redirects=False)


def _cuoi(lid):
    return db.ket_noi().execute("SELECT * FROM cham_soc WHERE lead_id = ? ORDER BY id DESC", (lid,)).fetchone()


def test_khac_khong_ghi_ro_thi_khong_luu(du_lieu):
    c = dang_nhap("sale1")
    lid = id_lead("Hoa Thử")
    truoc = _cuoi(lid)
    r = _gui(c, lid, ly_do_tu_choi="Khác", ly_do_chi_tiet="  ")
    assert r.status_code == 400 and "ghi rõ lý do" in r.text
    assert (_cuoi(lid) or {"id": None})["id"] == (truoc or {"id": None})["id"]


def test_khac_ghi_ro_thi_luu_va_hien(du_lieu):
    c = dang_nhap("sale1")
    lid = id_lead("Hoa Thử")
    form = c.get(f"/lead/{lid}/ghi-nhan").text
    assert 'data-hien-khi="ly_do_tu_choi=Khác"' in form and 'name="ly_do_chi_tiet"' in form
    assert _gui(c, lid, ly_do_tu_choi="Khác", ly_do_chi_tiet="Cơ sở đang thi công").status_code == 303
    cs = _cuoi(lid)
    assert (cs["ly_do_tu_choi"], cs["ly_do_chi_tiet"]) == ("Khác", "Cơ sở đang thi công")
    assert "(Khác: Cơ sở đang thi công)" in c.get(f"/lead/{lid}").text
    chu = dang_nhap("chu")
    assert "Khác: Cơ sở đang thi công" in chu.get("/chu/xuat/cham-soc.csv").text


def test_ly_do_khac_khong_phai_khac_thi_bo_chi_tiet(du_lieu):
    c = dang_nhap("sale1")
    lid = id_lead("Hoa Thử")
    assert _gui(c, lid, ly_do_tu_choi="Học phí", ly_do_chi_tiet="còn sót").status_code == 303
    assert _cuoi(lid)["ly_do_chi_tiet"] == ""


def test_cot_moi_them_vao_db_cu(tmp_path):
    conn = db.ket_noi(tmp_path / "cu.db")
    conn.executescript(db.SCHEMA)  # DB tạo trước khi có cột mới
    assert "ly_do_chi_tiet" not in {r[1] for r in conn.execute("PRAGMA table_info(cham_soc)")}
    db.khoi_tao(conn)
    db.khoi_tao(conn)  # chạy lại không lỗi
    assert "ly_do_chi_tiet" in {r[1] for r in conn.execute("PRAGMA table_info(cham_soc)")}
