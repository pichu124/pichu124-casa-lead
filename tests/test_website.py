"""Lead website: đọc tệp đăng ký của form website, danh sách chưa nhận, giao lead điền sẵn, báo Telegram. Dữ liệu giả."""

import json

import pytest

from app import db, dong_bo_website, nhac_sang, website
from tests.conftest import csrf, dang_nhap


def _dong(ten="Lan Web Thử", sdt="0912000001", thoi_gian="2026-11-03T02:15:00.000Z", **them):
    h = {"thoi_gian": thoi_gian, "ten": ten, "sdt": sdt, "thang_sinh": 5, "nam_sinh": 2023, "co_so": "chua-lang",
         "ngon_ngu": "vi", "biet_qua": "google-maps", "nguon": "google-maps", "dong_y": True, "email": "da-gui"}
    h.update(them)
    return h


@pytest.fixture
def tep(du_lieu, tmp_path, monkeypatch):
    """Tệp dang-ky.jsonl giả. Trả hàm ghi lại tệp từ danh sách dòng."""
    p = tmp_path / "dang-ky.jsonl"
    monkeypatch.setenv("CASA_WEBSITE_DANG_KY", str(p))

    def ghi(*dong, them_rac=False):
        noi_dung = [json.dumps(h, ensure_ascii=False) for h in dong]
        if them_rac:
            noi_dung += ["{không phải json", json.dumps({"ten": "Thiếu SĐT"})]
        p.write_text("\n".join(noi_dung) + "\n", encoding="utf-8")
    ghi(_dong(), _dong("Minh Web Thử", "0912000002", "2026-11-03T05:00:00.000Z", co_so="kim-ma", biet_qua="", nguon=""),
        them_rac=True)
    return ghi


def test_doc_tep_bo_dong_hong_va_moi_nhat_len_dau(tep):
    conn = db.ket_noi()
    assert website.dong_bo(conn) == 2
    ds = website.chua_nhan(conn)
    assert [h["ten"] for h in ds] == ["Minh Web Thử", "Lan Web Thử"]
    assert ds[1]["gio_vn"] == "03/11/2026 09:15"  # UTC → giờ Việt Nam
    assert ds[1]["ten_biet_qua"] == "Google Maps" and ds[1]["sinh"] == "5/2023"


def test_doc_lai_khong_nhan_doi(tep):
    conn = db.ket_noi()
    website.dong_bo(conn)
    website.dong_bo(conn)
    assert conn.execute("SELECT COUNT(*) FROM website").fetchone()[0] == 2


def test_chua_co_tep_thi_bao_chua_cau_hinh(du_lieu, tmp_path, monkeypatch):
    monkeypatch.setenv("CASA_WEBSITE_DANG_KY", str(tmp_path / "chua-co.jsonl"))
    assert website.dong_bo(db.ket_noi()) is None
    assert "chưa đọc được tệp" in dang_nhap("chu").get("/chu/website").text


def test_dien_san_doi_ma_sang_danh_muc(tep):
    conn = db.ket_noi()
    website.dong_bo(conn)
    co_so, nguon = db.danh_muc(conn, "Cơ sở"), db.danh_muc(conn, "Nguồn") + ["Google Maps", "Tự biết tới trường"]
    lan, minh = sorted(website.chua_nhan(conn), key=lambda h: h["ten"])
    v = website.dien_san(lan, co_so, nguon)
    assert (v["co_so"], v["nguon"], v["chien_dich"], v["tuoi_be"]) == ("Chùa Láng", "Google Maps", "google-maps", "sinh tháng 5/2023")
    assert "Biết Casa qua: Google Maps" in v["ghi_chu"]
    v2 = website.dien_san(minh, co_so, nguon)
    assert (v2["co_so"], v2["nguon"], v2["chien_dich"]) == ("Kim Mã", "Website", "")  # không chọn → Website
    assert website.dien_san(dict(lan, biet_qua="di-ngang-qua"), co_so, nguon)["nguon"] == "Tự biết tới trường"
    assert website.dien_san(dict(lan, co_so="chua-chon"), co_so, nguon)["co_so"] == ""
    assert website.dien_san(dict(lan, biet_qua="google"), co_so, ["Website"])["nguon"] == ""  # không có trong danh mục


def test_chu_giao_lead_tu_website(tep):
    c = dang_nhap("chu")
    r = c.get("/chu/website")
    assert "Lan Web Thử" in r.text and "Website chưa nhận" in r.text
    conn = db.ket_noi()
    ma = next(h["ma"] for h in website.chua_nhan(conn) if h["ten"] == "Lan Web Thử")
    trang = c.get(f"/lead-moi?website={ma}")
    assert 'name="website_id"' in trang.text and "Lan Web Thử" in trang.text
    sale = conn.execute("SELECT id FROM nguoi_dung WHERE vai_tro = 'sale' ORDER BY id").fetchone()[0]
    r = c.post("/lead-moi", data={"csrf": csrf(c, "/lead-moi"), "ten_ph": "Lan Web Thử", "sdt": "0912000001",
                                  "website_id": ma, "nguon": "Website", "sale_id": str(sale)}, follow_redirects=False)
    assert r.status_code == 303, r.text
    assert conn.execute("SELECT website_id FROM lead WHERE ten_ph = 'Lan Web Thử'").fetchone()[0] == ma
    assert [h["ten"] for h in website.chua_nhan(conn)] == ["Minh Web Thử"]  # đã giao thì không hiện nữa
    r = c.post("/lead-moi", data={"csrf": csrf(c, "/lead-moi"), "ten_ph": "Lan Web Thử", "sdt": "0912000001",
                                  "website_id": ma, "sale_id": str(sale)})
    assert r.status_code == 400 and "đã được giao" in r.text


