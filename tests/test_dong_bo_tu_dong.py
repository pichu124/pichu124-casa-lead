"""Lấy Sheet Messenger tự động (cron mỗi 5 phút) và báo ngay vào Telegram khi có phụ huynh Messenger mới chờ
giao sale (mỗi người một lần, không SĐT). Dữ liệu mẫu (giả)."""

import pytest

from app import db, dong_bo_messenger as dbm, messenger
from tests.test_messenger import _hang, sheet  # noqa: F401 — fixture Sheet giả


@pytest.fixture
def nhom():
    conn = db.ket_noi()
    db.dat_he_thong(conn, "telegram_nhom", "-1001")
    conn.commit()
    return conn


def test_lan_dau_chi_ghi_nho_khong_bao_ca_loat(sheet, nhom):  # noqa: F811
    hang, _ = sheet
    da_gui = dbm.chay(nhom)
    assert da_gui == [] and sheet  # phụ huynh có sẵn từ trước: không báo dồn
    hang.append(_hang("1009", ten="Lan Thử", sdt="0911000099", kid_name="Bé Na", campus="Kim Mã"))
    da_gui = dbm.chay(nhom)
    assert len(da_gui) == 1
    chat, tin = da_gui[0]
    assert chat == "-1001" and "Lan Thử" in tin and "Bé Na" in tin and "0911000099" not in tin
    assert "Messenger chưa nhận" in tin
    assert dbm.chay(nhom) == []  # không báo lại


def test_nhieu_phu_huynh_moi_gop_mot_tin(sheet, nhom):  # noqa: F811
    hang, _ = sheet
    dbm.chay(nhom)
    hang += [_hang("1010", ten="A Thử", sdt="0911000010"), _hang("1011", ten="B Thử", sdt="0911000011")]
    da_gui = dbm.chay(nhom)
    assert len(da_gui) == 1 and "A Thử" in da_gui[0][1] and "B Thử" in da_gui[0][1] and "2 phụ huynh" in da_gui[0][1]


def test_chua_noi_nhom_thi_bao_cho_chu(sheet):  # noqa: F811
    conn = db.ket_noi()
    conn.execute("UPDATE nguoi_dung SET telegram_chat_id = '777' WHERE vai_tro = 'chu'")
    conn.commit()
    hang, _ = sheet
    dbm.chay(conn)
    hang.append(_hang("1012", ten="C Thử", sdt="0911000012"))
    assert [c for c, _ in dbm.chay(conn)] == ["777"]


def test_sheet_loi_khong_bao_khong_sap(sheet, nhom, monkeypatch):  # noqa: F811
    dbm.chay(nhom)

    def loi():
        raise messenger.LoiSheet("Sheet trả mã 500")
    monkeypatch.setattr(messenger, "_tai", loi)
    assert dbm.chay(nhom) == []


def test_chua_cau_hinh_thi_im_lang(du_lieu, nhom):
    assert dbm.chay(nhom) == [] and du_lieu == []
