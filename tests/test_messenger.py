"""Lead Messenger từ tab Leads của bot (qua Apps Script): đồng bộ, danh sách chưa nhận, giao lead. Dữ liệu giả."""

import re
from datetime import date

import pytest

from app import db, messenger, nhac_sang
from tests.conftest import csrf, dang_nhap


def _hang(cid, ten="Mai Thử", sdt="0911000001", **them):
    h = {"time": "2026-11-03 09:15:00", "event": "SĐT mới", "fb_name": ten, "customer_id": cid, "phone": sdt,
         "kid_name": "Bé Bơ", "kid_age": "3 tuổi", "campus": "Cơ sở Mỹ Đình - hệ song ngữ", "area": "Cầu Giấy",
         "expected_start": "Tháng 1/2027", "visit_request": "", "ad_title": "QC Cambridge T11",
         "stage": "Đã có SĐT", "last_message": "Cho chị xin học phí", "first_contact": "2026-11-02 20:01:00",
         "updated_at": "2026-11-03 09:15:00", "page": "Casa Mỹ Đình"}
    h.update(them)
    return h


@pytest.fixture
def sheet(du_lieu, monkeypatch):
    """Giả Apps Script: trả các hàng trong danh sách `hang`."""
    hang = [_hang("1001"), _hang("1002", ten="Hà Thử", sdt="0911000002", campus="Kim Mã", updated_at="2026-11-03 10:00:00"),
            _hang("1003", ten="khách chưa rõ tên", sdt=""),  # chưa để SĐT: không phải lead
            _hang("", ten="Không ID")]
    goi = []
    monkeypatch.setenv("LEADS_SHEET_WEBHOOK_URL", "https://script.google.com/macros/s/thu/exec")
    monkeypatch.setenv("LEADS_READ_TOKEN", "doc-thu")
    monkeypatch.setattr(messenger, "_tai", lambda: goi.append(1) or list(hang))
    return hang, goi


def _ds(conn):
    return [r["customer_id"] for r in messenger.chua_nhan(conn)]


def test_dong_bo_va_danh_sach_chua_nhan(sheet):
    conn = db.ket_noi()
    assert messenger.dong_bo(conn) == 3  # hàng không có Customer ID bị bỏ
    assert _ds(conn) == ["1002", "1001"]  # mới cập nhật lên đầu; chưa có SĐT thì chưa phải lead
    sheet[0][0]["phone"] = "0911000009"
    messenger.dong_bo(conn)
    assert next(r for r in messenger.chua_nhan(conn) if r["customer_id"] == "1001")["phone"] == "0911000009"


def test_tai_loi_giu_du_lieu_cu_va_bao_loi(sheet, monkeypatch):
    conn = db.ket_noi()
    messenger.dong_bo(conn)

    def hong():
        raise messenger.LoiSheet("Sheet trả ok:false (web app còn chạy bản script cũ?)")
    monkeypatch.setattr(messenger, "_tai", hong)
    assert messenger.dong_bo(conn) is None
    assert len(_ds(conn)) == 2
    assert "bản script cũ" in db.lay_he_thong(conn, "messenger_loi")


