"""Báo cáo tháng: số liệu dùng chung cho trang /chu/bao-cao và bản tóm tắt gửi ban giám hiệu.

Ngày làm việc đầu tiên mỗi tháng (quy tắc ở quy_tac_nhac.ngay_gui_bao_cao_thang), cron 8:10 gửi bản tóm tắt
THÁNG TRƯỚC vào nhóm Telegram quản lý (chưa nối nhóm thì từng chủ). Ngày khác cron chạy mà không làm gì.

    python -m app.bao_cao_thang                      # cron: gửi nếu hôm nay là ngày gửi và tháng đó chưa gửi
    python -m app.bao_cao_thang --thu                # chỉ in ra, không gửi
    python -m app.bao_cao_thang --thu --thang 2026-11

Tin chỉ có số đếm và tên nguồn / cơ sở / chiến dịch: không tên, không SĐT phụ huynh (gui_tin còn qua an_sdt).
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from datetime import date

from . import db, dongho, logic, quy_tac_nhac as q, telegram

log = logging.getLogger("casa_lead.bao_cao_thang")

CHUA_GHI = "(chưa ghi)"
SO_CHIEN_DICH = 15  # bảng chiến dịch trên trang chỉ hiện chừng này dòng nhiều lead nhất
DA_GUI = "bao_cao_thang_da_gui"  # he_thong: tháng ("YYYY-MM") đã gửi tóm tắt


def hang_bao_cao(conn: sqlite3.Connection) -> tuple[list[dict], list[dict]]:
    ho_so = [{"Mã lead": str(r["id"]), "Ngày nhận": r["ngay_nhan"], "Cơ sở": r["co_so"], "Nguồn": r["nguon"],
              "Chiến dịch": r["chien_dich"]}
             for r in conn.execute("SELECT id, ngay_nhan, co_so, nguon, chien_dich FROM lead")]
    cs = [{"Mã lead": str(r["lead_id"]), "Tình trạng": r["tinh_trang"]}
          for r in conn.execute("SELECT lead_id, tinh_trang FROM cham_soc")]
    return ho_so, cs


def theo_nhom(ho_so: list[dict], cs: list[dict], thang: str, cot: str, thu_tu: list[str]) -> list[dict]:
    """Phễu tháng chia theo một cột (Nguồn, Chiến dịch) của các lead nhận trong tháng. Chỉ nhóm có lead mới.
    Nhóm xếp theo thứ tự danh mục `thu_tu`, nhóm ngoài danh mục theo số lead giảm dần, ô trống cuối cùng."""
    nhom: dict[str, list[dict]] = {}
    for h in ho_so:
        if h["Ngày nhận"].startswith(thang):
            nhom.setdefault((h[cot] or "").strip() or CHUA_GHI, []).append(h)
    vi_tri = {g: i for i, g in enumerate(thu_tu)}
    ten = sorted(nhom, key=lambda g: (g == CHUA_GHI, vi_tri.get(g, len(vi_tri)), -len(nhom[g]), g))
    hang = []
    for g in ten:
        dem = q.thong_ke_thang(nhom[g], cs, thang, q.TAT_CA)
        moi = dem[q.BUOC_PHEU[0]]
        hang.append(dict(ten=g, so=[dem[b] for b in q.BUOC_PHEU],
                         ty_le=f"{dem['Đã đặt cọc'] * 100 // moi}%" if moi else "–"))
    return hang


def chien_dich_nhieu_nhat(ho_so: list[dict], cs: list[dict], thang: str, n: int) -> list[dict]:
    """`n` chiến dịch nhiều lead mới nhất trong tháng (bỏ lead không ghi chiến dịch)."""
    ds = [h for h in theo_nhom(ho_so, cs, thang, "Chiến dịch", []) if h["ten"] != CHUA_GHI]
    return sorted(ds, key=lambda h: -h["so"][0])[:n]


def thang_truoc(thang: str) -> str:
    y, m = int(thang[:4]), int(thang[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _thang_vn(thang: str) -> str:
    return f"{thang[5:7]}/{thang[:4]}"


def tom_tat(conn: sqlite3.Connection, thang: str, kem_link: bool = True) -> str:
    """Bản tóm tắt chữ thường của tháng `thang` ("YYYY-MM"), mọi cơ sở: phễu so với tháng trước, theo nguồn,
    theo cơ sở, top 3 chiến dịch. Cùng nội dung cho tin Telegram và nút Chép bản tóm tắt."""
    ho_so, cs = hang_bao_cao(conn)
    dem = q.thong_ke_thang(ho_so, cs, thang, q.TAT_CA)
    truoc_thang = thang_truoc(thang)
    truoc = q.thong_ke_thang(ho_so, cs, truoc_thang, q.TAT_CA)
    hom_nay = dongho.hom_nay()
    tinh_toi = f", tính tới {hom_nay:%d/%m/%Y}" if thang >= f"{hom_nay:%Y-%m}" else ""
    dong = [f"📊 Tuyển sinh tháng {_thang_vn(thang)} (lead nhận trong tháng{tinh_toi})", "", "Phễu:"]
    dong += [f"- {b}: {dem[b]} (tháng {_thang_vn(truoc_thang)}: {truoc[b]})" for b in q.BUOC_PHEU]
    if not dem[q.BUOC_PHEU[0]]:
        dong += ["", "Tháng này chưa có lead mới."]
        return "\n".join(dong + _cuoi(thang, kem_link, co_lead=False))

    dong += ["", "Theo nguồn (lead mới · đặt cọc):"]
    dong += [f"- {h['ten']}: {h['so'][0]} · {h['so'][3]}"
             for h in theo_nhom(ho_so, cs, thang, "Nguồn", db.danh_muc(conn, "Nguồn"))]

    dong += ["", "Theo cơ sở (lead mới · tham quan · đặt cọc):"]
    for c in db.danh_muc(conn, "Cơ sở"):
        d = q.thong_ke_thang([h for h in ho_so if c in logic.cac_co_so(h["Cơ sở"])], cs, thang, q.TAT_CA)
        dong.append(f"- {c}: {d['Lead mới']} · {d['Đã tham quan']} · {d['Đã đặt cọc']}")
    d = q.thong_ke_thang([h for h in ho_so if not logic.cac_co_so(h["Cơ sở"])], cs, thang, q.TAT_CA)
    if d["Lead mới"]:
        dong.append(f"- Chưa rõ cơ sở: {d['Lead mới']} · {d['Đã tham quan']} · {d['Đã đặt cọc']}")
    if any(len(logic.cac_co_so(h["Cơ sở"])) > 1 for h in ho_so if h["Ngày nhận"].startswith(thang)):
        dong.append("(Lead quan tâm nhiều cơ sở được đếm ở mỗi cơ sở.)")

    top = chien_dich_nhieu_nhat(ho_so, cs, thang, 3)
    if top:
        dong += ["", "Chiến dịch nhiều lead nhất (lead mới · đặt cọc):"]
        dong += [f"{i}. {h['ten']}: {h['so'][0]} · {h['so'][3]}" for i, h in enumerate(top, 1)]
    return "\n".join(dong + _cuoi(thang, kem_link, co_lead=True))


def _cuoi(thang: str, kem_link: bool, co_lead: bool) -> list[str]:
    dong = []
    if co_lead:
        dong += ["", f"Lưu ý: đặt cọc, nhập học tính theo tháng nhận lead, nên số của tháng {_thang_vn(thang)} "
                     "còn tăng thêm trong vài tuần tới."]
    url = os.environ.get("CASA_LEAD_URL", "").rstrip("/")
    if kem_link and url:
        dong += ["", f"Xem đủ: {url}/chu/bao-cao?thang={thang}"]
    return dong


def chay(conn: sqlite3.Connection, hom_nay: date, thu: bool = False, thang: str | None = None) -> list[tuple[str, str]]:
    """Gửi (hoặc với `thu`, chỉ trả về) tóm tắt tháng trước nếu hôm nay là ngày gửi. Trả (người nhận, nội dung)
    đã gửi được. Mỗi tháng gửi một lần: chỉ đánh dấu đã gửi khi ít nhất một nơi nhận được, lỗi thì lần chạy sau
    (cùng ngày, cron chạy lại tay) gửi lại. `thang` ép tháng cần xem, bỏ qua ngày gửi và dấu đã gửi."""
    ep = thang is not None
    thang = thang or q.ngay_gui_bao_cao_thang(hom_nay, logic.ngay_nghi(conn))
    if thang is None or (not ep and not thu and db.lay_he_thong(conn, DA_GUI) == thang):
        return []
    tin = tom_tat(conn, thang)
    nhan = telegram.nguoi_nhan_quan_ly(conn)
    if thu:
        return [(", ".join(nhan) or "(chưa có nơi nhận: chưa nối nhóm, chủ chưa nối Telegram)", tin)]
    if not nhan:
        log.warning("Chưa nối nhóm Telegram và chủ chưa nối Telegram: không gửi được báo cáo tháng %s", thang)
        return []
    gui = [(c, tin) for c in nhan if telegram.gui_tin(c, tin)]
    if gui:
        db.dat_he_thong(conn, DA_GUI, thang)
        conn.commit()
    else:
        log.warning("Không gửi được báo cáo tháng %s (lỗi mạng hoặc bot bị gỡ): lần chạy sau thử lại", thang)
    return gui


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gửi tóm tắt báo cáo tháng trước qua Telegram")
    p.add_argument("--thu", action="store_true", help="chỉ in ra, không gửi")
    p.add_argument("--ngay", help="ngày tính (YYYY-MM-DD), mặc định hôm nay")
    p.add_argument("--thang", help="xem tháng này (YYYY-MM) thay vì tháng trước của ngày gửi")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx ghi URL kèm token bot ở mức INFO
    hom_nay = date.fromisoformat(a.ngay) if a.ngay else dongho.hom_nay()
    conn = db.ket_noi()
    try:
        db.khoi_tao(conn)
        ds = chay(conn, hom_nay, thu=a.thu, thang=a.thang)
    finally:
        conn.close()
    if a.thu:
        for ai, tin in ds:
            print(f"--- {ai}\n{tin}\n")
        if not ds:
            print(f"{hom_nay:%d/%m/%Y}: không phải ngày gửi báo cáo tháng (thêm --thang YYYY-MM để xem trước).")
    elif ds:
        log.info("Đã gửi báo cáo tháng tới %d nơi", len(ds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
