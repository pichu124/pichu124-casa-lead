#!/usr/bin/env python3
"""Sao lưu cơ sở dữ liệu (an toàn cả khi app đang chạy) và dọn bản cũ.

    python scripts/sao_luu.py                       # vào <thư mục dữ liệu>/backups
    python scripts/sao_luu.py --ra /mnt/o-ngoai     # thêm một bản ra nơi khác (ổ ngoài, thư mục đồng bộ)

Giữ: mọi bản trong 2 ngày gần nhất, một bản mỗi ngày trong 14 ngày, một bản mỗi tháng trong 12 tháng.
Mỗi bản được mở lại và kiểm `PRAGMA integrity_check` trước khi coi là xong.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.dongho import bay_gio  # noqa: E402

TEN = "casa-lead-%Y%m%d-%H%M%S.db"


def sao_luu(dich: Path, bay: datetime) -> Path:
    dich.mkdir(parents=True, exist_ok=True)
    tep = dich / bay.strftime(TEN)
    nguon = sqlite3.connect(db.duong_dan_db())
    try:
        dst = sqlite3.connect(tep)
        with dst:
            nguon.backup(dst)
        dst.close()
    finally:
        nguon.close()
    kiem = sqlite3.connect(tep)
    try:
        if kiem.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit(f"Bản sao {tep} hỏng: không dùng được.")
    finally:
        kiem.close()
    tep.chmod(0o600)
    return tep


def don(dich: Path, bay: datetime) -> list[Path]:
    """Xoá bản cũ theo lịch giữ ở đầu tệp. Chỉ đụng tệp đúng mẫu tên của app."""
    ban = []
    for p in dich.glob("casa-lead-*.db"):
        try:
            ban.append((datetime.strptime(p.name, TEN), p))
        except ValueError:
            continue
    ban.sort(reverse=True)
    giu, ngay_da, thang_da = set(), set(), set()
    for t, p in ban:
        if bay - t <= timedelta(days=2):
            giu.add(p)
            ngay_da.add(t.date())  # ngày, tháng này đã có bản: không giữ thêm
            thang_da.add((t.year, t.month))
        elif bay - t <= timedelta(days=14) and t.date() not in ngay_da:
            giu.add(p)
            ngay_da.add(t.date())
            thang_da.add((t.year, t.month))
        elif bay - t <= timedelta(days=366) and (t.year, t.month) not in thang_da:
            giu.add(p)
            thang_da.add((t.year, t.month))
    xoa = [p for _, p in ban if p not in giu]
    for p in xoa:
        p.unlink()
    return xoa


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--ra", type=Path, help="thêm một bản ra thư mục này")
    o = a.parse_args()
    bay = bay_gio()
    goc = db.duong_dan_db().parent / "backups"
    tep = sao_luu(goc, bay)
    don(goc, bay)
    print(f"Đã sao lưu: {tep}")
    if o.ra:
        tep2 = sao_luu(o.ra, bay)
        don(o.ra, bay)
        print(f"Đã sao lưu ra ngoài: {tep2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
