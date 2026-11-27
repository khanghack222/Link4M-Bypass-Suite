"""Command line entry point: ``python -m vpsfarm``."""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import uuid
from pathlib import Path

from . import config as config_module
from . import mail as mail_module
from . import providers
from . import ssh as ssh_module
from .pool import Pool, PoolError
from .providers.base import Identity, ProviderError, VMSpec


def _identity(args: argparse.Namespace) -> Identity:
    return Identity(
        id=uuid.uuid4().hex[:12],
        email=args.email or "",
        password=args.password or mail_module.random_password(),
        first_name=args.first_name,
        last_name=args.last_name,
        phone=args.phone or "",
        country=args.country,
        proxy=args.proxy or "",
    )


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, default=str))


def cmd_init(args: argparse.Namespace) -> int:
    cfg = config_module.load()
    cfg.ensure_dirs()
    _print(
        {
            "data_dir": str(cfg.data_dir),
            "inventory": str(cfg.inventory_path),
            "providers": providers.names(),
        }
    )
    return 0


def cmd_mail(args: argparse.Namespace) -> int:
    cfg = config_module.load()
    client = mail_module.provider(cfg, args.provider)
    if args.action == "new":
        inbox = client.create(local=args.local)
        _print({"address": inbox.address, "provider": inbox.provider})
        return 0
    inbox = mail_module.Inbox(address=args.address, provider=client.name, token=args.token)
    if args.link:
        _print({"link": client.wait_for_link(inbox, timeout=args.timeout)})
    else:
        _print({"code": client.wait_for_code(inbox, timeout=args.timeout)})
    return 0


def cmd_signup(args: argparse.Namespace) -> int:
    cfg = config_module.load()
    pool = Pool(cfg)
    provider = providers.get(cfg, args.provider)
    identity = _identity(args)
    if not identity.email:
        identity.email = mail_module.provider(cfg).create().address
    pool.save_identity(identity)
    mail = mail_module.provider(cfg) if provider.name == "aws" else None
    account = (
        provider.signup(identity, interactive=args.interactive, mail=mail)
        if mail
        else provider.signup(identity, interactive=args.interactive)
    )
    pool.add_account(account)
    _print({"account": account.id, "email": account.email, "provider": account.provider})
    return 0


def cmd_keys(args: argparse.Namespace) -> int:
    cfg = config_module.load()
    pool = Pool(cfg)
    provider = providers.get(cfg, args.provider)
    account = pool.account(args.account)
    identity = pool.identity(account.identity_id)
    if not hasattr(provider, "bootstrap_keys"):
        raise ProviderError(f"{provider.name} does not use access keys")
    keys = provider.bootstrap_keys(identity, account, interactive=args.interactive)  # type: ignore[attr-defined]
    account.extra["keys"] = keys
    pool.update_account(account)
    _print({"account": account.id, "access_key_id": keys["access_key_id"]})
    return 0


def cmd_provision(args: argparse.Namespace) -> int:
    cfg = config_module.load()
    pool = Pool(cfg)
    provider = providers.get(cfg, args.provider)
    account = pool.account(args.account) if args.account else pool.pick_account(provider.name)
    spec = VMSpec(
        region=args.region or "",
        instance_type=args.type or "",
        name=args.name or "",
    )
    vm = provider.provision(account, spec)
    pool.add_vm(vm)
    pool.update_account(account)
    _print({"vm": vm.id, "ip": vm.ip, "provider": vm.provider, "specs": vm.specs})
    return 0


