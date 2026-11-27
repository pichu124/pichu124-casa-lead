"""Báo cáo tháng tự động: tóm tắt tháng trước gửi Telegram nhóm quản lý vào ngày làm việc đầu tháng, và nút
"Chép bản tóm tắt" ở /chu/bao-cao. Dữ liệu giả."""

from datetime import date

from app import bao_cao_thang as bct, db, quy_tac_nhac as q
from tests.conftest import dang_nhap


def _them(conn, ten, ngay, co_so="", nguon="", chien_dich="", tinh_trang=None):
    cur = conn.execute("INSERT INTO lead (ngay_nhan, ten_ph, sdt, co_so, nguon, chien_dich, tao_luc) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (ngay, ten, "0913" + str(abs(hash(ten)) % 10**6).zfill(6), co_so, nguon, chien_dich, ngay))
    if tinh_trang:
        conn.execute("INSERT INTO cham_soc (lead_id, thoi_gian, tinh_trang) VALUES (?, ?, ?)",
                     (cur.lastrowid, ngay, tinh_trang))


def _du_lieu_thang(conn):
    # tháng 01/2027: 4 lead mới; tháng 12/2026: 1 lead mới (để so sánh)
    _them(conn, "Một Báo Cáo Thử", "2027-01-05 09:00:00", "Kim Mã", "Facebook Messenger", "QC Cambridge", q.DAT_COC)
    _them(conn, "Hai Báo Cáo Thử", "2027-01-06 09:00:00", "Kim Mã, Mỹ Đình", "Facebook Messenger", "QC Cambridge",
          q.DA_THAM_QUAN)
    _them(conn, "Ba Báo Cáo Thử", "2027-01-07 09:00:00", "", "Google Maps", "google-maps")
    _them(conn, "Bốn Báo Cáo Thử", "2027-01-08 09:00:00", "Chùa Láng", "", "Hội chợ")
    _them(conn, "Năm Báo Cáo Thử", "2026-12-20 09:00:00", "Kim Mã", "Zalo", "", q.DAT_COC)
    conn.commit()


def test_tom_tat_phieu_nguon_co_so_chien_dich(du_lieu):
    conn = db.ket_noi()
    _du_lieu_thang(conn)
    t = bct.tom_tat(conn, "2027-01", kem_link=False)
    assert "tháng 01/2027" in t
    assert "- Lead mới: 4 (tháng 12/2026: 1)" in t
    assert "- Đã tham quan: 2 (tháng 12/2026: 1)" in t
    assert "- Đã đặt cọc: 1 (tháng 12/2026: 1)" in t
    assert "- Facebook Messenger: 2 · 1" in t and "- Google Maps: 1 · 0" in t and "- (chưa ghi): 1 · 0" in t
    assert "Zalo" not in t  # nguồn không có lead mới tháng này
    # lead quan tâm Kim Mã và Mỹ Đình được đếm ở cả hai cơ sở
    assert "- Kim Mã: 2 · 2 · 1" in t and "- Mỹ Đình: 1 · 1 · 0" in t and "- Chùa Láng: 1 · 0 · 0" in t
    assert "- Chưa rõ cơ sở: 1 · 0 · 0" in t
    assert "1. QC Cambridge: 2 · 1\n2. Hội chợ: 1 · 0\n3. google-maps: 1 · 0" in t
    assert "còn tăng" in t  # đặt cọc tính theo tháng nhận lead
    assert "Báo Cáo Thử" not in t and "0913" not in t  # không tên, không SĐT


def test_thang_chua_co_lead(du_lieu):
    t = bct.tom_tat(db.ket_noi(), "2030-05", kem_link=False)
    assert "- Lead mới: 0" in t and "chưa có lead mới" in t


def test_gui_vao_ngay_lam_viec_dau_thang_mot_lan(du_lieu, monkeypatch):
    conn = db.ket_noi()
    _du_lieu_thang(conn)
    db.dat_he_thong(conn, "telegram_nhom", "-1001")
    conn.commit()
    monkeypatch.setenv("CASA_LEAD_URL", "https://casa-lead.vi-du.vn")
    assert bct.chay(conn, date(2027, 1, 29)) == []  # chưa tới ngày gửi
    gui = bct.chay(conn, date(2027, 2, 1))
    assert [c for c, _ in du_lieu] == ["-1001"] and len(gui) == 1
    tin = du_lieu[0][1]
    assert "tháng 01/2027" in tin and "https://casa-lead.vi-du.vn/chu/bao-cao?thang=2027-01" in tin
    assert bct.chay(conn, date(2027, 2, 1)) == [] and len(du_lieu) == 1  # cron chạy lại: không gửi lần hai
    assert bct.chay(conn, date(2027, 2, 2)) == [] and len(du_lieu) == 1  # ngày gửi bù hôm sau: đã gửi rồi


def test_chua_noi_nhom_thi_gui_chu_gui_loi_thi_lan_sau_gui_lai(du_lieu, monkeypatch):
    conn = db.ket_noi()
    conn.execute("UPDATE nguoi_dung SET telegram_chat_id = '555' WHERE vai_tro = 'chu'")
    conn.commit()
    monkeypatch.setattr(bct.telegram, "gui_tin", lambda chat, tin: False)
    assert bct.chay(conn, date(2026, 12, 1)) == []
    assert not db.lay_he_thong(conn, "bao_cao_thang_da_gui")
    da = []
    monkeypatch.setattr(bct.telegram, "gui_tin", lambda chat, tin: da.append(chat) or True)
    assert len(bct.chay(conn, date(2026, 12, 1))) == 1 and da == ["555"]


def test_chay_thu_khong_gui_khong_ghi(du_lieu):
    conn = db.ket_noi()
    db.dat_he_thong(conn, "telegram_nhom", "-1001")
    conn.commit()
    kq = bct.chay(conn, date(2026, 12, 1), thu=True)
    assert len(kq) == 1 and "tháng 11/2026" in kq[0][1]
    assert du_lieu == [] and not db.lay_he_thong(conn, "bao_cao_thang_da_gui")
    assert len(bct.chay(conn, date(2026, 12, 15), thu=True, thang="2026-11")) == 1  # ép tháng để xem trước


def test_trang_bao_cao_co_ban_tom_tat_va_nut_chep(du_lieu):
    conn = db.ket_noi()
    _du_lieu_thang(conn)
    html = dang_nhap("chu").get("/chu/bao-cao?thang=2027-01&co_so=Kim+M%C3%A3").text
    assert 'id="tom-tat"' in html and 'data-chep="tom-tat"' in html and "Chép bản tóm tắt" in html
    assert "- Lead mới: 4 (tháng 12/2026: 1)" in html  # bản tóm tắt luôn tính mọi cơ sở
    assert "/chu/bao-cao?thang" not in html.split('id="tom-tat"')[1].split("</textarea>")[0]  # bản chép không kèm link
    assert dang_nhap("sale1").get("/chu/bao-cao").status_code == 403


def test_nut_chep_co_trong_app_js(du_lieu):
    from pathlib import Path
    js = (Path(__file__).parent.parent / "app/static/app.js").read_text(encoding="utf-8")
    assert "closest('[data-chep]')" in js and "clipboard.writeText" in js and "execCommand('copy')" in js
    assert "/static/app.js?v=7" in dang_nhap("chu").get("/chu/bao-cao").text


def test_hai_chu_mot_nguoi_loi_thi_lan_sau_chi_gui_nguoi_do(du_lieu, monkeypatch):
    conn = db.ket_noi()
    chu_id = conn.execute("SELECT id FROM nguoi_dung WHERE vai_tro = 'chu'").fetchone()[0]
    conn.execute("UPDATE nguoi_dung SET telegram_chat_id = '555' WHERE id = ?", (chu_id,))
    conn.execute("UPDATE nguoi_dung SET vai_tro = 'chu', telegram_chat_id = '777' WHERE ten_dang_nhap = 'sale1'")
    conn.commit()
    da = []
    monkeypatch.setattr(bct.telegram, "gui_tin", lambda chat, tin: da.append(chat) or chat != "777")
    assert [c for c, _ in bct.chay(conn, date(2026, 12, 1))] == ["555"]
    da.clear()
    monkeypatch.setattr(bct.telegram, "gui_tin", lambda chat, tin: da.append(chat) or True)
    assert [c for c, _ in bct.chay(conn, date(2026, 12, 1))] == ["777"] and da == ["777"]  # 555 không nhận trùng
    assert bct.chay(conn, date(2026, 12, 2)) == [] and da == ["777"]


def test_ngay_gui_ma_loi_het_thi_hom_sau_gui_bu(du_lieu, monkeypatch):
    conn = db.ket_noi()
    db.dat_he_thong(conn, "telegram_nhom", "-1001")
    conn.commit()
    monkeypatch.setattr(bct.telegram, "gui_tin", lambda chat, tin: False)
    assert bct.chay(conn, date(2026, 12, 1)) == []
    monkeypatch.setattr(bct.telegram, "gui_tin", lambda chat, tin: True)
    assert len(bct.chay(conn, date(2026, 12, 2))) == 1


def test_xem_truoc_theo_thang_khong_bao_gio_gui_that(du_lieu, capsys):
    import pytest
    conn = db.ket_noi()
    db.dat_he_thong(conn, "telegram_nhom", "-1001")
    conn.commit()
    assert len(bct.chay(conn, date(2026, 11, 20), thang="2026-11")) == 1  # ép tháng là xem trước, kể cả thiếu thu
    assert du_lieu == [] and not db.lay_he_thong(conn, bct.DA_GUI)
    with pytest.raises(SystemExit):
        bct.main(["--thang", "2026-11"])  # dòng lệnh: --thang phải đi kèm --thu
    assert du_lieu == []


def test_co_so_ngoai_danh_muc_vao_dong_co_so_khac(du_lieu):
    conn = db.ket_noi()
    _them(conn, "Cũ Cơ Sở Thử", "2027-03-05 09:00:00", "Long Biên")
    _them(conn, "Mới Cơ Sở Thử", "2027-03-06 09:00:00", "Kim Mã")
    conn.commit()
    t = bct.tom_tat(conn, "2027-03", kem_link=False)
    assert "- Kim Mã: 1 · 0 · 0" in t and "- Cơ sở khác: 1 · 0 · 0" in t and "Chưa rõ cơ sở" not in t
