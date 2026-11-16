"""Kiểm thử app web: đăng nhập, phân quyền, ghi nhận, lead trùng, tin nhắc. Dữ liệu là dữ liệu mẫu (giả)."""

import re
from datetime import date, datetime

from fastapi.testclient import TestClient

from app import db, dongho, nhac_sang, telegram
from app.main import app
from tests.conftest import MK, csrf, dang_nhap, id_lead


def _lead(ten):
    conn = db.ket_noi()
    try:
        return dict(conn.execute("SELECT * FROM lead WHERE ten_ph = ?", (ten,)).fetchone())
    finally:
        conn.close()


def _cham_soc_cuoi(lead_id):
    conn = db.ket_noi()
    try:
        return dict(conn.execute("SELECT * FROM cham_soc WHERE lead_id = ? ORDER BY id DESC LIMIT 1", (lead_id,)).fetchone())
    finally:
        conn.close()


# ------------------------------------------------------------------ đăng nhập

def test_chua_dang_nhap_thi_ve_trang_dang_nhap(du_lieu):
    r = TestClient(app).get("/hom-nay", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/dang-nhap"


def test_sai_mat_khau_va_khoa_sau_5_lan(du_lieu):
    c = TestClient(app)
    for _ in range(5):
        r = c.post("/dang-nhap", data={"csrf": csrf(c), "ten_dang_nhap": "sale1", "mat_khau": "sai-roi"})
        assert r.status_code == 401
    r = c.post("/dang-nhap", data={"csrf": csrf(c), "ten_dang_nhap": "sale1", "mat_khau": MK})
    assert r.status_code == 429  # đúng mật khẩu cũng bị chặn khi đang khoá


def test_bieu_mau_thieu_ma_bi_tu_choi(du_lieu):
    c = TestClient(app)
    c.get("/dang-nhap")
    r = c.post("/dang-nhap", data={"ten_dang_nhap": "sale1", "mat_khau": MK})
    assert r.status_code == 403


def test_doi_mat_khau_dang_xuat_may_khac(du_lieu):
    may1, may2 = dang_nhap("sale1"), dang_nhap("sale1")
    r = may1.post("/tai-khoan/mat-khau", data={"csrf": csrf(may1, "/tai-khoan"), "cu": MK, "moi": "mat-khau-moi-1",
                                              "lai": "mat-khau-moi-1"}, follow_redirects=False)
    assert r.status_code == 303
    assert may1.get("/hom-nay", follow_redirects=False).status_code == 200
    assert may2.get("/hom-nay", follow_redirects=False).status_code == 303  # máy kia phải đăng nhập lại


def test_tai_khoan_nghi_viec_khong_dang_nhap_duoc(du_lieu):
    chu = dang_nhap("chu")
    uid = db.ket_noi().execute("SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sale1'").fetchone()[0]
    sale = dang_nhap("sale1")
    chu.post(f"/quan-tri/nguoi-dung/{uid}", data={"csrf": csrf(chu, "/quan-tri/nguoi-dung"), "viec": "nghi"})
    assert sale.get("/hom-nay", follow_redirects=False).status_code == 303
    c = TestClient(app)
    assert c.post("/dang-nhap", data={"csrf": csrf(c), "ten_dang_nhap": "sale1", "mat_khau": MK}).status_code == 401


# ------------------------------------------------------------------ phân quyền

def test_sale_chi_thay_lead_cua_minh(du_lieu):
    c = dang_nhap("sale1")
    r = c.get("/cua-toi")
    assert "Hoa Thử" in r.text and "Đào Thử" in r.text
    assert "Lan Thử" not in r.text and "Vy Thử" not in r.text
    for url in (f"/lead/{id_lead('Lan Thử')}", f"/lead/{id_lead('Lan Thử')}/ghi-nhan", f"/lead/{id_lead('Lan Thử')}/sua"):
        assert c.get(url).status_code == 404, url
    r = c.post(f"/lead/{id_lead('Lan Thử')}/ghi-nhan",
               data={"csrf": csrf(c, "/tai-khoan"), "phuong_thuc": "Gọi điện", "tinh_trang": "Đang cân nhắc",
                     "muc_quan_tam": "Hời hợt"})
    assert r.status_code == 404
    assert c.get("/tat-ca").status_code == 403
    assert c.get("/quan-tri/nguoi-dung").status_code == 403


def test_sale_khong_tu_doi_nguoi_phu_trach_hay_tam_dung(du_lieu):
    c = dang_nhap("sale1")
    lid = id_lead("Hoa Thử")
    truoc = _lead("Hoa Thử")
    form = {k: truoc[k] or "" for k in ("ten_ph", "sdt", "ten_be", "tuoi_be", "co_so", "nguon")}
    form.update(csrf=csrf(c, f"/lead/{lid}/sua"), sale_id="1", tam_dung="1", ghi_chu="sửa thử")
    assert c.post(f"/lead/{lid}/sua", data=form, follow_redirects=False).status_code == 303
    sau = _lead("Hoa Thử")
    assert (sau["sale_id"], sau["tam_dung"], sau["ghi_chu"]) == (truoc["sale_id"], 0, "sửa thử")


def test_chu_thay_tat_ca(du_lieu):
    r = dang_nhap("chu").get("/tat-ca")
    for ten in ("Lan Thử", "Hoa Thử", "Vy Thử", "Tú Thử"):
        assert ten in r.text


# ------------------------------------------------------------------ màn Hôm nay và quy tắc

def test_hom_nay_cua_sale3(du_lieu):
    r = dang_nhap("sale3").get("/hom-nay")
    assert "Lan Thử" in r.text and "Xác nhận lịch tham quan" in r.text  # hẹn tham quan 04/11, xác nhận 03/11: quá hạn
    assert "Quang Thử" in r.text and "Liên hệ lần đầu" in r.text


def test_ghi_nhan_be_nho_chuyen_dai_han(du_lieu, monkeypatch):
    monkeypatch.setattr(dongho, "GIO_CO_DINH", datetime(2026, 11, 5, 10, 0))
    c = dang_nhap("sale2")
    r = c.post("/lead-moi", data={"csrf": csrf(c, "/lead-moi"), "ten_ph": "Thử Nhỏ", "sdt": "0900000701",
                                  "tuoi_be": "10 tháng", "co_so": "Chùa Láng", "nguon": "Zalo"}, follow_redirects=False)
    assert r.status_code == 303
    lid = int(r.headers["location"].rsplit("/", 1)[1])
    r = c.post(f"/lead/{lid}/ghi-nhan", data={"csrf": csrf(c, f"/lead/{lid}/ghi-nhan"), "phuong_thuc": "Gọi điện",
                                              "tinh_trang": "Đang cân nhắc", "muc_quan_tam": "Quan tâm bình thường"},
               follow_redirects=False)
    assert r.status_code == 303
    trang = c.get(f"/lead/{lid}").text
    assert "Dài hạn" in trang and "08/03/2027" in trang and "Bé sắp đủ tuổi nhận học" in trang


def test_o_an_con_gia_tri_cu_bi_xoa(du_lieu):
    c = dang_nhap("sale1")
    lid = id_lead("Hoa Thử")
    r = c.post(f"/lead/{lid}/ghi-nhan", data={
        "csrf": csrf(c, f"/lead/{lid}/ghi-nhan"), "phuong_thuc": "Gọi điện", "tinh_trang": "Từ chối",
        "ly_do_tu_choi": "Chưa có nhu cầu", "hen_lai_sau": "1 tháng", "muc_quan_tam": "Hời hợt",
        "ngay_hen_tham_quan": "2026-11-20", "ngay_nhap_hoc": "2026-12-01", "da_gui_thu_moi": "1"}, follow_redirects=False)
    assert r.status_code == 303
    cs = _cham_soc_cuoi(lid)
    assert (cs["hen_lai_sau"], cs["muc_quan_tam"], cs["ngay_hen_tham_quan"], cs["ngay_nhap_hoc"], cs["da_gui_thu_moi"]) == \
        ("", "", None, None, 0)


def test_thieu_o_bat_buoc_thi_bao_loi(du_lieu):
    c = dang_nhap("sale1")
    lid = id_lead("Hoa Thử")
    r = c.post(f"/lead/{lid}/ghi-nhan", data={"csrf": csrf(c, f"/lead/{lid}/ghi-nhan"), "phuong_thuc": "Gọi điện",
                                              "tinh_trang": "Yêu cầu gọi lại sau", "muc_quan_tam": "Hời hợt"})
    assert r.status_code == 400 and "chọn Hẹn lại sau" in r.text
    r = c.post(f"/lead/{lid}/ghi-nhan", data={"csrf": csrf(c, f"/lead/{lid}/ghi-nhan"), "phuong_thuc": "Gọi điện",
                                              "tinh_trang": "Từ chối"})
    assert r.status_code == 400 and "lý do từ chối" in r.text


def test_dat_coc_thu_moi_roi_da_chot(du_lieu):
    c = dang_nhap("sale1")
    lid = id_lead("Hoa Thử")
    c.post(f"/lead/{lid}/ghi-nhan", data={"csrf": csrf(c, f"/lead/{lid}/ghi-nhan"), "phuong_thuc": "Gọi điện",
                                          "tinh_trang": "Đã đặt cọc", "muc_quan_tam": "Rất quan tâm",
                                          "ngay_nhap_hoc": "2026-12-01"})
    trang = c.get(f"/lead/{lid}").text
    assert "Viết thư mời tuyển sinh" in trang and "Đã gửi thư mời" in trang
    r = c.post(f"/lead/{lid}/da-gui-thu-moi", data={"csrf": csrf(c, f"/lead/{lid}")}, follow_redirects=False)
    assert r.status_code == 303
    trang = c.get(f"/lead/{lid}").text
    assert "Đã chốt" in trang and "01/03/2027" in trang and "Giới thiệu chương trình đại sứ" in trang


# ------------------------------------------------------------------ lead trùng, lead em

def test_lead_trung_bao_chu_khong_kem_sdt(du_lieu):
    conn = db.ket_noi()
    conn.execute("UPDATE nguoi_dung SET telegram_chat_id = '111' WHERE ten_dang_nhap = 'chu'")
    conn.commit()
    c = dang_nhap("sale1")
    c.post("/lead-moi", data={"csrf": csrf(c, "/lead-moi"), "ten_ph": "Hằng Trùng", "sdt": "0900 000 604"})
    assert len(du_lieu) == 1
    chat, tin = du_lieu[0]
    assert chat == "111" and "Hằng Trùng" in tin and "Hằng Thử" in tin
    assert not re.search(r"\d{3}.?\d{3}.?\d{3}", tin)


def test_lead_em_khong_bi_bao_trung_va_nut_an_sau_khi_tao(du_lieu):
    c = dang_nhap("sale5")
    lid = id_lead("Tú Thử")
    form = {k: v or "" for k, v in _lead("Tú Thử").items() if k in ("ten_ph", "sdt", "ten_be", "tuoi_be", "co_so", "nguon")}
    form.update(csrf=csrf(c, f"/lead/{lid}/sua"), em_nho="Sắp sinh em", ngay_sinh_em="2027-01-15")
    c.post(f"/lead/{lid}/sua", data=form)
    trang = c.get(f"/lead/{lid}").text
    assert "Dừng" in trang and f"/lead-moi?em_cua={lid}" in trang
    moi = c.get(f"/lead-moi?em_cua={lid}").text
    assert "Em nhỏ trong gia đình" in moi and "2027-01-15" in moi
    r = c.post("/lead-moi", data={"csrf": csrf(c, "/lead-moi"), "ten_ph": "Tú Thử", "sdt": _lead("Tú Thử")["sdt"],
                                  "nguon": "Em nhỏ trong gia đình", "ngay_sinh_be": "2027-01-15"}, follow_redirects=False)
    assert du_lieu == []  # không báo trùng
    em = int(r.headers["location"].rsplit("/", 1)[1])
    trang_em = c.get(f"/lead/{em}").text
    assert "Dài hạn" in trang_em and "Bé sắp đủ tuổi nhận học" in trang_em
    assert f"/lead-moi?em_cua={lid}" not in c.get(f"/lead/{lid}").text


# ------------------------------------------------------------------ tin nhắc buổi sáng

def test_tin_sang_cua_sale_khong_co_sdt(du_lieu):
    conn = db.ket_noi()
    ds = dict(nhac_sang.chay(conn, date(2026, 11, 4), thu=True))
    tin = ds["sale3"]
    assert "Lan Thử" in tin and "Quá hạn: Xác nhận lịch tham quan" in tin and "Quang Thử" in tin
    assert "Hoa Thử" not in tin  # lead của sale khác
    for t in ds.values():
        assert "090000" not in t
    assert "Lead bỏ quên" in ds["chu"]


def test_khong_nhac_cuoi_tuan_va_ngay_le(du_lieu):
    conn = db.ket_noi()
    assert nhac_sang.chay(conn, date(2026, 11, 7), thu=True) == []  # thứ 7
    assert nhac_sang.chay(conn, date(2027, 1, 1), thu=True) == []  # Tết Dương lịch (tab ngày nghỉ mẫu)


def test_gui_tin_that_qua_ham_gui(du_lieu):
    conn = db.ket_noi()
    conn.execute("UPDATE nguoi_dung SET telegram_chat_id = '333' WHERE ten_dang_nhap = 'sale3'")
    conn.commit()
    gui = []
    nhac_sang.chay(conn, date(2026, 11, 4), gui=lambda chat, tin: gui.append(chat))
    assert "333" in gui


def test_an_sdt_trong_tin_telegram():
    assert telegram.an_sdt("gọi 0912 345 678 hoặc +84912345678") == "gọi [SĐT] hoặc [SĐT]"


def test_noi_telegram_bang_ma_start(du_lieu):
    conn = db.ket_noi()
    uid = conn.execute("SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sale2'").fetchone()[0]
    ma = telegram.tao_ma_noi(conn, uid)
    so = telegram.xu_ly_cap_nhat(conn, [{"update_id": 1, "message": {"text": "/start sai-ma", "chat": {"id": 9}}},
                                        {"update_id": 2, "message": {"text": f"/start {ma}", "chat": {"id": 42}}}])
    assert so == 1
    r = conn.execute("SELECT telegram_chat_id, telegram_ma FROM nguoi_dung WHERE id = ?", (uid,)).fetchone()
    assert (r[0], r[1]) == ("42", None)


def test_healthz(du_lieu):
    assert TestClient(app).get("/healthz").text == "ok"


# ------------------------------------------------------------------ lỗi reviewer tìm ra (đợt A)

def test_ngay_vo_ly_bi_tu_choi_khong_lam_sap(du_lieu):
    c = dang_nhap("sale1")
    lid = id_lead("Hoa Thử")
    for o, ngay in (("ngay_nhap_hoc", "9999-12-31"), ("ngay_nhap_hoc", "0001-01-01")):
        r = c.post(f"/lead/{lid}/ghi-nhan", data={"csrf": csrf(c, f"/lead/{lid}/ghi-nhan"), "phuong_thuc": "Gọi điện",
                                                  "tinh_trang": "Đã đặt cọc", "muc_quan_tam": "Rất quan tâm",
                                                  "da_gui_thu_moi": "1", o: ngay})
        assert r.status_code == 400 and "Ngày" in r.text
    r = c.post(f"/lead/{lid}/ghi-nhan", data={"csrf": csrf(c, f"/lead/{lid}/ghi-nhan"), "phuong_thuc": "Gọi điện",
                                              "tinh_trang": "Đã hẹn tham quan / học thử", "muc_quan_tam": "Rất quan tâm",
                                              "ngay_hen_tham_quan": "0001-01-01"})
    assert r.status_code == 400
    assert c.get("/cua-toi").status_code == 200
    assert dang_nhap("chu").get("/tat-ca").status_code == 200


def test_ngay_29_thang_2_khong_loi(du_lieu, monkeypatch):
    monkeypatch.setattr(dongho, "GIO_CO_DINH", datetime(2028, 2, 29, 9, 0))
    assert dang_nhap("sale6").get("/cua-toi").status_code == 200  # Thu Thử: dài hạn, không có hạn
    assert dang_nhap("chu").get("/tat-ca").status_code == 200


def test_nguon_em_nho_go_tay_van_bao_trung_khac_sale(du_lieu):
    conn = db.ket_noi()
    conn.execute("UPDATE nguoi_dung SET telegram_chat_id = '111' WHERE ten_dang_nhap = 'chu'")
    conn.commit()
    c = dang_nhap("sale1")
    c.post("/lead-moi", data={"csrf": csrf(c, "/lead-moi"), "ten_ph": "Lan Giả", "sdt": "0900000601",
                              "nguon": "Em nhỏ trong gia đình"})
    assert len(du_lieu) == 1 and "Lan Thử" in du_lieu[0][1]


def test_sua_sdt_thanh_so_trung_bao_chu(du_lieu):
    conn = db.ket_noi()
    conn.execute("UPDATE nguoi_dung SET telegram_chat_id = '111' WHERE ten_dang_nhap = 'chu'")
    conn.commit()
    c = dang_nhap("sale1")
    lid = id_lead("Hoa Thử")
    form = {k: v or "" for k, v in _lead("Hoa Thử").items() if k in ("ten_ph", "ten_be", "tuoi_be", "co_so", "nguon")}
    form.update(csrf=csrf(c, f"/lead/{lid}/sua"), sdt="0900000601")
    c.post(f"/lead/{lid}/sua", data=form)
    assert len(du_lieu) == 1 and "Lan Thử" in du_lieu[0][1]
    form.update(ghi_chu="sửa lần hai, SĐT không đổi")
    c.post(f"/lead/{lid}/sua", data=form)
    assert len(du_lieu) == 1  # không báo lại khi SĐT không đổi


def test_chu_sua_lead_cua_sale_da_nghi_khong_mat_nguoi_phu_trach(du_lieu):
    conn = db.ket_noi()
    conn.execute("UPDATE nguoi_dung SET dang_lam = 0 WHERE ten_dang_nhap = 'sale1'")
    conn.commit()
    trang = dang_nhap("chu").get(f"/lead/{id_lead('Hoa Thử')}/sua").text
    sale1 = conn.execute("SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sale1'").fetchone()[0]
    assert re.search(rf'<option value="{sale1}" selected', trang)


def test_tin_dai_duoc_chia_nho():
    gui = []
    import app.telegram as tg
    phan = tg.chia_tin("\n".join(f"- Phụ huynh số {i} (bé Thử), Quá hạn: Gọi lại" for i in range(300)))
    assert len(phan) > 1 and all(len(p) <= 4000 for p in phan)


def test_an_sdt_nhieu_kieu_viet():
    for s in ("(091) 234 5678", "912345678", "0912 - 345 - 678", "+84 (91) 234 5678"):
        assert not re.search(r"\d{3}", telegram.an_sdt(f"Chị Lan {s}").replace("[SĐT]", "")), s
    assert telegram.an_sdt("Quá hạn 12 ngày, nhận 04/11") == "Quá hạn 12 ngày, nhận 04/11"


def test_an_sdt_dau_ngan_khac():
    for s in ("0912 345 678", "0912,345,678", "0912_345_678", "0912–345–678"):
        assert "345" not in telegram.an_sdt(f"PH Lan {s} hỏi"), repr(s)
    assert telegram.an_sdt("Quá hạn 12 ngày\n04/11/2026") == "Quá hạn 12 ngày\n04/11/2026"


def test_ngay_sai_o_bi_an_khong_chan_luu(du_lieu):
    c = dang_nhap("sale3")
    lead = id_lead("Lan Thử")
    r = c.post(f"/lead/{lead}/ghi-nhan", data={
        "csrf": csrf(c, f"/lead/{lead}/ghi-nhan"), "phuong_thuc": "Gọi điện", "tinh_trang": "Đang cân nhắc",
        "muc_quan_tam": "Hời hợt", "hen_lai_sau": "1 tuần", "ngay_nhap_hoc": "20277-01-01"}, follow_redirects=False)
    assert r.status_code == 303, r.text


def test_ngay_sai_o_dang_hien_van_bao_loi(du_lieu):
    c = dang_nhap("sale3")
    lead = id_lead("Lan Thử")
    goc = {"phuong_thuc": "Gọi điện", "muc_quan_tam": "Hời hợt"}
    for them in ({"tinh_trang": "Yêu cầu gọi lại sau", "hen_lai_sau": "Chọn ngày", "ngay_hen_goi_lai": "20277-01-01"},
                 {"tinh_trang": "Đã hẹn tham quan / học thử", "ngay_hen_tham_quan": "20277-01-01"},
                 {"tinh_trang": "Đã đặt cọc", "ngay_nhap_hoc": "20277-01-01"}):
        r = c.post(f"/lead/{lead}/ghi-nhan", data={"csrf": csrf(c, f"/lead/{lead}/ghi-nhan"), **goc, **them})
        assert r.status_code == 400 and "không hợp lệ" in r.text, them


def test_ngay_sinh_em_sai_o_bi_an_khong_chan_luu_lead(du_lieu):
    c = dang_nhap("sale3")
    lead = id_lead("Lan Thử")
    r = _lead("Lan Thử")
    data = {"csrf": csrf(c, f"/lead/{lead}/sua"), "ten_ph": r["ten_ph"], "sdt": r["sdt"], "em_nho": "Không",
            "ngay_sinh_em": "20277-01-01"}
    assert c.post(f"/lead/{lead}/sua", data=data, follow_redirects=False).status_code == 303
    data["em_nho"] = "Có em nhỏ"
    assert c.post(f"/lead/{lead}/sua", data=data, follow_redirects=False).status_code == 400


def test_an_sdt_dau_tru_toan_hoc():
    assert "345" not in telegram.an_sdt("0912\u2212345\u2212678")
