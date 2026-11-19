"""Kiểm tra sao lưu mỗi sáng: bản đêm qua của casa-lead và CASA Mầm non phải có trên VPS và trên Drive (rclone);
thiếu thì báo Telegram (nhóm quản lý, chưa nối nhóm thì chủ), đủ thì im lặng. Không gọi rclone thật."""

import subprocess
from datetime import date

import pytest

from app import db, kiem_tra_sao_luu as kt

HOM_NAY = date(2026, 11, 4)  # đồng hồ test cố định 04/11/2026


@pytest.fixture
def may(du_lieu, tmp_path, monkeypatch):
    """Hai thư mục sao lưu giả và rclone giả: `drive` là các tệp trên Drive theo từng remote."""
    lead, mamnon = tmp_path / "lead-bk", tmp_path / "mamnon-bk"
    lead.mkdir()
    mamnon.mkdir()
    monkeypatch.setenv("SAO_LUU_KIEM_TRA", f"casa-lead={lead}=mahoa:casa-lead;casa-mamnon={mamnon}=mahoa:casa-mamnon")
    drive = {"mahoa:casa-lead": [], "mahoa:casa-mamnon": []}
    goi = []

    def chay(lenh, **kw):
        goi.append(lenh)
        assert lenh[:2] == ["rclone", "lsf"]
        if drive.get("loi"):
            return subprocess.CompletedProcess(lenh, 1, "", "Failed to lsf: couldn't connect")
        return subprocess.CompletedProcess(lenh, 0, "".join(t + "\n" for t in drive[lenh[2]]), "")
    monkeypatch.setattr(kt.subprocess, "run", chay)
    conn = db.ket_noi()
    db.dat_he_thong(conn, "telegram_nhom", "-1001")
    conn.commit()
    return lead, mamnon, drive, du_lieu, conn


def _du(lead, mamnon, drive):
    (lead / "casa-lead-20261104-021501.db").write_bytes(b"x")
    (mamnon / "school-20261104-0200.db.gz").write_bytes(b"x")
    drive["mahoa:casa-lead"] = ["casa-lead-20261103-021501.db", "casa-lead-20261104-021501.db"]
    drive["mahoa:casa-mamnon"] = ["school-20261104-0200.db.gz", "uploads-da-vang.json"]


def test_du_ca_hai_noi_thi_im_lang(may):
    lead, mamnon, drive, da_gui, conn = may
    _du(lead, mamnon, drive)
    assert kt.chay(conn, HOM_NAY) == [] and da_gui == []


def test_thieu_ban_tren_vps_hoac_drive_thi_bao_nhom(may):
    lead, mamnon, drive, da_gui, conn = may
    _du(lead, mamnon, drive)
    (mamnon / "school-20261104-0200.db.gz").unlink()
    drive["mahoa:casa-lead"] = ["casa-lead-20261103-021501.db"]
    loi = kt.chay(conn, HOM_NAY)
    assert len(loi) == 2
    [(chat, tin)] = da_gui
    assert chat == "-1001" and "04/11/2026" in tin
    assert "casa-mamnon: không thấy bản sao lưu đêm qua trên VPS" in tin
    assert "casa-lead: chưa lên Drive" in tin


def test_rclone_loi_thi_bao(may):
    lead, mamnon, drive, da_gui, conn = may
    _du(lead, mamnon, drive)
    drive["loi"] = True
    kt.chay(conn, HOM_NAY)
    assert da_gui and "không đọc được Drive" in da_gui[0][1]


def test_khong_co_rclone_thi_bao(may, monkeypatch):
    lead, mamnon, drive, da_gui, conn = may
    _du(lead, mamnon, drive)

    def khong_co(lenh, **kw):
        raise FileNotFoundError("rclone")
    monkeypatch.setattr(kt.subprocess, "run", khong_co)
    kt.chay(conn, HOM_NAY)
    assert da_gui and "không đọc được Drive" in da_gui[0][1]


def test_chua_noi_nhom_thi_bao_chu(may):
    lead, mamnon, drive, da_gui, conn = may
    db.dat_he_thong(conn, "telegram_nhom", "")
    conn.execute("UPDATE nguoi_dung SET telegram_chat_id = '777' WHERE vai_tro = 'chu'")
    conn.commit()
    kt.chay(conn, HOM_NAY)
    assert [c for c, _ in da_gui] == ["777"]


def test_chay_thu_khong_gui(may):
    lead, mamnon, drive, da_gui, conn = may
    assert kt.chay(conn, HOM_NAY, thu=True) and da_gui == []


def test_cau_hinh_mac_dinh_tren_vps(monkeypatch):
    monkeypatch.delenv("SAO_LUU_KIEM_TRA", raising=False)
    ds = kt.cac_noi_kiem()
    assert [(t, r) for t, _, r in ds] == [("casa-lead", "mahoa:casa-lead"), ("casa-mamnon", "mahoa:casa-mamnon")]
    assert str(ds[1][1]) == "/var/lib/casa-mamnon/backups"


THU_2 = date(2026, 11, 9)  # thứ 2: tổng kết 7 đêm 03/11 → 09/11


def _du_tuan(lead, mamnon, drive, bo_drive=()):
    for d in range(3, 10):
        ngay = f"202611{d:02d}"
        (lead / f"casa-lead-{ngay}-021501.db").write_bytes(b"x")
        (mamnon / f"school-{ngay}-0200.db.gz").write_bytes(b"x")
        if ngay not in bo_drive:
            drive["mahoa:casa-lead"].append(f"casa-lead-{ngay}-021501.db")
        drive["mahoa:casa-mamnon"].append(f"school-{ngay}-0200.db.gz")


def test_thu_2_gui_tong_ket_tuan_khi_du(may):
    lead, mamnon, drive, da_gui, conn = may
    _du_tuan(lead, mamnon, drive)
    assert kt.chay(conn, THU_2) == []
    [(chat, tin)] = da_gui
    assert chat == "-1001" and tin.startswith("✅") and "03/11–09/11" in tin
    assert "casa-lead: 7/7 đêm" in tin and "casa-mamnon: 7/7 đêm" in tin


def test_thu_2_tong_ket_neu_ro_dem_thieu(may):
    lead, mamnon, drive, da_gui, conn = may
    _du_tuan(lead, mamnon, drive, bo_drive=("20261105",))
    kt.chay(conn, THU_2)
    [(_, tin)] = da_gui
    assert "casa-lead: 6/7 đêm" in tin and "thiếu 05/11" in tin


def test_ngay_thuong_du_thi_van_im_lang(may):
    lead, mamnon, drive, da_gui, conn = may
    _du_tuan(lead, mamnon, drive)
    assert kt.chay(conn, date(2026, 11, 6)) == [] and da_gui == []


def test_thu_2_co_loi_thi_mot_tin_gom_canh_bao_va_tong_ket(may):
    lead, mamnon, drive, da_gui, conn = may
    _du_tuan(lead, mamnon, drive, bo_drive=("20261109",))
    kt.chay(conn, THU_2)
    [(_, tin)] = da_gui
    assert tin.startswith("⚠") and "casa-lead: chưa lên Drive" in tin and "casa-lead: 6/7 đêm" in tin
