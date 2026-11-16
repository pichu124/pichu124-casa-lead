# Cài app chăm sóc lead lên VPS của trường

Máy: VPS InterData đặt tại Việt Nam, IP `103.195.238.114`, Ubuntu 24.04, giờ máy +07, người dùng `casa`. Trên máy đã có app CASA Mầm non (`/opt/casa-mamnon`, cổng 3000, Caddy lo HTTPS). App chăm sóc lead chạy **bên cạnh**, không đụng gì của app kia:

| | CASA Mầm non (đã có) | Chăm sóc lead (mới) |
|---|---|---|
| Mã | `/opt/casa-mamnon` | `/opt/casa-lead` |
| Dữ liệu | `/var/lib/casa-mamnon` | `/var/lib/casa-lead` |
| Dịch vụ | `casa-mamnon` | `casa-lead` |
| Cổng (chỉ trong máy) | 3000 | 8100 |
| Tên miền | `casa-school.duckdns.org` | `casa-lead.duckdns.org` (tạm, miễn phí) |

Chỗ chung duy nhất là tệp `/etc/caddy/Caddyfile`: chỉ **thêm** một khối, không sửa khối của app kia.

**Cách làm:** đăng nhập máy bằng `ssh casa@103.195.238.114`, rồi **dán từng dòng một**, chờ dấu nhắc hiện lại rồi mới dán dòng tiếp. Dán cả khối một lúc dễ hỏng mà không báo lỗi.

## 0. Chuẩn bị (làm trên điện thoại hoặc máy tính, không cần vào VPS)

1. **Bot Telegram riêng cho app**: trong Telegram nhắn `@BotFather` → `/newbot` → đặt tên (vd `Casa nhắc lead`) và username (vd `casa_lead_bot`). Giữ lại **token** (dạng `123456:ABC…`). Token là bí mật: không gửi vào nhóm chat, không dán vào kho mã.
2. **Tên miền tạm**: vào https://www.duckdns.org bằng tài khoản đã tạo `casa-school`, thêm tên `casa-lead`, ô "current ip" điền `103.195.238.114`, bấm **update ip**.

## 1. Cài Python và lấy mã

```bash
sudo apt-get update
sudo apt-get install -y python3-venv git sqlite3
python3 --version
```

Dòng cuối phải in `Python 3.12` trở lên.

Kho mã `pichu124/casa-lead` để riêng tư, nên máy cần một **khoá chỉ đọc** (deploy key):

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/casa-lead-deploy -C "vps casa-lead"
cat ~/.ssh/casa-lead-deploy.pub
```

Chép dòng in ra. Trên GitHub mở kho `casa-lead` → **Settings → Deploy keys → Add deploy key**, dán vào, **không** tick "Allow write access", bấm **Add key**. Rồi trên VPS:

```bash
printf 'Host github-casa-lead\n  HostName github.com\n  User git\n  IdentityFile ~/.ssh/casa-lead-deploy\n  IdentitiesOnly yes\n' >> ~/.ssh/config
sudo mkdir -p /opt/casa-lead /var/lib/casa-lead
sudo chown casa:casa /opt/casa-lead /var/lib/casa-lead
chmod 700 /var/lib/casa-lead
git clone git@github-casa-lead:pichu124/casa-lead.git /opt/casa-lead
cd /opt/casa-lead
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
./scripts/check.sh
```

Dòng cuối phải in `check.sh XANH`. Máy chỉ lấy nhánh `main`.

## 2. Cấu hình và tài khoản chủ

Tệp cấu hình chứa token Telegram, chỉ `root` và `casa` đọc được:

```bash
sudo install -m 640 -o root -g casa /dev/null /etc/casa-lead.env
sudo nano /etc/casa-lead.env
```

Gõ vào (thay `<…>`), lưu bằng Ctrl+O, Enter, thoát Ctrl+X:

```
CASA_LEAD_ENV=production
CASA_LEAD_DATA=/var/lib/casa-lead
CASA_LEAD_URL=https://casa-lead.duckdns.org
TELEGRAM_BOT_TOKEN=<token BotFather đưa>
TELEGRAM_BOT_USERNAME=<username của bot, không có @>
```

Tạo tài khoản chủ **trước khi bật dịch vụ** (mật khẩu được hỏi ở dòng lệnh, không hiện ra):

```bash
cd /opt/casa-lead
CASA_LEAD_DATA=/var/lib/casa-lead .venv/bin/python scripts/tao_tai_khoan.py <tên đăng nhập> "<Tên chủ>"
```

Thử sao lưu một lần ngay, khi chưa có dữ liệu:

```bash
CASA_LEAD_DATA=/var/lib/casa-lead .venv/bin/python scripts/sao_luu.py
```

## 3. Dịch vụ tự bật lại

`--host 127.0.0.1`: app chỉ nghe trong máy; Caddy là cửa duy nhất ra Internet (tường lửa `ufw` cũng chỉ mở 22/80/443).

```bash
sudo tee /etc/systemd/system/casa-lead.service >/dev/null <<'UNIT'
[Unit]
Description=Casa cham soc lead
After=network.target

