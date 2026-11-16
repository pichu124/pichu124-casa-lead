"""Tin nhắc sáng gửi vào nhóm Telegram (thay cho tin riêng buổi sáng). Dữ liệu mẫu (giả)."""

from datetime import date

from app import db, nhac_sang, telegram
from tests.conftest import csrf, dang_nhap


def _ht(khoa):
    conn = db.ket_noi()
    try:
        return db.lay_he_thong(conn, khoa)
    finally:
        conn.close()


def _noi_nhom(conn, chat="-1001", ma=None):
    ma = ma or telegram.tao_ma_nhom(conn)
    return telegram.xu_ly_cap_nhat(conn, [{"update_id": 5, "message": {
        "text": f"/noi@casa_lead_bot {ma}", "chat": {"id": int(chat), "type": "supergroup", "title": "Casa sale"}}}])


def test_noi_nhom_bang_lenh_trong_nhom(du_lieu):
    conn = db.ket_noi()
    ma = telegram.tao_ma_nhom(conn)
    telegram.xu_ly_cap_nhat(conn, [{"update_id": 1, "message": {
        "text": "/noi@casa_lead_bot sai0000000000000", "chat": {"id": -9, "type": "group", "title": "Lạ"}}},
        {"update_id": 2, "message": {"text": "chào cả nhà", "chat": {"id": -9, "type": "group", "title": "Lạ"}}}])
    assert _ht("telegram_nhom") == "" and not du_lieu  # mã sai, tin thường trong nhóm: im lặng
    _noi_nhom(conn, ma=ma)
    assert _ht("telegram_nhom") == "-1001" and _ht("telegram_nhom_ten") == "Casa sale"
    assert _ht("telegram_nhom_ma") == ""
    assert du_lieu and du_lieu[-1][0] == "-1001"


def test_nhom_doi_ma_khi_nang_cap_thanh_supergroup(du_lieu):
    conn = db.ket_noi()
    _noi_nhom(conn, chat="-55")
    telegram.xu_ly_cap_nhat(conn, [{"update_id": 9, "message": {"migrate_to_chat_id": -100555, "chat": {"id": -55, "type": "group"}}}])
    assert _ht("telegram_nhom") == "-100555"


def test_nhac_sang_gui_mot_tin_vao_nhom_thay_tin_rieng(du_lieu):
    conn = db.ket_noi()
    conn.execute("UPDATE nguoi_dung SET telegram_chat_id = '333' WHERE ten_dang_nhap = 'sale3'")
    conn.commit()
    _noi_nhom(conn)
    du_lieu.clear()
    gui = []
    nhac_sang.chay(conn, date(2026, 11, 4), gui=lambda chat, tin: gui.append((chat, tin)) or True)
    assert [c for c, _ in gui] == ["-1001"]
    tin = gui[0][1]
    assert "Sale 3" in tin and "Lan Thử" in tin and "Sale 1" in tin and "Bỏ quên" in tin
    sdt = [r[0] for r in conn.execute("SELECT sdt FROM lead")]
    assert not any(s in tin for s in sdt)


def test_khong_co_nhom_thi_van_gui_tin_rieng(du_lieu):
    conn = db.ket_noi()
    conn.execute("UPDATE nguoi_dung SET telegram_chat_id = '333' WHERE ten_dang_nhap = 'sale3'")
    conn.commit()
    gui = []
    nhac_sang.chay(conn, date(2026, 11, 4), gui=lambda chat, tin: gui.append(chat) or True)
    assert "333" in gui


def test_chu_noi_kiem_tra_go_nhom_trong_cai_dat(du_lieu, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "casa_lead_bot")
    c = dang_nhap("chu")
    r = c.post("/chu/cai-dat", data={"csrf": csrf(c, "/chu/cai-dat"), "viec": "noi_nhom"})
    ma = _ht("telegram_nhom_ma")
    assert len(ma) == 16 and f"/noi@casa_lead_bot {ma}" in r.text
    tin = [{"update_id": 3, "message": {"text": f"/noi@casa_lead_bot {ma}",
                                         "chat": {"id": -1002, "type": "group", "title": "Nhóm sale"}}}]
    monkeypatch.setattr(telegram, "_lay_cap_nhat", lambda conn: tin)
    r = c.post("/chu/cai-dat", data={"csrf": csrf(c, "/chu/cai-dat"), "viec": "kiem_tra_nhom"})
    assert "Nhóm sale" in r.text and _ht("telegram_nhom") == "-1002"
    r = c.post("/chu/cai-dat", data={"csrf": csrf(c, "/chu/cai-dat"), "viec": "go_nhom"})
    assert _ht("telegram_nhom") == ""


def test_sale_khong_noi_duoc_nhom(du_lieu):
    c = dang_nhap("sale1")
    r = c.post("/chu/cai-dat", data={"csrf": csrf(c, "/tai-khoan"), "viec": "noi_nhom"}, follow_redirects=False)
    assert r.status_code == 403 and _ht("telegram_nhom_ma") == ""
