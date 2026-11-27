# Nơi chạy engine — chốt 27/11/2026

Máy local 3.7 GB chỉ nên giữ UI/API client. Chrome headful + OCR + ASR cần
≥ 2 GB riêng cho browser, nên phần nặng phải nằm ở nơi khác. Dưới đây là những
đường thật, đã đối chiếu trang chủ từng nhà, xếp theo "dùng được ngay" chứ
không theo quảng cáo.

## Bảng chọn

| Đường | Specs | Sống được bao lâu | Cần gì | Tự động hoá | Dùng khi |
|---|---|---|---|---|---|
| **AWS Free plan** | t3.small 2 vCPU/2 GB, hoặc t3.medium 4 GB | 6 tháng hoặc tới khi hết $100–200 | Email; SSO Google/GitHub/Apple; có thể bị hỏi thẻ để verify | **Có** — `vpsfarm burn aws` | Muốn VPS thật, IP public, chạy 24/7 |
| **Azure for Students** | B2ats v2 = 2 vCPU/8 GB | 12 tháng, $100 credit | Email trường (.edu) qua SheerID | Không (signup tay), provision bằng `az` | Có email trường, cần RAM |
| **Oracle Always Free** | 4 OCPU/24 GB ARM | Vĩnh viễn | Thẻ debit/credit + số điện thoại | Provision có, signup không | Chấp nhận thẻ, muốn box khoẻ nhất |
| **Lightning AI Studio** | 4 vCPU/16 GB | 24/7 nhưng **restart mỗi 4 h** | Tài khoản Lightning | CLI | Cần 16 GB free, chấp nhận restart |
| **GitHub Codespaces** | 2 core/8 GB, 120 core-h/tháng | 12 h/session, 30 phút idle | GitHub Free | `gh codespace` | Sandbox code, không phải VPS |
| **GitHub Actions** | 16 GB runner | Tối đa 6 h/job | Repo public | workflow có sẵn | Batch solve theo lô |
| **CloudSigma Instant** | 1 vCPU/2 GB | 60 phút | Không gì cả | `vpsfarm instant` | Box dùng một lần, test |
| **Colab / Kaggle** | 12–16 GB RAM | 12 h, bị kill khi idle | Tài khoản Google/Kaggle | `colab-start.sh` | Chạy thử nhanh |

## Đã loại

- **EUserv VS2-free / VPS Trial** — không còn free thật: phí activation ~€10,
  KYC/ID, danh sách chờ, 1 GB RAM. Dưới ngưỡng Chrome.
- **serv00 / ct8.pl** — FreeBSD shared, không root, đăng ký đóng từ 10/2025.
- **alwaysdata** — 256 MB, không root.
- **Koyeb / Hugging Face Spaces (free)** — đã bỏ free tier.
- **Render / Railway / Back4App / Northflank** — RAM 0.5–1 GB, dưới ngưỡng.
- **Hetzner** — không thẻ lúc đăng ký nhưng gửi ID sau, free-mail bị flag.
- **FreeVPS.org** — cần account LowEndTalk 3 tháng + 50 post.

## IP quan trọng hơn RAM — egress dân dụng

Cloudflare của link4m trả **"Just a moment..."** cho IP datacenter. Runner
16 GB của GitHub Actions (Azure) dính đúng cái này: solve chết sau 80 s dù
Chrome headful thật, Xvfb thật. VPS free cũng nằm trong datacenter, nên thêm
RAM không giải quyết gì — cái cần là **IP ra dân dụng**.

`deploy/remote/egress/` giữ đúng phần đó ở nhà:

```bash
# máy nhà (không cần sudo)
L4M_EGRESS_VAR=1 L4M_EGRESS_REPO=<owner>/<repo> deploy/remote/egress/egress.sh

# máy chạy Chrome (runner / VPS / Codespace)
export PROXY_LIST="$(cat ~/.l4m-egress/proxy.txt)"
```