[Service]
Type=simple
User=casa
WorkingDirectory=/opt/casa-lead
EnvironmentFile=/etc/casa-lead.env
ExecStart=/opt/casa-lead/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now casa-lead
curl -s http://127.0.0.1:8100/healthz
```

Dòng cuối phải in `ok`. Không ra thì xem lỗi: `sudo journalctl -u casa-lead -n 50`.

## 4. HTTPS qua Caddy

Thêm một khối vào cuối tệp (không sửa khối `casa-school` đang có):

```bash
sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.truoc-casa-lead
printf '\ncasa-lead.duckdns.org {\n    encode zstd gzip\n    reverse_proxy 127.0.0.1:8100\n}\n' | sudo tee -a /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl -I https://casa-lead.duckdns.org/healthz
```

`caddy validate` phải báo `Valid configuration`; dòng cuối phải có `HTTP/2 200` (lần đầu có thể chờ 1 phút để Caddy xin chứng chỉ). Kiểm luôn app kia vẫn chạy: `curl -I https://casa-school.duckdns.org/healthz`.

Lỡ hỏng Caddy: `sudo cp /etc/caddy/Caddyfile.truoc-casa-lead /etc/caddy/Caddyfile && sudo systemctl reload caddy`.

## 5. Lịch chạy hằng ngày

```bash
crontab -e
```

Thêm hai dòng ở cuối (giữ nguyên dòng sao lưu 02:00 của CASA Mầm non):

```
15 2 * * * cd /opt/casa-lead && CASA_LEAD_DATA=/var/lib/casa-lead .venv/bin/python scripts/sao_luu.py >> /home/casa/sao-luu-lead.log 2>&1
0 8 * * 1-5 cd /opt/casa-lead && set -a && . /etc/casa-lead.env && set +a && .venv/bin/python -m app.nhac_sang >> /home/casa/nhac-sang.log 2>&1
```

Dòng 1: sao lưu 02:15 mỗi đêm. Dòng 2: tin nhắc 8:00 thứ 2 – thứ 6 (app tự bỏ ngày lễ trong mục Ngày nghỉ). Thử tin nhắc mà không gửi:

```bash
cd /opt/casa-lead && set -a && . /etc/casa-lead.env && set +a && .venv/bin/python -m app.nhac_sang --thu
```

**Bản sao lưu đang cùng ổ đĩa với dữ liệu gốc.** Trước khi nhập dữ liệu thật, phải có thêm một bản ra ngoài máy (cùng việc còn thiếu của CASA Mầm non): dùng `scripts/sao_luu.py --ra <thư mục>` với thư mục đồng bộ ra ngoài.

## 6. Dùng thử

Mở https://casa-lead.duckdns.org trên điện thoại, đăng nhập tài khoản chủ.

1. **Tài khoản → Nối Telegram**, làm theo 3 bước trên màn hình.
2. **Quản trị**: tạo tài khoản cho từng sale (tên đăng nhập không dấu, mật khẩu ban đầu ít nhất 8 ký tự), gửi cho họ, dặn đổi lại ở mục Tài khoản và nối Telegram.
3. Trên điện thoại: menu trình duyệt → **Thêm vào màn hình chính** để mở như một app.

## Cập nhật mã về sau

```bash
cd /opt/casa-lead
CASA_LEAD_DATA=/var/lib/casa-lead .venv/bin/python scripts/sao_luu.py
git pull
.venv/bin/pip install -r requirements-dev.txt
./scripts/check.sh
sudo systemctl restart casa-lead
curl -s http://127.0.0.1:8100/healthz
```
