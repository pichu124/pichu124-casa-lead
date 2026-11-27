"""Cơ sở quan tâm có ô "Chưa rõ" (lưu là rỗng, như để trống); hồ sơ có Email không bắt buộc, có thì có nút gửi mail.
Dữ liệu mẫu (giả)."""

from app import db
from tests.conftest import csrf, dang_nhap


def _sale1():
    return str(db.ket_noi().execute("SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sale1'").fetchone()[0])


def _them(c, **them):
    data = {"csrf": csrf(c, "/lead-moi"), "ten_ph": "Mai Thử", "sdt": "0911000123", "sale_id": _sale1(), **them}
    return c.post("/lead-moi", data=data, follow_redirects=False)


def _lead():
    return db.ket_noi().execute("SELECT * FROM lead WHERE ten_ph = 'Mai Thử'").fetchone()


def test_o_chua_ro_co_so(du_lieu):
    c = dang_nhap("chu")
    form = c.get("/lead-moi").text
    assert 'name="co_so" value="Chưa rõ"' in form
    assert _them(c, co_so="Chưa rõ").status_code == 303
    r = _lead()
    assert r["co_so"] == ""
    assert "<dt>Cơ sở</dt><dd>Chưa rõ</dd>" in c.get(f"/lead/{r['id']}").text
    sua = c.get(f"/lead/{r['id']}/sua").text
    assert 'value="Chưa rõ" checked' in sua  # chưa có cơ sở thì ô Chưa rõ được tích sẵn


def test_chua_ro_kem_co_so_thi_giu_co_so(du_lieu):
    c = dang_nhap("chu")
    _them(c, co_so=["Chưa rõ", "Kim Mã"])
    assert _lead()["co_so"] == "Kim Mã"


def test_email_khong_bat_buoc_co_thi_co_nut_gui_mail(du_lieu):
    c = dang_nhap("chu")
    assert 'name="email"' in c.get("/lead-moi").text
    assert _them(c, email="  me.Mai@Vi-du.vn ").status_code == 303
    r = _lead()
    assert r["email"] == "me.Mai@Vi-du.vn"
    trang = c.get(f"/lead/{r['id']}").text
    assert 'href="mailto:me.Mai@Vi-du.vn"' in trang and "me.Mai@Vi-du.vn" in trang


def test_email_sai_dang_thi_bao_loi(du_lieu):
    c = dang_nhap("chu")
    r = _them(c, email="mai-o-gmail")
    assert r.status_code == 400 and "Email chưa đúng" in r.text
    assert _lead() is None


def test_khong_co_email_thi_khong_co_nut_mail(du_lieu):
    c = dang_nhap("chu")
    _them(c)
    r = _lead()
    assert r["email"] == "" and "mailto:" not in c.get(f"/lead/{r['id']}").text


def test_sale_sua_duoc_email(du_lieu):
    c = dang_nhap("chu")
    _them(c)
    r = _lead()
    s = dang_nhap("sale1")
    s.post(f"/lead/{r['id']}/sua", data={"csrf": csrf(s, "/lead-moi"), "ten_ph": "Mai Thử", "sdt": r["sdt"],
                                         "email": "mai@vi-du.vn"})
    assert _lead()["email"] == "mai@vi-du.vn"
