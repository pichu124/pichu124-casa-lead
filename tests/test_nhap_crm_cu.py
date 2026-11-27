"""Script nhập phụ huynh từ CSV của CRM Google Sheets cũ (bước 5). Dữ liệu giả, bố cục giống trang ContactDetails."""

import csv

from app import db
from scripts import nhap_crm_cu

TIEU_DE = ["", "STT", "Ngày phụ huynh quan tâm", "Tên phụ huynh", "Tên bé", "Lặp", "Đổ tuổi", "Fanpage", "Phone",
           "Email", "Địa chỉ", "Quan tâm cơ sở", "Nguồn khách hàng", "Thời gian nhập học dự kiến",
           "Câu hỏi/ Quan tâm/lưu ý", "Phân sale", "Notes"]


def _tep(tmp_path, *hang):
    p = tmp_path / "crm.csv"
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerows([["", "", "", "CONTACT DETAILS"], ["", "", "", "[CASA DEI BAMBINI]"], [], [],
                     ["", "", "", "THÔNG TIN KHÁCH HÀNG"], TIEU_DE, []])
        for h in hang:
            w.writerow(h)
    return p


def _h(ngay, ten, sdt, co_so="KM", nguon="CCFVN", tuoi="", sale="", email="", notes=""):
    return ["", "", ngay, ten, "Bé Thử", "1", tuoi, "", sdt, email, "", co_so, nguon, "", "Openday", sale, notes]


def test_chay_thu_khong_ghi_va_khong_in_ten_sdt(du_lieu, tmp_path, capsys):
    p = _tep(tmp_path, _h("8/4/2026", "Cũ Một Thử", "0914000001"))
    conn = db.ket_noi()
    truoc = conn.execute("SELECT COUNT(*) FROM lead").fetchone()[0]
    assert nhap_crm_cu.main([str(p)]) == 0
    assert conn.execute("SELECT COUNT(*) FROM lead").fetchone()[0] == truoc
    ra = capsys.readouterr().out
    assert "sẽ nhập: 1" in ra and "CHẠY THỬ" in ra
    assert "Cũ Một Thử" not in ra and "0914000001" not in ra


def test_ghi_that_doi_ma_va_tam_dung(du_lieu, tmp_path):
    conn = db.ket_noi()
    for g in ("Đối tác",):
        conn.execute("INSERT OR IGNORE INTO danh_muc (loai, gia_tri, thu_tu) VALUES ('Nguồn', ?, 99)", (g,))
    sale = conn.execute("SELECT ten FROM nguoi_dung WHERE vai_tro = 'sale' ORDER BY id").fetchone()[0]
    conn.commit()
    p = _tep(tmp_path,
             _h("8/4/2026", "Cũ Một Thử", "0914000001", "HK+KM", "CCFVN", "20/11/2023", sale, "a@thu.vn"),
             _h("9/4/2026", "Cũ Hai Thử", "0914000002", "FLC", "Zalo Oa", "Gần 1t"),
             _h("10/4/2026", "Cũ Ba Thử", "0914000003", "Chưa rõ", "Hotline tuyển sinh", email="sai-dang"),
             _h("10/4/2026", "Cũ Bốn Thử", "0914000001"),        # trùng SĐT trong tệp
             _h("", "Cũ Năm Thử", "0914000005"),                 # thiếu ngày
             _h("11/4/2026", "Cũ Sáu Thử", "123"))               # SĐT sai
    assert nhap_crm_cu.main([str(p), "--ghi"]) == 0
    r = {x["ten_ph"]: x for x in conn.execute("SELECT * FROM lead WHERE ghi_chu LIKE '[Nhập từ CRM cũ%'")}
    assert set(r) == {"Cũ Một Thử", "Cũ Hai Thử", "Cũ Ba Thử"}
    mot = r["Cũ Một Thử"]
    assert mot["co_so"] == "Chùa Láng, Kim Mã" and mot["nguon"] == "Đối tác" and mot["chien_dich"] == "CCFVN"
    assert mot["ngay_nhan"] == "2026-04-08 08:00:00" and mot["ngay_sinh_be"] == "2023-11-20"
    assert mot["sale_id"] is not None and mot["email"] == "a@thu.vn" and mot["tam_dung"] == 1
    assert r["Cũ Hai Thử"]["nguon"] == "Zalo" and r["Cũ Hai Thử"]["co_so"] == "Mỹ Đình" and r["Cũ Hai Thử"]["sale_id"] is None
    ba = r["Cũ Ba Thử"]
    assert ba["nguon"] == "" and ba["co_so"] == "" and ba["email"] == ""
    assert "hotline" in ba["ghi_chu"] and "sai-dang" in ba["ghi_chu"]
    # chạy lại không nhập trùng
    assert nhap_crm_cu.main([str(p), "--ghi"]) == 0
    assert conn.execute("SELECT COUNT(*) FROM lead WHERE ghi_chu LIKE '[Nhập từ CRM cũ%'").fetchone()[0] == 3


def test_nhan_ca_ban_chep_co_ten_co_so_day_du():
    assert nhap_crm_cu.doi_co_so("Chùa Láng + Mỹ Đình", ["Chùa Láng", "Mỹ Đình", "Kim Mã"]) == "Chùa Láng, Mỹ Đình"
    assert nhap_crm_cu.doi_nguon("Zalo / Zalo OA", ["Zalo"])[0] == "Zalo"
    assert nhap_crm_cu.doi_nguon("Kiddi Hub", ["Zalo"]) == ("", "Kiddi Hub", "")  # chưa có "Đối tác" trong danh mục
    assert nhap_crm_cu.doi_nguon("TikTok", ["Khác"]) == ("Khác", "TikTok", "")
