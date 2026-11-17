"""Gửi ưu đãi / thông tin là việc của sale: đến hạn thì hiện ở tab Hôm nay (nút mở Zalo, chép nội dung mẫu của chủ,
Đã gửi) và còn nhắc tới khi sale bấm Đã gửi; chủ chỉ theo dõi danh sách. Dữ liệu mẫu (giả)."""

from datetime import date

from app import db, nhac_sang, quy_tac_nhac as q
from tests.conftest import csrf, dang_nhap, id_lead


def _den_han(ten="Hoa Thử"):
    """Lead nhận từ 01/08: ưu đãi lần đầu đến hạn 30/09 (lead thường: 60 ngày sau ngày nhận) -> quá hạn 35 ngày."""
    conn = db.ket_noi()
    conn.execute("UPDATE lead SET ngay_nhan = '2026-08-01 09:00:00' WHERE ten_ph = ?", (ten,))
    conn.commit()
    return id_lead(ten)


def test_hom_nay_cua_sale_co_viec_gui_uu_dai_kem_zalo_va_noi_dung_mau(du_lieu):
    lid = _den_han()
    conn = db.ket_noi()
    db.dat_he_thong(conn, "noi_dung_uu_dai", "Tháng 11: giảm 10% học phí 3 tháng đầu")
    conn.commit()
    trang = dang_nhap("sale1").get("/hom-nay").text
    assert "Gửi ưu đãi học phí" in trang and "Hoa Thử" in trang and "quá hạn 35 ngày" in trang
    assert 'href="https://zalo.me/' in trang and "Tháng 11: giảm 10% học phí 3 tháng đầu" in trang
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
    assert "Hoa Thử" in trang and "quá hạn 35 ngày" in trang and 'type="checkbox"' not in trang
    assert "Sale 1" in trang or "sale1" in trang.lower()
    assert c.post("/chu/gui/uu-dai", data={"csrf": csrf(c, "/chu/cai-dat")}).status_code in (404, 405)


def test_tin_nhac_sang_co_viec_gui(du_lieu):
    _den_han()
    conn = db.ket_noi()
    ds = nhac_sang.chay(conn, date(2026, 11, 4), thu=True)
    tin = "\n".join(t for _, t in ds)
    assert "Hoa Thử" in tin and "Gửi ưu đãi học phí" in tin


def test_chu_soan_noi_dung_mau_o_cai_dat(du_lieu):
    c = dang_nhap("chu")
    c.post("/chu/cai-dat", data={"csrf": csrf(c, "/chu/cai-dat"), "viec": "noi_dung_gui",
                                 "noi_dung_uu_dai": "Ưu đãi T11", "noi_dung_thong_tin": "Hội thảo 30/11"})
    conn = db.ket_noi()
    assert db.lay_he_thong(conn, "noi_dung_uu_dai") == "Ưu đãi T11"
    assert db.lay_he_thong(conn, "noi_dung_thong_tin") == "Hội thảo 30/11"
    assert "Hội thảo 30/11" in c.get("/chu/cai-dat").text


def test_qua_han_roi_ghi_them_cham_soc_van_con_nhac(du_lieu):
    """Sale gọi phụ huynh (ghi nhận) mà chưa gửi ưu đãi: việc gửi đã quá hạn không được biến mất."""
    lid = _den_han()
    s = dang_nhap("sale1")
    assert "quá hạn 35 ngày" in s.get("/hom-nay").text
    r = s.post(f"/lead/{lid}/ghi-nhan", follow_redirects=False, data={"csrf": csrf(s, f"/lead/{lid}/ghi-nhan"), "phuong_thuc": "Gọi điện",
                                          "tinh_trang": "Đang cân nhắc", "muc_quan_tam": "Quan tâm bình thường",
                                          "phan_hoi": "Hỏi lại học phí"})
    assert r.status_code == 303
    trang = s.get("/hom-nay").text
    assert "Gửi ưu đãi học phí" in trang and "quá hạn 35 ngày" in trang
    assert "Hoa Thử" in dang_nhap("chu").get("/chu/gui/uu-dai").text
    s.post(f"/lead/{lid}/da-gui", data={"csrf": csrf(s, "/lead-moi"), "kieu": "uu-dai"})
    assert "Gửi ưu đãi học phí" not in s.get("/hom-nay").text
