import sqlite3
from datetime import datetime, timedelta

from app import db
from scripts import sao_luu


def test_sao_luu_mo_lai_duoc_va_du_du_lieu(du_lieu, tmp_path):
    tep = sao_luu.sao_luu(tmp_path / "bk", datetime(2026, 11, 4, 2, 0))
    conn = sqlite3.connect(tep)
    assert conn.execute("SELECT COUNT(*) FROM lead").fetchone()[0] == 10
    goc = db.ket_noi()
    assert goc.execute("SELECT COUNT(*) FROM cham_soc").fetchone()[0] == conn.execute("SELECT COUNT(*) FROM cham_soc").fetchone()[0]


def test_don_ban_cu_theo_lich_giu(tmp_path):
    bay = datetime(2026, 11, 30, 2, 0)
    for gio in range(0, 24 * 60, 6):  # 60 ngày, 4 bản mỗi ngày
        (tmp_path / (bay - timedelta(hours=gio)).strftime(sao_luu.TEN)).write_text("x")
    (tmp_path / "khong-phai-ban-sao.db").write_text("x")
    sao_luu.don(tmp_path, bay)
    con = sorted(datetime.strptime(p.name, sao_luu.TEN) for p in tmp_path.glob("casa-lead-*.db"))
    gan = [t for t in con if bay - t <= timedelta(days=2)]
    assert len(gan) == 9  # 4 bản/ngày trong 48 giờ, tính cả hai đầu
    assert all(bay - t <= timedelta(days=366) for t in con)
    ngay_cu = [t.date() for t in con if timedelta(days=2) < bay - t <= timedelta(days=14)]
    assert len(ngay_cu) == len(set(ngay_cu))  # mỗi ngày một bản
    assert (tmp_path / "khong-phai-ban-sao.db").exists()  # không đụng tệp khác


def test_du_lieu_mau_khong_chay_khi_da_co_nguoi_dung(tmp_path, monkeypatch):
    import pytest
    from scripts import du_lieu_mau
    monkeypatch.setenv("CASA_LEAD_DATA", str(tmp_path))
    conn = db.ket_noi()
    db.khoi_tao(conn)
    conn.execute("INSERT INTO nguoi_dung (ten_dang_nhap, ten, vai_tro, mat_khau, tao_luc) VALUES ('hieu', 'Hiệu', 'chu', 'x', '2026-11-16')")
    conn.commit()
    with pytest.raises(SystemExit):
        du_lieu_mau.nap(conn, __import__("datetime").date(2026, 11, 2))


def test_chay_that_bat_buoc_thu_muc_du_lieu_ngoai_kho(monkeypatch):
    import pytest
    monkeypatch.setenv("CASA_LEAD_ENV", "production")
    monkeypatch.delenv("CASA_LEAD_DATA", raising=False)
    with pytest.raises(SystemExit):
        db.duong_dan_db()
    monkeypatch.setenv("CASA_LEAD_DATA", str(db.GOC / "data"))
    with pytest.raises(SystemExit):
        db.duong_dan_db()