def test_chua_cau_hinh_thi_khong_goi_mang(du_lieu, monkeypatch):
    monkeypatch.delenv("LEADS_SHEET_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(messenger, "_tai", lambda: pytest.fail("không được gọi mạng"))
    assert messenger.dong_bo(db.ket_noi()) is None
    assert "chưa cấu hình" in dang_nhap("chu").get("/chu/messenger").text.lower()


def test_tai_gui_dung_token_doc_va_doc_tra_loi(monkeypatch):
    import httpx
    monkeypatch.setenv("LEADS_SHEET_WEBHOOK_URL", "https://script.google.com/macros/s/thu/exec")
    monkeypatch.setenv("LEADS_READ_TOKEN", "doc-thu")
    gui = {}

    class Tra:
        status_code = 200
        def json(self):
            return {"ok": True, "rows": [_hang("1001")]}

    def post(url, json, **kw):
        gui.update(url=url, body=json, kw=kw)
        return Tra()
    monkeypatch.setattr(httpx, "post", post)
    assert messenger._tai()[0]["customer_id"] == "1001"
    assert gui["body"] == {"type": "leads_read", "token": "doc-thu"} and gui["kw"].get("follow_redirects")

    class Hong(Tra):
        def json(self):
            return {"ok": False}
    monkeypatch.setattr(httpx, "post", lambda url, json, **kw: Hong())
    with pytest.raises(messenger.LoiSheet):
        messenger._tai()


def test_chi_chu_xem_va_giao_duoc(sheet):
    c = dang_nhap("sale1")
    assert c.get("/chu/messenger").status_code == 403
    assert c.get("/lead-moi?messenger=1001").status_code == 403


def test_man_messenger_cua_chu(sheet):
    r = dang_nhap("chu").get("/chu/messenger")
    assert r.status_code == 200 and "Mai Thử" in r.text and "Hà Thử" in r.text and "0911000001" in r.text
    assert "khách chưa rõ tên" not in r.text
    assert 'href="/lead-moi?messenger=1001"' in r.text


def test_giao_lead_dien_san_roi_bien_khoi_danh_sach(sheet):
    du_lieu = sheet  # noqa
    c = dang_nhap("chu")
    c.get("/chu/messenger")  # đồng bộ
    form = c.get("/lead-moi?messenger=1001").text
    for chu in ('value="Mai Thử"', 'value="0911000001"', 'value="Bé Bơ"', 'value="3 tuổi"', 'value="QC Cambridge T11"',
                'name="customer_id" value="1001"', "Cầu Giấy", "Cho chị xin học phí"):
        assert chu in form, chu
    assert re.search(r"<option selected>Mỹ Đình</option>", form)  # "Cơ sở Mỹ Đình - hệ song ngữ" → Mỹ Đình
    assert re.search(r"<option selected>Facebook Messenger</option>", form)
    conn = db.ket_noi()
    sale2 = conn.execute("SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sale2'").fetchone()[0]
    conn.execute("UPDATE nguoi_dung SET telegram_chat_id = '222' WHERE id = ?", (sale2,))
    conn.commit()
    ma = re.search(r'name="csrf" value="([^"]+)"', form).group(1)
    data = {"csrf": ma, "ten_ph": "Mai Thử", "sdt": "0911000001", "nguon": "Facebook Messenger",
            "customer_id": "1001", "sale_id": str(sale2)}
    r = c.post("/lead-moi", data=data, follow_redirects=False)
    assert r.status_code == 303
    lead = conn.execute("SELECT * FROM lead WHERE customer_id = '1001'").fetchone()
    assert lead and lead["sale_id"] == sale2
    assert "1001" not in _ds(conn)
    r = c.post("/lead-moi", data=data)  # giao lần nữa: từ chối, không tạo hai hồ sơ
    assert r.status_code == 400 and "đã được giao" in r.text
    assert conn.execute("SELECT COUNT(*) FROM lead WHERE customer_id = '1001'").fetchone()[0] == 1


def test_customer_id_la_hoac_cua_sale_bi_bo_qua(sheet):
    conn = db.ket_noi()
    messenger.dong_bo(conn)
    c = dang_nhap("chu")
    c.post("/lead-moi", data={"csrf": csrf(c, "/lead-moi"), "ten_ph": "X Thử", "sdt": "0911000777", "customer_id": "khong-co"})
    assert conn.execute("SELECT customer_id FROM lead WHERE ten_ph = 'X Thử'").fetchone()[0] == ""
    s = dang_nhap("sale1")
    s.post("/lead-moi", data={"csrf": csrf(s, "/lead-moi"), "ten_ph": "Y Thử", "sdt": "0911000888", "customer_id": "1002"})
    assert conn.execute("SELECT customer_id FROM lead WHERE ten_ph = 'Y Thử'").fetchone()[0] == ""
    assert "1002" in _ds(conn)


def test_bo_qua_va_trung_sdt(sheet):
    conn = db.ket_noi()
    messenger.dong_bo(conn)
    conn.execute("UPDATE lead SET sdt = '0911 000 002' WHERE id = (SELECT MIN(id) FROM lead)")
    conn.commit()
    hang = {r["customer_id"]: r for r in messenger.chua_nhan(conn)}
    assert hang["1002"]["trung"] and not hang["1001"]["trung"]
    c = dang_nhap("chu")
    c.post("/chu/messenger/bo-qua", data={"csrf": csrf(c, "/chu/messenger"), "customer_id": "1002"})
    assert _ds(conn) == ["1001"]


def test_tin_nhom_buoi_sang_bao_so_messenger_chua_giao(sheet):
    conn = db.ket_noi()
    db.dat_he_thong(conn, "telegram_nhom", "-1")
    conn.commit()
    gui = []
    nhac_sang.chay(conn, date(2026, 11, 4), gui=lambda chat, tin: gui.append(tin) or True)
    assert "Messenger chưa giao: 2" in gui[0]
    assert sheet[1]  # nhắc sáng tự đồng bộ trước khi đếm
