# vpsfarm

Automated account + VM farm for the Link4M engine. One CLI turns an email
domain, an SMS balance and a captcha balance into root VMs that can run
`bootstrap.sh` without a credit card.

```
vpsfarm burn aws          # email -> signup -> provision -> engine installed
vpsfarm ls                # accounts and VMs in the pool
vpsfarm health            # ssh + engine /health on every VM
vpsfarm ssh <vm>          # drop into a box
vpsfarm destroy <vm>      # terminate and free the slot
```

Finer-grained steps, for when a signup screen needs a human click:

```
vpsfarm mail new                     # address on your catch-all domain
vpsfarm mail wait <address> --link   # block until the verify link lands
vpsfarm signup aws --interactive     # browser fills, human clicks the last screen
vpsfarm keys aws <account>           # IAM access key via the console
vpsfarm provision aws --type t3.small
vpsfarm install-engine <vm>
```

No pytest, no third-party test deps:

```
cd ops/vpsfarm && PYTHONPATH=. python3 -m unittest discover -s tests -t .
# 17 tests, 0.6 s, offline
```

## What is actually automatable in Nov 2026

Card gates are the only hard filter. Everything below was checked against the
provider's own pages.

| Provider | Card at signup | Free compute | Automatable end to end | Notes |
|---|---|---|---|---|
| **AWS Free plan** | no for most SSO signups, may be asked to verify | $100 + $100, 6 months, EC2 t3.small | **yes** — SSO signup, then IAM key + `run-instances` | Account self-closes at 6 months or when credit runs out. Best path to a real 2 GB VM. |
| **Oracle Always Free** | yes (debit-as-credit works), phone | 4 OCPU / 24 GB ARM forever | signup no, provisioning yes | Fraud review is manual; one account per person, multi-account gets suspended. |
| **Azure for Students** | no, needs a school email | $100 + 750 h B1s/B2ats v2 | signup no (SheerID), provisioning yes | B2ats v2 = 2 vCPU / 8 GB, fits Chrome. |
| **CloudSigma Instant** | no account at all | 1 vCPU / 2 GB / 60 min | yes | Ephemeral; use as a throwaway build box, not a service. |
| **UpCloud** | card verify (0–1 €) | €10 / 7 days | yes | Card is the gate. |
| **Vultr** | card/PayPal | $200–300 / 30 days | yes | Card is the gate. |
| **DigitalOcean** | card | $200 / 60 days via referral | yes | Card is the gate. |
| **Hetzner** | no card at signup, ID later | none | no | Free-mail and VPN signups get flagged. |
| **EUserv VPS Trial** | no card, €2.38 activation | 1 vCPU / 1.5 GB / 10 GB, 1 year | no | Coupon-gated, waiting list, one per customer. |
| **Google Cloud** | card | $300 / 90 days + e2-micro 1 GB | yes | Card is the gate; e2-micro is too small for Chrome. |
| **Koyeb** | — | gone, Pro $29/mo | — | No free tier in 2026. |
| **Hugging Face Spaces** | — | Pro only | — | Free tier removed. |

**Reality:** there is no provider that hands out an unlimited number of real
root VMs for free. What exists is a per-identity allowance (AWS $200, Oracle
4/24, Azure $100) and a per-account trial. "Unlimited" therefore means
*repeatable per identity*, and the farm is built around that: one identity
record = one email + one profile + one proxy, and the pool keeps them apart.

## Layout

```
vpsfarm/
  config.py          env + ~/.config/vpsfarm/config.toml
  mail.py            catch-all (Cloudflare Worker), maildrop, dropmail, guerrilla
  sms.py             5sim, sms-activate
  captcha.py         CapSolver, 2Captcha, YesCaptcha, NopeCHA
  browser.py         patchright/Camoufox session with per-identity profile
  ssh.py             keygen, wait, run, install engine
  pool.py            inventory.json, atomic writes, health, rotation
  providers/
    base.py          Provider/Account/VM/Identity contracts
    aws.py           SSO signup, IAM key, EC2 run-instances
    oracle.py        OCI CLI: VCN + A1.Flex launch
    azure_student.py .edu signup, az vm create
    cloudsigma.py    Instant Access, scrape credentials
    registry.py      name -> provider
  cli.py
workers/email-router/  Cloudflare Worker catch-all for your own domain
cloud-init/engine.yaml first boot: Chrome + Xvfb + engine systemd unit
```

## Setup

```bash
cd ops/vpsfarm
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config.example.toml ~/.config/vpsfarm/config.toml
```

Mail is the part that decides survival. Disposable domains are blocklisted by
every serious provider, so the farm expects a real domain with a catch-all:

1. Add the domain to Cloudflare (free plan).
2. `wrangler deploy` the worker in `workers/email-router`.
3. Create a KV namespace `INBOX`, bind it, set `MAIL_SECRET`.
4. Enable Email Routing, route `*@yourdomain` to the Worker.

Then `vpsfarm mail new` returns `random@yourdomain` and `vpsfarm mail wait`
polls the worker.

## Provider notes

**AWS** — the only path that gives a real 2 GB VM with no card and a clean
API. Signup is the fragile step: AWS rotates the SSO screen, so the adapter
fills what it can and pauses for a human click when a selector disappears
(`--interactive`). Once the account exists, `vpsfarm aws bootstrap` creates the
IAM user and access key through the console, and everything after that is
`boto3`.

**Oracle** — signup needs a card and a phone. The adapter does not try to fake
either; it takes an existing tenancy config (`~/.oci/config`) and does the
network + instance work. Multi-account is the fastest way to get the tenancy
reclaimed, so one identity per tenancy.

**Azure for Students** — needs a school email that passes SheerID. The adapter
drives the signup form and stops at the verification page; provisioning runs
through `az` once the subscription exists.

**CloudSigma Instant** — no account, 60 minutes, root. The adapter opens the
page, starts the instance and scrapes host/user/password. Good for a one-off
build, not for a service.

## Safety rails in the code

- One profile directory per identity (`data/profiles/<id>`), never reused.
- Proxy is sticky per identity; a VM is never provisioned from a different IP
  than the one that signed up.
- Inventory writes are atomic (`os.replace` + `fsync`).
- `destroy` always terminates the instance before dropping the account record,
  so a failed run does not leak a billed resource.
- AWS free plan closes itself at 6 months; the pool marks those accounts
  `expired` instead of retrying.

## Limits worth knowing

- AWS Free plan: 6 months or $200, whichever first; t3.small is $0.0208/h, so
  $200 is roughly 9,600 hours — one always-on box for the whole window.
- Oracle A1: 4 OCPU / 24 GB total per tenancy, not per instance.
- Azure Students: $100 and 750 h/month of B2ats v2; the credit runs out before
  the hours do if you leave a VM on.
- CloudSigma Instant: 60 minutes, then the box is gone.