def test_sale_khong_vao_duoc_va_khong_gan_duoc_ma_website(tep):
    c = dang_nhap("sale1")
    assert c.get("/chu/website").status_code in (303, 403, 404)
    conn = db.ket_noi()
    website.dong_bo(conn)
    ma = website.chua_nhan(conn)[0]["ma"]
    r = c.post("/lead-moi", data={"csrf": csrf(c, "/lead-moi"), "ten_ph": "Gán Web Thử", "sdt": "0912000099",
                                  "website_id": ma}, follow_redirects=False)
    assert r.status_code == 303
    assert conn.execute("SELECT website_id FROM lead WHERE ten_ph = 'Gán Web Thử'").fetchone()[0] == ""


def test_bo_qua(tep):
    c = dang_nhap("chu")
    conn = db.ket_noi()
    website.dong_bo(conn)
    ma = website.chua_nhan(conn)[0]["ma"]
    c.post("/chu/website/bo-qua", data={"csrf": csrf(c, "/chu/website"), "ma": ma})
    assert ma not in [h["ma"] for h in website.chua_nhan(conn)]


def test_cron_bao_mot_lan_khong_bao_don_lan_dau(tep, du_lieu):
    conn = db.ket_noi()
    conn.execute("UPDATE nguoi_dung SET telegram_chat_id = '555' WHERE vai_tro = 'chu'")
    conn.commit()
    assert dong_bo_website.chay(conn) == []  # lần đầu: ghi nhớ, không báo dồn
    tep(_dong(), _dong("Minh Web Thử", "0912000002", "2026-11-03T05:00:00.000Z"),
        _dong("Hoa Web Thử", "0912000003", "2026-11-04T01:00:00.000Z", co_so="my-dinh"))
    gui = dong_bo_website.chay(conn)
    assert len(gui) == 1 and "Hoa Web Thử" in gui[0][1] and "Mỹ Đình" in gui[0][1]
    assert "0912000003" not in gui[0][1]  # tin không chứa SĐT
    assert dong_bo_website.chay(conn) == []  # đã báo thì thôi


def test_tin_nhac_sang_co_so_website(tep):
    conn = db.ket_noi()
    website.dong_bo(conn)
    chu = conn.execute("SELECT * FROM nguoi_dung WHERE vai_tro = 'chu'").fetchone()
    from datetime import date
    assert "Website chưa giao: 2" in nhac_sang.tin_cho_chu(conn, chu, date(2026, 11, 4))


def test_khong_co_quyen_doc_thu_muc_khong_lam_sap_app_va_tin_nhac(du_lieu, tmp_path, monkeypatch):
    """Thư mục website 0750 mà user chạy app chưa vào nhóm casa-form: stat ném PermissionError."""
    import os
    from datetime import date
    p = tmp_path / "khoa" / "dang-ky.jsonl"
    monkeypatch.setenv("CASA_WEBSITE_DANG_KY", str(p))
    goc = os.stat

    def stat_khoa(duong, *a, **k):
        if str(duong).startswith(str(tmp_path / "khoa")):
            raise PermissionError(13, "Permission denied", str(duong))
        return goc(duong, *a, **k)
    monkeypatch.setattr(os, "stat", stat_khoa)
    assert website.da_cau_hinh() is False
    assert website.dong_bo(db.ket_noi()) is None
    c = dang_nhap("chu")
    assert c.get("/chu").status_code == 200
    assert c.get("/chu/website").status_code == 200
    gui = nhac_sang.chay(db.ket_noi(), date(2026, 11, 4), thu=True)
    assert gui  # vẫn có tin cho chủ và sale


def test_tep_co_byte_hong_khong_lam_sap(tep, tmp_path):
    p = tmp_path / "dang-ky.jsonl"
    with p.open("ab") as f:
        f.write(b'{"ten": "\xe1\xbb')  # form đang ghi dở một ký tự nhiều byte
    conn = db.ket_noi()
    assert website.dong_bo(conn) == 2
    c = dang_nhap("chu")
    assert c.get("/chu").status_code == 200 and c.get("/chu/website").status_code == 200


def test_chua_co_tep_luc_trien_khai_thi_dang_ky_dau_tien_van_duoc_bao(du_lieu, tmp_path, monkeypatch):
    p = tmp_path / "dang-ky.jsonl"
    monkeypatch.setenv("CASA_WEBSITE_DANG_KY", str(p))
    conn = db.ket_noi()
    conn.execute("UPDATE nguoi_dung SET telegram_chat_id = '555' WHERE vai_tro = 'chu'")
    conn.commit()
    assert dong_bo_website.chay(conn) == []  # chưa có tệp
    p.write_text(json.dumps(_dong("Đầu Web Thử", "0912000077")) + "\n", encoding="utf-8")
    gui = dong_bo_website.chay(conn)
    assert len(gui) == 1 and "Đầu Web Thử" in gui[0][1]
