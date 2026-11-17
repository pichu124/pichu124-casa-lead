"""Gửi ưu đãi / thông tin là việc của sale: đến hạn thì hiện ở tab Hôm nay (nút mở Zalo, Đã gửi; sale tự viết ưu đãi
của cơ sở mình) và còn nhắc tới khi sale bấm Đã gửi; chủ chỉ theo dõi danh sách. Dữ liệu mẫu (giả)."""

import re
from datetime import date

from app import db, nhac_sang, quy_tac_nhac as q
from tests.conftest import csrf, dang_nhap, id_lead


QUA_HAN = re.compile(r"quá hạn (\d+) ngày")


def _den_han(ten="Hoa Thử"):
    """Lead đang chăm sóc, băn khoăn học phí, liên hệ lần cuối hơn 100 ngày trước: ưu đãi (60 ngày sau lần liên hệ
    cuối) đã quá hạn."""
    lid = id_lead(ten)
    conn = db.ket_noi()
    conn.execute("UPDATE lead SET ngay_nhan = '2026-07-01 09:00:00', ly_do_chat_luong = 'Học phí vượt khả năng' "
                 "WHERE id = ?", (lid,))
    conn.execute("UPDATE cham_soc SET thoi_gian = datetime(thoi_gian, '-100 days') WHERE lead_id = ?", (lid,))
    conn.commit()
    return lid


def test_hom_nay_cua_sale_co_viec_gui_uu_dai_kem_zalo(du_lieu):
    lid = _den_han()
    trang = dang_nhap("sale1").get("/hom-nay").text
    assert "Gửi ưu đãi học phí" in trang and "Hoa Thử" in trang and QUA_HAN.search(trang)
    assert 'href="https://zalo.me/' in trang and "Chép nội dung" not in trang
    assert f'action="/lead/{lid}/da-gui"' in trang
    assert "Gửi ưu đãi học phí" not in dang_nhap("sale2").get("/hom-nay").text  # lead của sale1


def test_bam_da_gui_thi_het_nhac_va_khong_ghi_trung(du_lieu):
    lid = _den_han()
    s = dang_nhap("sale1")
    for _ in range(2):
        r = s.post(f"/lead/{lid}/da-gui", data={"csrf": csrf(s, "/lead-moi"), "kieu": "uu-dai"}, follow_redirects=False)
        assert r.status_code == 303
    rows = list(db.ket_noi().execute("SELECT loai, nguoi_gui FROM gui_thong_tin WHERE lead_id = ?", (lid,)))
    assert len(rows) == 1 and rows[0]["loai"] == q.GUI_UU_DAI
    assert "Gửi ưu đãi học phí" not in s.get("/hom-nay").text


def test_sale_khac_khong_ghi_duoc(du_lieu):
    lid = _den_han()
    s = dang_nhap("sale2")
    s.post(f"/lead/{lid}/da-gui", data={"csrf": csrf(s, "/lead-moi"), "kieu": "uu-dai"})
    assert not db.ket_noi().execute("SELECT 1 FROM gui_thong_tin WHERE lead_id = ?", (lid,)).fetchone()


def test_chu_chi_theo_doi_danh_sach_kem_sale_va_qua_han(du_lieu):
    _den_han()
    c = dang_nhap("chu")
    trang = c.get("/chu/gui/uu-dai").text
    assert "Hoa Thử" in trang and QUA_HAN.search(trang) and 'type="checkbox"' not in trang
    assert "Sale 1" in trang or "sale1" in trang.lower()
    assert c.post("/chu/gui/uu-dai", data={"csrf": csrf(c, "/chu/cai-dat")}).status_code in (404, 405)


def test_tin_nhac_sang_co_viec_gui(du_lieu):
    _den_han()
    conn = db.ket_noi()
    ds = nhac_sang.chay(conn, date(2026, 11, 4), thu=True)
    tin = "\n".join(t for _, t in ds)
    assert "Hoa Thử" in tin and "Gửi ưu đãi học phí" in tin


def test_lead_thuong_dang_cham_soc_khong_bi_nhac_gui_uu_dai(du_lieu):
    conn = db.ket_noi()
    conn.execute("UPDATE lead SET ngay_nhan = '2026-07-01 09:00:00' WHERE ten_ph = 'Đào Thử'")
    conn.commit()
    assert "Gửi ưu đãi" not in dang_nhap("sale1").get("/hom-nay").text  # sale tự quyết khi đang chăm sóc


