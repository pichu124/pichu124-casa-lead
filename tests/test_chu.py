"""Màn của chủ (đợt B): phân quyền, nhắc sale, gửi ưu đãi / thông tin, báo cáo, cài đặt, xuất CSV, báo được giao lead.
Dữ liệu là dữ liệu mẫu (giả)."""

import csv
import io
import re

import pytest

from app import db, quy_tac_nhac as q
from tests.conftest import csrf, dang_nhap, id_lead

TRANG_CHU = ["/chu", "/chu/bo-quen", "/chu/rat-quan-tam", "/chu/theo-sale", "/chu/gui/uu-dai", "/chu/gui/thong-tin",
             "/chu/bao-cao", "/chu/cai-dat", "/chu/xuat/ho-so-lead.csv", "/chu/xuat/cham-soc.csv"]


def _sql(sql, tham=()):
    conn = db.ket_noi()
    try:
        r = conn.execute(sql, tham).fetchall()
        conn.commit()
        return r
    finally:
        conn.close()


def _noi_telegram(ten_dang_nhap, chat):
    _sql("UPDATE nguoi_dung SET telegram_chat_id = ? WHERE ten_dang_nhap = ?", (chat, ten_dang_nhap))


def _ten_trong(html):
    return re.findall(r"<strong>(?:⚠ )?([^<]+)</strong>", html)


@pytest.mark.parametrize("url", TRANG_CHU)
def test_sale_khong_vao_duoc_man_cua_chu(du_lieu, url):
    assert dang_nhap("sale1").get(url).status_code == 403


def test_sale_khong_post_duoc_man_cua_chu(du_lieu):
    c = dang_nhap("sale1")
    ma = csrf(c, "/tai-khoan")
    lead = id_lead("Đào Thử")
    for url, data in [(f"/chu/nhac-sale/{lead}", {}), ("/chu/gui/uu-dai", {"lead_id": lead}),
                      ("/chu/cai-dat", {"viec": "cau_hinh", "ch_L1": "9"})]:
        assert c.post(url, data={"csrf": ma, **data}, follow_redirects=False).status_code == 403
    assert _sql("SELECT gia_tri FROM cau_hinh WHERE khoa = 'L1'")[0][0] == 1
    assert not _sql("SELECT * FROM gui_thong_tin")


@pytest.mark.parametrize("url", TRANG_CHU)
def test_chu_mo_duoc_moi_man(du_lieu, url):
    assert dang_nhap("chu").get(url).status_code == 200


def test_bo_quen_chi_gom_lead_dang_cham_soc_qua_han(du_lieu):
    html = dang_nhap("chu").get("/chu/bo-quen").text
    ten = _ten_trong(html)
    assert "Đào Thử" in ten  # hẹn gọi lại 18/10, hôm nay 04/11
    assert "Long Thử" not in ten  # dài hạn, không phải bỏ quên


def test_rat_quan_tam_bo_lead_da_dat_coc(du_lieu):
    ten = _ten_trong(dang_nhap("chu").get("/chu/rat-quan-tam").text)
    assert "Lan Thử" in ten
    assert "Hằng Thử" not in ten  # lần cuối Đã đặt cọc: chỉ còn chờ thư mời, không cần gọi kèm


