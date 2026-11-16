"""Cơ sở quan tâm: chọn nhiều, hoặc để trống khi chưa rõ. Dữ liệu mẫu (giả)."""

import re

from app import db, messenger
from tests.conftest import csrf, dang_nhap


def _lead(ten):
    conn = db.ket_noi()
    try:
        return conn.execute("SELECT * FROM lead WHERE ten_ph = ?", (ten,)).fetchone()
    finally:
        conn.close()


def _them(c, ten, sdt, co_so):
    return c.post("/lead-moi", data={"csrf": csrf(c, "/lead-moi"), "ten_ph": ten, "sdt": sdt, "co_so": co_so},
                  follow_redirects=False)


def test_chon_nhieu_co_so_hoac_de_trong(du_lieu):
    c = dang_nhap("sale1")
    assert _them(c, "Hai Thử", "0912000001", ["Kim Mã", "Chùa Láng"]).status_code == 303
    assert _lead("Hai Thử")["co_so"] == "Chùa Láng, Kim Mã"  # theo thứ tự danh mục
    _them(c, "Chưa Thử", "0912000002", [])
    assert _lead("Chưa Thử")["co_so"] == ""
    form = c.get(f"/lead/{_lead('Hai Thử')['id']}/sua").text
    assert re.search(r'name="co_so" value="Chùa Láng" checked', form)
    assert re.search(r'name="co_so" value="Kim Mã" checked', form)
    assert not re.search(r'name="co_so" value="Mỹ Đình" checked', form)


def test_loc_va_bao_cao_theo_co_so_tinh_ca_lead_nhieu_co_so(du_lieu):
    _them(dang_nhap("sale1"), "Hai Thử", "0912000001", ["Chùa Láng", "Kim Mã"])
    c = dang_nhap("chu")
    assert "Hai Thử" in c.get("/tat-ca?co_so=Kim Mã").text
    assert "Hai Thử" in c.get("/tat-ca?co_so=Chùa Láng").text
    assert "Hai Thử" not in c.get("/tat-ca?co_so=Mỹ Đình").text
    conn = db.ket_noi()
    thang = _lead("Hai Thử")["ngay_nhan"][:7]
    mong = conn.execute("SELECT COUNT(*) FROM lead WHERE substr(ngay_nhan, 1, 7) = ? AND "
                        "(', ' || co_so || ', ') LIKE '%, Kim Mã, %'", (thang,)).fetchone()[0]
    html = c.get(f"/chu/bao-cao?thang={thang}&co_so=Kim Mã").text
    assert re.search(rf"<td>Lead mới</td><td>{mong}</td>", html) and mong >= 1


def test_doan_nhieu_co_so_tu_messenger():
    ds = ["Chùa Láng", "Mỹ Đình", "Kim Mã"]
    assert messenger.doan_co_so("Mỹ Đình hoặc Kim Mã đều được", ds) == "Mỹ Đình, Kim Mã"
    assert messenger.doan_co_so("cơ sở nào gần Cầu Giấy", ds) == ""