def test_qua_han_roi_ghi_them_cham_soc_van_con_nhac(du_lieu):
    """Sale gọi phụ huynh (ghi nhận) mà chưa gửi ưu đãi: việc gửi đã quá hạn không được biến mất."""
    lid = _den_han()
    s = dang_nhap("sale1")
    assert QUA_HAN.search(s.get("/hom-nay").text)
    r = s.post(f"/lead/{lid}/ghi-nhan", follow_redirects=False, data={"csrf": csrf(s, f"/lead/{lid}/ghi-nhan"), "phuong_thuc": "Gọi điện",
                                          "tinh_trang": "Đang cân nhắc", "muc_quan_tam": "Quan tâm bình thường",
                                          "phan_hoi": "Hỏi lại học phí"})
    assert r.status_code == 303
    trang = s.get("/hom-nay").text
    assert "Gửi ưu đãi học phí" in trang and QUA_HAN.search(trang)
    assert "Hoa Thử" in dang_nhap("chu").get("/chu/gui/uu-dai").text
    s.post(f"/lead/{lid}/da-gui", data={"csrf": csrf(s, "/lead-moi"), "kieu": "uu-dai"})
    assert "Gửi ưu đãi học phí" not in s.get("/hom-nay").text


def _qua_han_roi_ghi_cham_soc():
    lid = _den_han()
    s = dang_nhap("sale1")
    s.get("/hom-nay")  # việc đến hạn được ghi lại
    s.post(f"/lead/{lid}/ghi-nhan", data={"csrf": csrf(s, f"/lead/{lid}/ghi-nhan"), "phuong_thuc": "Gọi điện",
                                          "tinh_trang": "Đang cân nhắc", "muc_quan_tam": "Quan tâm bình thường",
                                          "phan_hoi": "Hỏi lại học phí"})
    return lid, s


def test_chay_thu_tin_nhac_ngay_cu_khong_lam_mat_viec(du_lieu):
    _, s = _qua_han_roi_ghi_cham_soc()
    nhac_sang.chay(db.ket_noi(), date(2026, 9, 25), thu=True)
    nhac_sang.chay(db.ket_noi(), date(2026, 9, 25))
    assert QUA_HAN.search(s.get("/hom-nay").text)


def test_tam_dung_roi_bo_tam_dung_viec_van_con(du_lieu):
    lid, s = _qua_han_roi_ghi_cham_soc()
    conn = db.ket_noi()
    conn.execute("UPDATE lead SET tam_dung = 1 WHERE id = ?", (lid,))
    conn.commit()
    assert "Gửi ưu đãi học phí" not in s.get("/hom-nay").text
    conn.execute("UPDATE lead SET tam_dung = 0 WHERE id = ?", (lid,))
    conn.commit()
    assert QUA_HAN.search(s.get("/hom-nay").text)


def test_tin_nhac_sang_ghi_lai_viec_cua_lead_chua_giao(du_lieu):
    lid = _den_han()
    conn = db.ket_noi()
    conn.execute("UPDATE lead SET sale_id = NULL WHERE id = ?", (lid,))
    conn.commit()
    nhac_sang.chay(conn, date(2026, 11, 4))
    assert conn.execute("SELECT han FROM viec_gui_den WHERE lead_id = ?", (lid,)).fetchone()


def test_dai_han_sang_dang_cham_soc_roi_ve_dai_han_khong_hien_viec_cu(du_lieu):
    """Lead dài hạn có việc gửi thông tin quá hạn, rồi đang chăm sóc (thôi gửi thông tin), rồi lại dài hạn:
    hạn mới tính từ lần liên hệ mới, không lôi việc cũ quá hạn 30+ ngày về."""
    lid = id_lead("Hoa Thử")
    conn = db.ket_noi()
    conn.execute("DELETE FROM cham_soc WHERE lead_id = ?", (lid,))
    conn.execute("INSERT INTO cham_soc (lead_id, thoi_gian, sale_id, phuong_thuc, tinh_trang, ly_do_tu_choi) "
                 "SELECT ?, '2026-09-01 09:00:00', sale_id, 'Gọi điện', 'Từ chối', 'Chưa có nhu cầu' FROM lead WHERE id = ?",
                 (lid, lid))
    conn.commit()
    s = dang_nhap("sale1")
    assert "Gửi thông tin hoạt động" in s.get("/hom-nay").text  # hạn 01/10: đã ghi lại
    ma = csrf(s, f"/lead/{lid}/ghi-nhan")
    s.post(f"/lead/{lid}/ghi-nhan", data={"csrf": ma, "phuong_thuc": "Gọi điện", "tinh_trang": "Đang cân nhắc",
                                          "muc_quan_tam": "Quan tâm bình thường", "hen_lai_sau": "1 tuần"})
    assert "Gửi thông tin hoạt động" not in s.get("/hom-nay").text
    s.post(f"/lead/{lid}/ghi-nhan", data={"csrf": ma, "phuong_thuc": "Gọi điện", "tinh_trang": "Từ chối",
                                          "ly_do_tu_choi": "Chưa có nhu cầu"})
    assert "Gửi thông tin hoạt động" not in s.get("/hom-nay").text  # hạn mới 04/12
