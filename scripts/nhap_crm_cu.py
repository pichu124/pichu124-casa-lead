#!/usr/bin/env python3
"""Nhập phụ huynh từ tệp CRM Google Sheets cũ ("2026 CRM MARKETING", trang ContactDetails) vào app.

    python scripts/nhap_crm_cu.py /duong/dan/crm.csv          # CHẠY THỬ: chỉ in số đếm, không ghi gì
    python scripts/nhap_crm_cu.py /duong/dan/crm.csv --ghi    # ghi thật (nên sao lưu trước: scripts/sao_luu.py)

Tệp CSV: mở Google Sheet, chọn trang cần nhập, Tệp → Tải xuống → CSV. Nhận cả trang ContactDetails(MKT) của
tệp gốc (mã cơ sở HK/KM/FLC) lẫn trang "Khách hàng" của bản chép 26/11/2026 (tên cơ sở đầy đủ). Script tự tìm
hàng tiêu đề (hàng có "Tên phụ huynh" và "Phone"); các hàng tiêu đề, trống phía trên bị bỏ qua.

Quy tắc (người phụ trách dự án duyệt 27/11/2026):
- Cơ sở: HK → Chùa Láng, KM → Kim Mã, FLC → Mỹ Đình; "HK+KM" → hai cơ sở; "Chưa rõ" → để trống.
- Nguồn: CCFVN, Kiddi Hub, Huyền Chibi → "Đối tác", tên đối tác vào ô Chiến dịch. "Zalo Oa" → "Zalo".
  "Hotline tuyển sinh", "Chưa hỏi", trống → để trống (ghi chú "Liên hệ qua hotline" nếu có). Nguồn khác có trong
  danh mục thì giữ, không có thì "Khác" + tên cũ vào Chiến dịch. Nguồn không có trong danh mục lúc nhập thì để trống.
- Ngày nhận = "Ngày phụ huynh quan tâm" (8:00). Hàng thiếu ngày, thiếu tên hoặc SĐT dưới 9 chữ số: bỏ qua, có đếm.
- Sale phụ trách: khớp cột "Phân sale" với tên tài khoản trong app (bỏ dấu, không phân biệt hoa thường); không
  khớp đúng một người thì để chưa giao.
- **Tạm dừng nhắc** (lead cũ không làm ngập tab Hôm nay của sale); chủ bật lại từng lead nếu muốn chăm sóc tiếp.
  Thêm --nhac để không tạm dừng.
- SĐT đã có trong app (hoặc lặp trong tệp): bỏ qua, chỉ nhập lần đầu gặp. Chạy lại script không nhập trùng.
- Cột còn lại (Fanpage, Địa chỉ, Câu hỏi, Thời gian nhập học dự kiến, Notes) gộp vào Ghi chú.

Script chỉ in SỐ ĐẾM, không bao giờ in tên hay SĐT phụ huynh. Tệp CSV chứa dữ liệu cá nhân: xoá sau khi nhập,
không chép vào kho mã.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, logic  # noqa: E402
from app.dongho import bay_gio, ghi_gio  # noqa: E402

DOI_TAC = {"ccfvn": "CCFVN", "kiddi hub": "Kiddi Hub", "huyen chibi": "Huyền Chibi"}
MA_CO_SO = {"hk": "Chùa Láng", "chua lang": "Chùa Láng", "km": "Kim Mã", "kim ma": "Kim Mã",
            "flc": "Mỹ Đình", "my dinh": "Mỹ Đình"}
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
NGAY = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")


def bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower()).replace("đ", "d")
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()


def doc_ngay(s: str) -> date | None:
    m = NGAY.match(s or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


# Tên cột trong app → các tên tiêu đề có thể gặp (đã bỏ dấu). Khớp khi tiêu đề BẮT ĐẦU bằng một tên ở đây.
COT = {
    "ngay": ["ngay phu huynh quan tam"], "ten_ph": ["ten phu huynh"], "ten_be": ["ten be"],
    "tuoi": ["do tuoi", "đo tuoi"], "fanpage": ["fanpage"], "sdt": ["phone", "sdt"], "email": ["email"],
    "dia_chi": ["dia chi"], "co_so": ["quan tam co so"], "nguon": ["nguon khach hang"],
    "nguon_goc": ["nguon ghi o tep goc"], "kenh": ["kenh lien he"], "nhap_hoc": ["thoi gian nhap hoc"],
    "cau_hoi": ["cau hoi"], "sale": ["phan sale"], "notes": ["notes"],
}


def tim_tieu_de(hang: list[list[str]]) -> tuple[int, dict[str, int]] | None:
    for i, h in enumerate(hang):
        ten = [bo_dau(x) for x in h]
        if "ten phu huynh" in ten and ("phone" in ten or "sdt" in ten):
            vi_tri = {}
            for khoa, mau in COT.items():
                for j, t in enumerate(ten):
                    if khoa not in vi_tri and any(t.startswith(bo_dau(m)) for m in mau):
                        vi_tri[khoa] = j
            return i, vi_tri
    return None


def doi_co_so(chu: str, ds_co_so: list[str]) -> str:
    chon = set()
    for phan in re.split(r"[+,;/]", chu or ""):
        ten = MA_CO_SO.get(bo_dau(phan))
        if ten:
            chon.add(ten)
    return ", ".join(c for c in ds_co_so if c in chon)


def doi_nguon(chu: str, ds_nguon: list[str]) -> tuple[str, str, str]:
    """(nguồn trong danh mục, chiến dịch, ghi chú thêm) từ nguồn ghi ở CRM cũ."""
    k = bo_dau(chu)
    nguon, chien_dich, ghi = "", "", ""
    if k in DOI_TAC:
        nguon, chien_dich = "Đối tác", DOI_TAC[k]
    elif k.startswith("zalo"):
        nguon = "Zalo"
    elif k.startswith("hotline"):
        ghi = "Liên hệ qua hotline (CRM cũ chưa hỏi biết Casa qua đâu)."
    elif k in ("", "nguon kh", "chua hoi"):
        pass
    elif chu.strip() in ds_nguon:
        nguon = chu.strip()
    else:
        nguon, chien_dich = "Khác", chu.strip()
    if nguon and nguon not in ds_nguon:
        nguon = ""
    return nguon, chien_dich, ghi


def khop_sale(chu: str, sale: list[tuple[int, str]]) -> int | None:
    k = bo_dau(chu)
    if not k:
        return None
    dung = [i for i, ten in sale if bo_dau(ten) == k]
    if len(dung) == 1:
        return dung[0]
    gan = [i for i, ten in sale if k in bo_dau(ten) or bo_dau(ten) in k]
    return gan[0] if len(gan) == 1 else None


def chuan_bi(hang: list[list[str]], conn, nhac: bool) -> tuple[list[dict], Counter]:
    """Đổi các hàng CSV thành lead sẽ nhập. Trả (danh sách lead, bộ đếm). Không ghi gì."""
    dem: Counter = Counter()
    tim = tim_tieu_de(hang)
    if tim is None:
        raise SystemExit("Không thấy hàng tiêu đề (cần có cột \"Tên phụ huynh\" và \"Phone\"). Kiểm tra lại tệp CSV.")
    dau, vt = tim
    ds_co_so, ds_nguon = db.danh_muc(conn, "Cơ sở"), db.danh_muc(conn, "Nguồn")
    sale = [(r["id"], r["ten"]) for r in conn.execute("SELECT id, ten FROM nguoi_dung WHERE vai_tro = 'sale'")]
    da_co = {logic.chu_so(r[0]) for r in conn.execute("SELECT sdt FROM lead")}
    hom_nay = ghi_gio(bay_gio()).split(" ")[0]
    kq = []

    def o(h, khoa):
        j = vt.get(khoa)
        return (h[j] if j is not None and j < len(h) else "").strip()

    for h in hang[dau + 1:]:
        if not any(x.strip() for x in h):
            continue
        dem["hàng có dữ liệu"] += 1
        ten, so, ngay = o(h, "ten_ph"), logic.chu_so(o(h, "sdt")), doc_ngay(o(h, "ngay"))
        if not ten:
            dem["bỏ: thiếu tên"] += 1
            continue
        if len(so) < 9:
            dem["bỏ: SĐT dưới 9 chữ số"] += 1
            continue
        if ngay is None:
            dem["bỏ: thiếu hoặc sai ngày quan tâm"] += 1
            continue
        if so in da_co:
            dem["bỏ: SĐT đã có (trong app hoặc lặp trong tệp)"] += 1
            continue
        da_co.add(so)
        nguon, chien_dich, ghi_nguon = doi_nguon(o(h, "nguon_goc") or o(h, "nguon"), ds_nguon)
        tuoi, ngay_sinh = o(h, "tuoi"), doc_ngay(o(h, "tuoi"))
        email = o(h, "email")
        ghi = [f"[Nhập từ CRM cũ ngày {hom_nay}]"]
        if ghi_nguon:
            ghi.append(ghi_nguon)
        for nhan, khoa in (("Fanpage", "fanpage"), ("Địa chỉ", "dia_chi"), ("Kênh liên hệ", "kenh"),
                           ("Nhập học dự kiến", "nhap_hoc"), ("Câu hỏi / quan tâm", "cau_hoi"), ("Ghi chú cũ", "notes")):
            if o(h, khoa):
                ghi.append(f"{nhan}: {o(h, khoa)}")
        if email and not EMAIL.fullmatch(email):
            ghi.append(f"Email cũ (sai dạng): {email}")
            email = ""
        sale_id = khop_sale(o(h, "sale"), sale)
        dem["có sale phụ trách" if sale_id else "chưa giao sale (không khớp tên)"] += 1
        dem[f"nguồn: {nguon or '(trống)'}"] += 1
        co_so = doi_co_so(o(h, "co_so"), ds_co_so)
        dem["có cơ sở" if co_so else "cơ sở trống"] += 1
        kq.append({
            "ngay_nhan": f"{ngay.isoformat()} 08:00:00", "ten_ph": ten, "sdt": o(h, "sdt"), "email": email,
            "ten_be": o(h, "ten_be"), "tuoi_be": f"sinh {tuoi}" if ngay_sinh else tuoi,
            "ngay_sinh_be": ngay_sinh.isoformat() if ngay_sinh else None, "co_so": co_so, "nguon": nguon,
            "chien_dich": chien_dich, "sale_id": sale_id, "ghi_chu": "\n".join(ghi), "tam_dung": 0 if nhac else 1,
        })
    dem["sẽ nhập"] = len(kq)
    return kq, dem


def ghi(conn, ds: list[dict]) -> None:
    bay_gio_s = ghi_gio(bay_gio())
    for v in ds:
        cot = list(v) + ["tao_luc"]
        conn.execute(f"INSERT INTO lead ({', '.join(cot)}) VALUES ({', '.join('?' * len(cot))})",
                     [*v.values(), bay_gio_s])
    conn.commit()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Nhập phụ huynh từ CSV của CRM Google Sheets cũ (mặc định chỉ chạy thử).")
    p.add_argument("tep", type=Path, help="tệp CSV tải từ Google Sheets")
    p.add_argument("--ghi", action="store_true", help="ghi thật vào cơ sở dữ liệu (mặc định chỉ chạy thử)")
    p.add_argument("--nhac", action="store_true", help="không tạm dừng nhắc các lead nhập vào")
    a = p.parse_args(argv)
    with a.tep.open(encoding="utf-8-sig", newline="") as f:
        hang = list(csv.reader(f))
    conn = db.ket_noi()
    try:
        db.khoi_tao(conn)
        ds, dem = chuan_bi(hang, conn, a.nhac)
        for k in sorted(dem, key=lambda k: (k.startswith("nguồn"), k)):
            print(f"{k}: {dem[k]}")
        if not a.ghi:
            print("\nCHẠY THỬ: chưa ghi gì. Xem số đếm, sao lưu (scripts/sao_luu.py), rồi chạy lại với --ghi.")
            return 0
        ghi(conn, ds)
        print(f"\nĐã nhập {len(ds)} lead vào {db.duong_dan_db()}"
              + ("." if a.nhac else ", đều đang tạm dừng nhắc (chủ bật lại trong hồ sơ nếu muốn chăm sóc tiếp)."))
        print("Nhớ xoá tệp CSV (có tên, SĐT phụ huynh) sau khi nhập.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