- `socks5.py` — SOCKS5 user/pass (RFC 1929), chỉ CONNECT, bind loopback.
- `egress.sh` — bật listener, mở tunnel TCP qua `tcp@a.pinggy.io`, in ra
  `socks5://user:pass@host:port`, tự nối lại khi tunnel free 60 phút hết hạn,
  và cập nhật repo variable `L4M_EGRESS_PROXY`.
- Workflow `batch.yml` đọc `vars.L4M_EGRESS_PROXY`, preflight bằng
  `curl --socks5-hostname`, rồi truyền thẳng vào engine qua `PROXY_LIST`.

Đo thật 27/11/2026: engine qua relay giải `link4m.net/go/2kCcIqn` trong
**59 s**, `captcha_ms=17306`, trả đúng `destination_url`. Cùng link đó trên
runner không proxy: `page did not expose a captcha (title: Just a moment...)`.

Hệ quả: mọi box free (Codespaces 8 GB, VPS 2 GB, runner 16 GB) đều dùng được
miễn là nó trỏ `PROXY_LIST` về relay nhà. VPS chỉ còn để chạy 24/7, không còn
là điều kiện để solve được.

## GratisVPS — đã thử, checkout hỏng

Trang `/manage/store/free-vps/kvm-vps-free` có thật: KVM 6 GB DDR5, 2 core
7700X, 120 GB NVMe, $0.00, không captcha. Nhưng bước đặt hàng chết ở server:

- `POST cart.php?a=checkout` với `paymentmethod=banktransfer` → **500 "Oops"**,
  mọi biến thể (email khác, country US/DE, bỏ state, bỏ ccinfo) đều 500.
- Bỏ `paymentmethod` → 200 kèm "The selected gateway is not available".
- Gateway duy nhất là "Free Trial (No Payment)" value `banktransfer` — module
  hỏng, không phải form sai.
- `pwreset.php` nhận request nhưng mail không bao giờ tới maildrop, nên không
  lấy lại được account đã tạo dở.

Kết luận: không đăng ký được, đừng thử lại trừ khi họ sửa checkout.

## vyce.cloud — cửa hẹp nhưng thật

Vps-Mini free: 2 GB RAM, 1 vCore, 6 GB NVMe, IPv6 public, root SSH, renew qua
dashboard + captcha. Signup **chỉ** qua GitHub OAuth, account GitHub phải
≥ 30 ngày. API `/api/stock` hiện `free.open=false` toàn bộ region; đã đặt
automation 15 phút/lần báo khi mở. OAuth không tự động được bằng Bearer token
(GitHub đá về `/login`), nên lúc stock mở cần một lần đăng nhập GitHub của
femboy.

## Kết luận thẳng

Không có nhà nào tặng VPS root miễn phí vô hạn. Có **hạn mức theo identity**:
AWS $100–200/6 tháng, Oracle 4 OCPU/24 GB vĩnh viễn nhưng cần thẻ, Azure $100
nếu có email trường. "Farm" ở đây nghĩa là lặp lại theo từng identity, và
`ops/vpsfarm` giữ mỗi identity một email + một profile browser + một proxy.

Đường automation đầy đủ duy nhất hiện tại: AWS. Đường free không thẻ, không
sinh viên, không credit: Lightning AI (restart 4 h) hoặc Codespaces (12 h).

## Nối vào engine

VM dựng xong thì chỉ cần:

```bash
vpsfarm install-engine <vm>          # clone repo, cài Chrome + Xvfb + systemd
scripts/remote-l4m.sh health <ip>    # kiểm tra từ máy local
scripts/remote-l4m.sh once <ip> <url>
```

Engine trên VM chạy `HOST=127.0.0.1`, gọi qua SSH tunnel:

```bash
ssh -N -L 8080:127.0.0.1:8080 ubuntu@<ip>
curl -s localhost:8080/health
```
