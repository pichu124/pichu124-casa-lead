"""Báo cáo tháng: số liệu dùng chung cho trang /chu/bao-cao và bản tóm tắt gửi ban giám hiệu.

Ngày làm việc đầu tiên mỗi tháng (quy tắc ở quy_tac_nhac.ngay_gui_bao_cao_thang), cron 8:10 gửi bản tóm tắt
THÁNG TRƯỚC vào nhóm Telegram quản lý (chưa nối nhóm thì từng chủ); hôm đó lỗi thì gửi bù tới ngày 10.

    python -m app.bao_cao_thang                      # cron: gửi nếu hôm nay là ngày gửi và còn nơi chưa nhận
    python -m app.bao_cao_thang --thu                # chỉ in ra, không gửi
    python -m app.bao_cao_thang --thu --thang 2026-11

Tin chỉ có số đếm và tên nguồn / cơ sở / chiến dịch: không tên, không SĐT phụ huynh (gui_tin còn qua an_sdt).
"""

from __future__ import annotations

import argparse
import json
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
    ds_cs = set(db.danh_muc(conn, "Cơ sở"))
    for nhan, chon in (("Cơ sở khác", lambda c: c and not set(c) & ds_cs),  # cơ sở đã bỏ khỏi danh mục
                       ("Chưa rõ cơ sở", lambda c: not c)):
        d = q.thong_ke_thang([h for h in ho_so if chon(logic.cac_co_so(h["Cơ sở"]))], cs, thang, q.TAT_CA)
        if d["Lead mới"]:
            dong.append(f"- {nhan}: {d['Lead mới']} · {d['Đã tham quan']} · {d['Đã đặt cọc']}")
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


def _da_nhan(conn: sqlite3.Connection, thang: str) -> set[str]:
    """Nơi đã nhận tóm tắt của `thang` (he_thong DA_GUI lưu {"thang", "da_nhan"})."""
    try:
        luu = json.loads(db.lay_he_thong(conn, DA_GUI) or "{}")
    except ValueError:
        return set()
    return set(luu.get("da_nhan", [])) if isinstance(luu, dict) and luu.get("thang") == thang else set()


def chay(conn: sqlite3.Connection, hom_nay: date, thu: bool = False, thang: str | None = None) -> list[tuple[str, str]]:
    """Gửi (hoặc với `thu`, chỉ trả về) tóm tắt tháng trước nếu hôm nay là ngày gửi. Trả (người nhận, nội dung)
    đã gửi được lần này. Mỗi nơi nhận (nhóm, hoặc từng chủ) nhận một lần mỗi tháng: nơi gửi lỗi được gửi lại ở lần
    chạy sau (cùng ngày chạy lại tay, hoặc cron các ngày gửi bù), nơi đã nhận thì không nhận trùng.
    `thang` ép tháng cần xem: luôn chỉ là xem trước (không gửi, không ghi), bỏ qua ngày gửi."""
    if thang is not None:
        thu = True
    thang = thang or q.ngay_gui_bao_cao_thang(hom_nay, logic.ngay_nghi(conn))
    if thang is None:
        return []
    nhan = telegram.nguoi_nhan_quan_ly(conn)
    if thu:
        return [(", ".join(nhan) or "(chưa có nơi nhận: chưa nối nhóm, chủ chưa nối Telegram)", tom_tat(conn, thang))]
    if not nhan:
        log.warning("Chưa nối nhóm Telegram và chủ chưa nối Telegram: chưa gửi được báo cáo tháng %s", thang)
        return []
    da_nhan = _da_nhan(conn, thang)
    con = [c for c in nhan if c not in da_nhan]
    if not con:
        return []
    tin = tom_tat(conn, thang)
    gui = [(c, tin) for c in con if telegram.gui_tin(c, tin)]
    if gui:
        da_nhan |= {c for c, _ in gui}
        db.dat_he_thong(conn, DA_GUI, json.dumps({"thang": thang, "da_nhan": sorted(da_nhan)}))
        conn.commit()
    if len(gui) < len(con):
        log.warning("Không gửi được báo cáo tháng %s tới %d nơi (lỗi mạng hoặc bot bị gỡ): lần chạy sau gửi lại",
                    thang, len(con) - len(gui))
    return gui


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gửi tóm tắt báo cáo tháng trước qua Telegram")
    p.add_argument("--thu", action="store_true", help="chỉ in ra, không gửi")
    p.add_argument("--ngay", help="ngày tính (YYYY-MM-DD), mặc định hôm nay")
    p.add_argument("--thang", help="xem trước tháng này (YYYY-MM), phải kèm --thu; không gửi")
    a = p.parse_args(argv)
    if a.thang and not a.thu:
        p.error("--thang chỉ để xem trước: thêm --thu (báo cáo tự gửi vào ngày làm việc đầu tháng)")
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