def test_nhac_sale_gui_telegram_cho_dung_sale_khong_kem_sdt(du_lieu):
    _noi_telegram("sale1", "111")
    c = dang_nhap("chu")
    lead = id_lead("Đào Thử")
    r = c.post(f"/chu/nhac-sale/{lead}", data={"csrf": csrf(c, "/chu/bo-quen"), "quay_ve": "/chu/bo-quen"},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/chu/bo-quen?")
    assert len(du_lieu) == 1 and du_lieu[0][0] == "111"
    tin = du_lieu[0][1]
    assert "Đào Thử" in tin and "Quá hạn" in tin
    sdt = _sql("SELECT sdt FROM lead WHERE id = ?", (lead,))[0][0]
    assert sdt not in tin
    assert _sql("SELECT chu_nhac_luc FROM lead WHERE id = ?", (lead,))[0][0]
    assert "Đã nhắc" in c.get("/chu/bo-quen").text


def test_nhac_sale_khong_chuyen_huong_ra_ngoai(du_lieu):
    c = dang_nhap("chu")
    r = c.post(f"/chu/nhac-sale/{id_lead('Đào Thử')}",
               data={"csrf": csrf(c, "/chu/bo-quen"), "quay_ve": "https://vi-du.invalid/"}, follow_redirects=False)
    assert r.headers["location"].startswith("/chu/bo-quen?")


def test_gui_uu_dai_danh_dau_roi_bien_khoi_danh_sach(du_lieu):
    c = dang_nhap("chu")
    assert "Hoa Thử" in _ten_trong(c.get("/chu/gui/uu-dai").text)
    lead = id_lead("Hoa Thử")
    r = c.post("/chu/gui/uu-dai", data={"csrf": csrf(c, "/chu/gui/uu-dai"), "lead_id": [str(lead), "999999"]})
    assert "Đã ghi 1 phụ huynh đã gửi." in r.text
    assert "Hoa Thử" not in _ten_trong(r.text)  # vừa gửi, chưa đủ số ngày cách nhau
    g = _sql("SELECT loai FROM gui_thong_tin WHERE lead_id = ?", (lead,))
    assert [x[0] for x in g] == [q.GUI_UU_DAI]
    assert not du_lieu  # app không tự nhắn ai


def test_gui_thong_tin_chi_lead_dai_han(du_lieu):
    html = dang_nhap("chu").get("/chu/gui/thong-tin").text
    assert "Long Thử" in _ten_trong(html)
    giai_doan = re.findall(r"<div class=\"nho\">[^·<]*· ([^·<]+?) ·", html)
    assert giai_doan and set(giai_doan) == {q.GD_DAI_HAN}


def test_kieu_gui_la_thi_404(du_lieu):
    assert dang_nhap("chu").get("/chu/gui/linh-tinh").status_code == 404


def test_bao_cao_dem_dung_lead_moi_cua_thang(du_lieu):
    c = dang_nhap("chu")
    for thang in ("2026-10", "2026-11"):
        mong = _sql("SELECT COUNT(*) FROM lead WHERE substr(ngay_nhan, 1, 7) = ?", (thang,))[0][0]
        html = c.get(f"/chu/bao-cao?thang={thang}").text
        assert re.search(rf"<td>Lead mới</td><td>{mong}</td>", html), thang
    assert c.get("/chu/bao-cao?thang=linh-tinh").status_code == 200


def test_cai_dat_luu_so_ngay_va_bo_o_sai(du_lieu):
    c = dang_nhap("chu")
    r = c.post("/chu/cai-dat", data={"csrf": csrf(c, "/chu/cai-dat"), "viec": "cau_hinh", "ch_L1": "2", "ch_L2": "-5"})
    assert "Bỏ qua ô không hợp lệ: L2" in r.text
    assert _sql("SELECT gia_tri FROM cau_hinh WHERE khoa = 'L1'")[0][0] == 2
    assert _sql("SELECT gia_tri FROM cau_hinh WHERE khoa = 'L2'")[0][0] == 3


def test_cai_dat_ngay_nghi_them_bo_va_tu_choi_ngay_vo_ly(du_lieu):
    c = dang_nhap("chu")
    ma = csrf(c, "/chu/cai-dat")
    r = c.post("/chu/cai-dat", data={"csrf": ma, "viec": "them_ngay_nghi", "ngay": "2026-12-24", "ten": "Nghỉ thử"})
    assert "Đã thêm ngày nghỉ 24/12/2026" in r.text
    assert _sql("SELECT ten FROM ngay_nghi WHERE ngay = '2026-12-24'")[0][0] == "Nghỉ thử"
    for sai in ("9999-12-31", "abc"):
        r = c.post("/chu/cai-dat", data={"csrf": ma, "viec": "them_ngay_nghi", "ngay": sai})
        assert r.status_code == 200 and "Ngày nghỉ không hợp lệ" in r.text
    c.post("/chu/cai-dat", data={"csrf": ma, "viec": "bo_ngay_nghi", "ngay": "2026-12-24"})
    assert not _sql("SELECT * FROM ngay_nghi WHERE ngay = '2026-12-24'")


def test_cai_dat_danh_muc_them_bo(du_lieu):
    c = dang_nhap("chu")
    ma = csrf(c, "/chu/cai-dat")
    c.post("/chu/cai-dat", data={"csrf": ma, "viec": "them_danh_muc", "loai": "Nguồn", "gia_tri": "Tờ rơi"})
    assert "Tờ rơi" in db.danh_muc(db.ket_noi(), "Nguồn")
    assert "Tờ rơi" in c.get("/lead-moi").text
    c.post("/chu/cai-dat", data={"csrf": ma, "viec": "them_danh_muc", "loai": "Tình trạng", "gia_tri": "X"})
    assert not _sql("SELECT * FROM danh_muc WHERE loai = 'Tình trạng'")  # loại cố định trong mã
    c.post("/chu/cai-dat", data={"csrf": ma, "viec": "bo_danh_muc", "loai": "Nguồn", "gia_tri": "Tờ rơi"})
    assert "Tờ rơi" not in db.danh_muc(db.ket_noi(), "Nguồn")


def test_xuat_csv_dung_cot_cua_sheet_cu(du_lieu):
    c = dang_nhap("chu")
    for ten, cot, bang in (("ho-so-lead", q.COT_HO_SO, "lead"), ("cham-soc", q.COT_CHAM_SOC, "cham_soc")):
        r = c.get(f"/chu/xuat/{ten}.csv")
        assert r.text.startswith("﻿") and "attachment" in r.headers["content-disposition"]
        hang = list(csv.reader(io.StringIO(r.text.lstrip("﻿"))))
        assert hang[0] == cot
        assert len(hang) - 1 == _sql(f"SELECT COUNT(*) FROM {bang}")[0][0]
        assert all(len(h) == len(cot) for h in hang)
    assert c.get("/chu/xuat/linh-tinh.csv").status_code == 404


def test_chu_giao_lead_cho_sale_thi_sale_nhan_telegram(du_lieu):
    _noi_telegram("sale2", "222")
    c = dang_nhap("chu")
    lead = id_lead("Đào Thử")
    form = c.get(f"/lead/{lead}/sua").text
    sale2 = _sql("SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sale2'")[0][0]
    r = _sql("SELECT * FROM lead WHERE id = ?", (lead,))[0]
    data = {"csrf": re.search(r'name="csrf" value="([^"]+)"', form).group(1), "ten_ph": r["ten_ph"], "sdt": r["sdt"],
            "ten_be": r["ten_be"], "co_so": r["co_so"], "nguon": r["nguon"], "sale_id": str(sale2)}
    c.post(f"/lead/{lead}/sua", data=data)
    assert [x[0] for x in du_lieu] == ["222"]
    assert "Đào Thử" in du_lieu[0][1] and r["sdt"] not in du_lieu[0][1]
    du_lieu.clear()
    c.post(f"/lead/{lead}/sua", data=data)  # lưu lại mà không đổi sale: không báo nữa
    assert not du_lieu


def test_thanh_duoi_cua_chu_co_quan_tri(du_lieu):
    assert 'href="/chu"' in dang_nhap("chu").get("/hom-nay").text
    assert 'href="/chu"' not in dang_nhap("sale1").get("/hom-nay").text


# ------------------------------------------------------------------ các lỗi reviewer đợt B tìm ra

def test_cai_dat_tu_choi_dau_nam_hoc_vo_ly_khong_lam_sap(du_lieu):
    c = dang_nhap("chu")
    ma = csrf(c, "/chu/cai-dat")
    for thang, ngay in (("13", "1"), ("0", "1"), ("6", "31"), ("2", "30")):
        r = c.post("/chu/cai-dat", data={"csrf": ma, "viec": "cau_hinh", "ch_Đầu năm học tháng": thang,
                                         "ch_Đầu năm học ngày": ngay})
        assert "không hợp lệ" in r.text, (thang, ngay)
    assert [x[0] for x in _sql("SELECT gia_tri FROM cau_hinh WHERE khoa LIKE 'Đầu năm học%' ORDER BY khoa DESC")] == [7, 1]
    c.post("/chu/cai-dat", data={"csrf": ma, "viec": "cau_hinh", "ch_Ưu đãi tối đa": "0", "ch_Chưa liên lạc tối đa": "0"})
    assert _sql("SELECT gia_tri FROM cau_hinh WHERE khoa = 'Ưu đãi tối đa'")[0][0] == 2
    for url in ("/tat-ca", "/chu/bo-quen", "/chu/gui/uu-dai"):
        assert c.get(url).status_code == 200


def _gui_lai_bieu_mau(c, url):
    """Gửi lại biểu mẫu y như trình duyệt: ô chọn đang chọn gì, ô đánh dấu đang đánh dấu gì."""
    html = c.get(url).text
    form = re.search(r'<form class="hop bieu-mau" method="post" action="([^"]+)">(.*?)</form>', html, re.S)
    data = []
    for m in re.finditer(r"<input ([^>]*)>", form.group(2)):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        loai = a.get("type", "text")
        if "name" not in a or (loai in ("checkbox", "radio") and " checked" not in m.group(1) + " "):
            continue
        data.append((a["name"], a.get("value", "")))
    for m in re.finditer(r'<select name="(\w+)"[^>]*>(.*?)</select>', form.group(2), re.S):
        chon = re.search(r"<option([^>]*)\bselected\b[^>]*>([^<]*)", m.group(2))
        if chon:
            val = re.search(r'value="([^"]*)"', chon.group(1))
            data.append((m.group(1), val.group(1) if val else chon.group(2).strip()))
    for m in re.finditer(r'<textarea name="(\w+)"[^>]*>(.*?)</textarea>', form.group(2), re.S):
        data.append((m.group(1), m.group(2)))
    gop: dict[str, list[str]] = {}
    for k, v in data:
        gop.setdefault(k, []).append(v)
    return c.post(form.group(1), data=gop)


def test_bo_lua_chon_danh_muc_khong_xoa_gia_tri_cua_lead_cu(du_lieu):
    lead = id_lead("Hoa Thử")
    _sql("UPDATE lead SET ph_quan_tam = 'Học phí', chat_luong = 'Trung bình', ly_do_chat_luong = 'Ở xa' WHERE id = ?", (lead,))
    cu = dict(_sql("SELECT * FROM lead WHERE id = ?", (lead,))[0])
    c = dang_nhap("chu")
    ma = csrf(c, "/chu/cai-dat")
    for loai, gia_tri in (("Cơ sở", cu["co_so"]), ("Nguồn", cu["nguon"]), ("Mối quan tâm", "Học phí"),
                          ("Lý do chất lượng", "Ở xa")):
        c.post("/chu/cai-dat", data={"csrf": ma, "viec": "bo_danh_muc", "loai": loai, "gia_tri": gia_tri})
    assert "(đã bỏ)" in c.get(f"/lead/{lead}/sua").text
    r = _gui_lai_bieu_mau(c, f"/lead/{lead}/sua")
    assert r.status_code == 200, r.text
    moi = dict(_sql("SELECT * FROM lead WHERE id = ?", (lead,))[0])
    for k in ("co_so", "nguon", "ph_quan_tam", "ly_do_chat_luong", "sale_id"):
        assert moi[k] == cu[k], k


def test_nhac_sale_da_nghi_khong_gui_telegram(du_lieu):
    _noi_telegram("sale1", "111")
    _sql("UPDATE nguoi_dung SET dang_lam = 0 WHERE ten_dang_nhap = 'sale1'")
    c = dang_nhap("chu")
    r = c.post(f"/chu/nhac-sale/{id_lead('Đào Thử')}", data={"csrf": csrf(c, "/chu/bo-quen"), "quay_ve": "/chu/bo-quen"})
    assert not du_lieu
    assert "đã nghỉ" in r.text


def test_cho_nghi_viec_thi_go_noi_telegram(du_lieu):
    _noi_telegram("sale1", "111")
    c = dang_nhap("chu")
    uid = _sql("SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sale1'")[0][0]
    c.post(f"/quan-tri/nguoi-dung/{uid}", data={"csrf": csrf(c, "/quan-tri/nguoi-dung"), "viec": "nghi"})
    assert _sql("SELECT telegram_chat_id FROM nguoi_dung WHERE id = ?", (uid,))[0][0] is None


def test_theo_sale_hien_sale_da_nghi_con_giu_lead(du_lieu):
    _sql("UPDATE nguoi_dung SET dang_lam = 0 WHERE ten_dang_nhap = 'sale1'")
    assert "Sale 1 (đã nghỉ)" in dang_nhap("chu").get("/chu/theo-sale").text


def test_gui_uu_dai_khong_ghi_trung(du_lieu):
    c = dang_nhap("chu")
    lead = str(id_lead("Hoa Thử"))
    ma = csrf(c, "/chu/gui/uu-dai")
    c.post("/chu/gui/uu-dai", data={"csrf": ma, "lead_id": [lead, lead]})
    c.post("/chu/gui/uu-dai", data={"csrf": ma, "lead_id": [lead]})
    assert len(_sql("SELECT * FROM gui_thong_tin WHERE lead_id = ?", (lead,))) == 1


def test_xuat_cham_soc_co_lan_thu_va_han_lien_he_tiep(du_lieu):
    from app import logic
    hang = list(csv.DictReader(io.StringIO(dang_nhap("chu").get("/chu/xuat/cham-soc.csv").text.lstrip("\ufeff"))))
    conn = db.ket_noi()
    ch, nghi = logic.cau_hinh(conn), logic.ngay_nghi(conn)
    lan = {r["id"]: (r["lead_id"], logic.lan_cham_soc(r)) for r in conn.execute("SELECT * FROM cham_soc")}
    conn.close()
    for h in hang:
        lead, c = lan[int(h["Mã"])]
        truoc = [x for i, (l, x) in lan.items() if l == lead and i != int(h["Mã"])]
        han = q.han_lien_he_tiep(c, truoc, ch, nghi)
        assert h["Lần thứ"] == str(q.lan_thu(truoc, c))
        assert h["Hạn liên hệ tiếp"] == (han.isoformat() if han else "")
    assert max(int(h["Lần thứ"]) for h in hang) >= 2
    assert any(h["Hạn liên hệ tiếp"] and h["Hạn liên hệ tiếp"] != h["Thời gian"][:10] for h in hang)


def test_chu_giao_lead_cho_sale_da_nghi_khong_gui(du_lieu):
    from app.main import _bao_duoc_giao
    _noi_telegram("sale2", "222")
    _sql("UPDATE nguoi_dung SET dang_lam = 0 WHERE ten_dang_nhap = 'sale2'")
    lead = id_lead("Đào Thử")
    _sql("UPDATE lead SET sale_id = (SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sale2') WHERE id = ?", (lead,))
    _bao_duoc_giao(lead, "Chủ")
    assert not du_lieu


def test_cai_dat_so_khong_phai_ascii_khong_loi(du_lieu):
    c = dang_nhap("chu")
    r = c.post("/chu/cai-dat", data={"csrf": csrf(c, "/chu/cai-dat"), "viec": "cau_hinh", "ch_L1": "²"})
    assert r.status_code == 200 and "Bỏ qua ô không hợp lệ: L1" in r.text


def test_xuat_csv_khong_de_o_thanh_cong_thuc(du_lieu):
    lead = id_lead("Hoa Thử")
    _sql("UPDATE lead SET ten_ph = '=HYPERLINK(\"x\")', ghi_chu = '@cmd', sdt = '+84 900 000 602' WHERE id = ?", (lead,))
    hang = list(csv.DictReader(io.StringIO(dang_nhap("chu").get("/chu/xuat/ho-so-lead.csv").text.lstrip("﻿"))))
    h = next(x for x in hang if x["Mã lead"] == str(lead))
    assert h["Tên phụ huynh"] == "'=HYPERLINK(\"x\")" and h["Ghi chú"] == "'@cmd"
    assert h["SĐT"] == "+84 900 000 602"
