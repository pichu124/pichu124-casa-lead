"""Cài đặt → Danh mục: nút ▲ ▼ đổi thứ tự lựa chọn (thứ tự hiện trong form lead). Dữ liệu mẫu (giả)."""

from app import db
from tests.conftest import csrf, dang_nhap


def _ds(loai="Nguồn"):
    return db.danh_muc(db.ket_noi(), loai)


def _doi(c, viec, gia_tri, loai="Nguồn"):
    return c.post("/chu/cai-dat", data={"csrf": csrf(c, "/chu/cai-dat"), "viec": viec, "loai": loai, "gia_tri": gia_tri},
                  follow_redirects=False)


def test_len_xuong_doi_cho_voi_lua_chon_lien_ke(du_lieu):
    c = dang_nhap("chu")
    ds = _ds()
    assert _doi(c, "len_danh_muc", ds[2]).status_code == 303
    assert _ds() == [ds[0], ds[2], ds[1], *ds[3:]]
    _doi(c, "xuong_danh_muc", ds[2])
    assert _ds() == ds


def test_dau_cuoi_khong_doi_va_khong_hien_nut(du_lieu):
    c = dang_nhap("chu")
    ds = _ds()
    _doi(c, "len_danh_muc", ds[0])
    _doi(c, "xuong_danh_muc", ds[-1])
    assert _ds() == ds
    trang = c.get("/chu/cai-dat").text
    assert 'value="len_danh_muc"' in trang and 'value="xuong_danh_muc"' in trang


def test_thu_tu_trung_van_doi_dung(du_lieu):
    conn = db.ket_noi()
    conn.execute("UPDATE danh_muc SET thu_tu = 5 WHERE loai = 'Cơ sở'")  # mọi dòng cùng thu_tu
    conn.commit()
    ds = _ds("Cơ sở")
    c = dang_nhap("chu")
    _doi(c, "xuong_danh_muc", ds[0], loai="Cơ sở")
    assert _ds("Cơ sở") == [ds[1], ds[0], *ds[2:]]
    assert _ds() and _ds("Mối quan tâm")  # loại khác không bị đụng


def test_form_lead_theo_thu_tu_moi(du_lieu):
    c = dang_nhap("chu")
    ds = _ds()
    _doi(c, "len_danh_muc", ds[-1])
    form = c.get("/lead-moi").text
    assert form.index(f">{ds[-1]}</option>") < form.index(f">{ds[-2]}</option>")


def test_sale_khong_doi_duoc(du_lieu):
    s = dang_nhap("sale1")
    ds = _ds()
    r = s.post("/chu/cai-dat", data={"csrf": csrf(s, "/tai-khoan"), "viec": "len_danh_muc", "loai": "Nguồn",
                                     "gia_tri": ds[1]}, follow_redirects=False)
    assert r.status_code == 403 and _ds() == ds
