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