def cmd_burn(args: argparse.Namespace) -> int:
    cfg = config_module.load()
    pool = Pool(cfg)
    provider = providers.get(cfg, args.provider)
    mail = mail_module.provider(cfg)
    identity = _identity(args)
    if not identity.email:
        identity.email = mail.create().address
    pool.save_identity(identity)

    print(f"[1/5] signup {provider.name} as {identity.email}", file=sys.stderr)
    account = provider.signup(identity, interactive=args.interactive, mail=mail)
    pool.add_account(account)

    if hasattr(provider, "bootstrap_keys"):
        print("[2/5] create access key", file=sys.stderr)
        keys = provider.bootstrap_keys(identity, account, interactive=args.interactive)  # type: ignore[attr-defined]
        account.extra["keys"] = keys
        pool.update_account(account)
    else:
        print("[2/5] no access key needed", file=sys.stderr)

    print("[3/5] provision", file=sys.stderr)
    vm = provider.provision(account, VMSpec(region=args.region or "", instance_type=args.type or ""))
    pool.add_vm(vm)

    if not args.no_install and vm.ip:
        print(f"[4/5] waiting for ssh on {vm.ip}", file=sys.stderr)
        ssh_module.wait_port(vm.ip, vm.ssh_port, timeout=300)
        print("[5/5] installing engine", file=sys.stderr)
        status = ssh_module.install_engine(
            vm.ip,
            Path(vm.key_name),
            args.repo_url,
            args.api_key,
            user=vm.ssh_user,
            port=vm.ssh_port,
        )
        print(status, file=sys.stderr)
    else:
        print("[4/5] skipped install", file=sys.stderr)

    _print({"vm": vm.id, "ip": vm.ip, "account": account.id, "specs": vm.specs})
    return 0


def cmd_instant(args: argparse.Namespace) -> int:
    cfg = config_module.load()
    provider = providers.get(cfg, "cloudsigma")
    identity = _identity(args)
    creds = provider.instant(identity)  # type: ignore[attr-defined]
    _print(creds)
    return 0


def cmd_ls(args: argparse.Namespace) -> int:
    cfg = config_module.load()
    pool = Pool(cfg)
    rows = []
    for vm in pool.vms(provider=args.provider):
        rows.append(
            {
                "id": vm.id,
                "provider": vm.provider,
                "ip": vm.ip,
                "specs": vm.specs,
                "status": vm.status,
                "account": vm.account_id,
            }
        )
    _print({"vms": rows, "count": len(rows)})
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    cfg = config_module.load()
    pool = Pool(cfg)
    rows = []
    for vm in pool.vms(provider=args.provider):
        if not vm.ip:
            rows.append({"id": vm.id, "ip": "", "ssh": False, "engine": False})
            continue
        try:
            ssh_module.wait_port(vm.ip, vm.ssh_port, timeout=10)
            ssh_ok = True
        except Exception:
            ssh_ok = False
        engine_ok = (
            ssh_module.engine_health(vm.ip, Path(vm.key_name), user=vm.ssh_user, port=vm.ssh_port)
            if ssh_ok
            else False
        )
        rows.append({"id": vm.id, "ip": vm.ip, "ssh": ssh_ok, "engine": engine_ok})
    _print({"health": rows})
    return 0


def cmd_ssh(args: argparse.Namespace) -> int:
    cfg = config_module.load()
    pool = Pool(cfg)
    vm = pool.vm(args.vm)
    if not vm.ip:
        raise ProviderError(f"{vm.id} has no direct IP; use {vm.extra.get('cli', 'the provider CLI')}")
    argv = [
        "ssh",
        "-i",
        vm.key_name,
        "-p",
        str(vm.ssh_port),
        "-o",
        "StrictHostKeyChecking=no",
        f"{vm.ssh_user}@{vm.ip}",
    ]
    return subprocess.call(argv)


def cmd_install_engine(args: argparse.Namespace) -> int:
    cfg = config_module.load()
    pool = Pool(cfg)
    vm = pool.vm(args.vm)
    status = ssh_module.install_engine(
        vm.ip, Path(vm.key_name), args.repo_url, args.api_key, user=vm.ssh_user, port=vm.ssh_port
    )
    _print({"vm": vm.id, "status": status})
    return 0


