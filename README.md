# Casa · Chăm sóc lead

App web nhắc sale tuyển sinh của Casa dei Bambini (3 cơ sở, Hà Nội) gọi đúng phụ huynh vào đúng ngày, và lưu lại mọi lần chăm sóc. Thay cho bản AppSheet: sale đăng nhập bằng tài khoản app cấp, không cần tài khoản Google hay email `@cdb.edu.vn`, chạy trên VPS của trường nên không tốn phí theo tháng.

- **Sale** (điện thoại): Hôm nay, Của tôi, chi tiết lead, ghi nhận lần chăm sóc, thêm lead, tạo lead cho em. Chỉ thấy lead mình phụ trách.
- **Chủ**: thấy tất cả lead, giao lead, quản lý tài khoản. (Đợt B: lead Messenger, bỏ quên, nhắc sale, theo dõi gửi ưu đãi / thông tin, báo cáo.) Gửi ưu đãi / thông tin là việc của sale: đến hạn thì hiện ở tab Hôm nay (mở Zalo, chép nội dung mẫu chủ soạn ở Cài đặt, bấm Đã gửi) và còn nhắc tới khi bấm Đã gửi.
- **Nhắc mỗi sáng 8:00, thứ 2 – thứ 6** qua Telegram (bot riêng của app). Tin không bao giờ chứa SĐT.

## Quy tắc nhắc

`app/quy_tac_nhac.py` là **bản chuẩn** của quy tắc nhắc (hạn liên hệ, giai đoạn, việc cần làm, tuổi bé, em nhỏ, đại sứ), chép từ `pichu124/casa-plugins` (`cham-soc-lead/`, commit `363d48f`) cùng bộ kiểm thử `tests/test_quy_tac_nhac.py`. Từ nay sửa quy tắc ở đây; bản trong casa-plugins chỉ còn là tài liệu của bản AppSheet. Mô tả quy tắc bằng lời: `cham-soc-lead/thiet-ke.md` mục 4 của casa-plugins.

`app/logic.py` chỉ đổi hàng dữ liệu thành đối tượng của bộ quy tắc, không tự tính hạn.

## Chạy thử trên máy

Cần Python 3.12 trở lên.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
CASA_LEAD_DATA=/tmp/casa-lead-thu .venv/bin/python scripts/du_lieu_mau.py   # 10 lead mẫu (giả)
CASA_LEAD_DATA=/tmp/casa-lead-thu .venv/bin/uvicorn app.main:app --reload
```

Mở http://localhost:8000, đăng nhập `sale3` (hoặc `chu`, `sale1`…`sale6`), mật khẩu `thu-app-123`.

Thử tin nhắc buổi sáng mà không gửi: `CASA_LEAD_DATA=/tmp/casa-lead-thu .venv/bin/python -m app.nhac_sang --thu`.

## Kiểm tra

```bash
./scripts/check.sh      # cú pháp, không có dữ liệu thật trong kho, toàn bộ kiểm thử
```

## Biến môi trường

| Biến | Ý nghĩa |
|---|---|
| `CASA_LEAD_DATA` | Thư mục dữ liệu (tệp `casa-lead.db`, khoá phiên). **Khi chạy thật phải nằm ngoài thư mục mã**, ví dụ `/var/lib/casa-lead` |
| `CASA_LEAD_ENV=production` | Bật cookie chỉ-HTTPS |
| `CASA_LEAD_SECRET` | Khoá ký cookie phiên (không đặt thì app tự tạo và giữ trong thư mục dữ liệu) |
| `CASA_LEAD_URL` | Địa chỉ app, ghi cuối tin nhắc Telegram |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` | Bot Telegram riêng của app (tạo bằng @BotFather). Token là bí mật, không ghi vào kho mã |

## Dữ liệu

Tên và SĐT phụ huynh, tên và tuổi bé: dữ liệu cá nhân. Không chép vào kho mã, log, bài kiểm thử hay pull request. `scripts/check.sh` chặn tệp `.db`, `data/`, `backups/`, `.env` trong kho. Dữ liệu mẫu chỉ dùng tên "… Thử", SĐT `09000006xx`.