def cmd_destroy(args: argparse.Namespace) -> int:
    cfg = config_module.load()
    pool = Pool(cfg)
    vm = pool.vm(args.vm)
    provider = providers.get(cfg, vm.provider)
    account = pool.account(vm.account_id)
    provider.destroy(account, vm)
    vm.status = "terminated"
    pool.update_vm(vm)
    _print({"vm": vm.id, "status": "terminated"})
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    cfg = config_module.load()
    pool = Pool(cfg)
    _print({"events": pool.events(args.limit)})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vpsfarm", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create data dirs and print providers").set_defaults(func=cmd_init)

    mail = sub.add_parser("mail", help="create an inbox or wait for a code")
    mail.add_argument("action", choices=["new", "wait"])
    mail.add_argument("address", nargs="?")
    mail.add_argument("--provider")
    mail.add_argument("--local")
    mail.add_argument("--token", default="")
    mail.add_argument("--timeout", type=float, default=180.0)
    mail.add_argument("--link", action="store_true")
    mail.set_defaults(func=cmd_mail)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--email")
    common.add_argument("--password")
    common.add_argument("--first-name", default="Alex")
    common.add_argument("--last-name", default="Tran")
    common.add_argument("--phone", default="")
    common.add_argument("--country", default="VN")
    common.add_argument("--proxy", default="")

    signup = sub.add_parser("signup", parents=[common], help="create an account")
    signup.add_argument("provider")
    signup.add_argument("--interactive", action="store_true")
    signup.set_defaults(func=cmd_signup)

    keys = sub.add_parser("keys", help="create an access key for an account")
    keys.add_argument("provider")
    keys.add_argument("account")
    keys.add_argument("--interactive", action="store_true")
    keys.set_defaults(func=cmd_keys)

    provision = sub.add_parser("provision", help="create a VM")
    provision.add_argument("provider")
    provision.add_argument("--account")
    provision.add_argument("--type")
    provision.add_argument("--region")
    provision.add_argument("--name")
    provision.set_defaults(func=cmd_provision)

    burn = sub.add_parser("burn", parents=[common], help="signup + keys + VM + engine")
    burn.add_argument("provider")
    burn.add_argument("--interactive", action="store_true")
    burn.add_argument("--type")
    burn.add_argument("--region")
    burn.add_argument("--no-install", action="store_true")
    burn.add_argument(
        "--repo-url",
        default="https://github.com/khanghack222/Link4M-Bypass-Suite.git",
    )
    burn.add_argument("--api-key", default=secrets.token_hex(16))
    burn.set_defaults(func=cmd_burn)

    instant = sub.add_parser("instant", parents=[common], help="CloudSigma 60-minute box")
    instant.set_defaults(func=cmd_instant)

    ls = sub.add_parser("ls", help="list VMs")
    ls.add_argument("--provider")
    ls.set_defaults(func=cmd_ls)

    health = sub.add_parser("health", help="ssh + engine health")
    health.add_argument("--provider")
    health.set_defaults(func=cmd_health)

    shell = sub.add_parser("ssh", help="open a shell on a VM")
    shell.add_argument("vm")
    shell.set_defaults(func=cmd_ssh)

    install = sub.add_parser("install-engine", help="run the remote bootstrap")
    install.add_argument("vm")
    install.add_argument(
        "--repo-url",
        default="https://github.com/khanghack222/Link4M-Bypass-Suite.git",
    )
    install.add_argument("--api-key", default=secrets.token_hex(16))
    install.set_defaults(func=cmd_install_engine)

    destroy = sub.add_parser("destroy", help="terminate a VM")
    destroy.add_argument("vm")
    destroy.set_defaults(func=cmd_destroy)

    events = sub.add_parser("events", help="recent pool events")
    events.add_argument("--limit", type=int, default=30)
    events.set_defaults(func=cmd_events)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ProviderError, PoolError, mail_module.MailError, ssh_module.SshError) as exc:
        print(f"vpsfarm: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
