"""Offline tests for vpsfarm: no provider, no browser, no network.

Run with:

    cd ops/vpsfarm && python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vpsfarm import captcha, config, mail, providers, ssh
from vpsfarm.pool import Pool
from vpsfarm.providers.base import Account, Identity, VM, VMSpec


def temp_config(root: Path) -> config.Config:
    cfg = config.Config()
    cfg.data_dir = root
    cfg.ensure_dirs()
    return cfg


class ConfigTests(unittest.TestCase):
    def test_toml_then_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "config.toml"
            path.write_text('aws_region = "eu-west-1"\nheadless = true\n', encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {"VPSFARM_AWS_REGION": "ap-northeast-1", "VPSFARM_DATA_DIR": str(root / "d")},
                clear=False,
            ):
                cfg = config.load(path)
            self.assertEqual(cfg.aws_region, "ap-northeast-1")
            self.assertTrue(cfg.headless)
            self.assertTrue(cfg.data_dir.is_dir())
            self.assertEqual((cfg.data_dir.stat().st_mode & 0o777), 0o700)

    def test_defaults_are_mutable_safe(self) -> None:
        first = config.Config()
        second = config.Config()
        first.aws_region = "us-east-1"
        self.assertEqual(second.aws_region, "ap-southeast-1")


class PoolTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.cfg = temp_config(self.root)
        self.pool = Pool(self.cfg)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_identity_roundtrip_writes_file(self) -> None:
        identity = Identity(id="id1", email="a@b.c", password="pw", phone="+8490")
        self.pool.save_identity(identity)
        path = self.root / "identities" / "id1.json"
        self.assertTrue(path.is_file())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        loaded = self.pool.identity("id1")
        self.assertEqual(loaded.email, "a@b.c")
        self.assertEqual(loaded.phone, "+8490")
        self.assertEqual(len(self.pool.identities()), 1)

    def test_account_and_vm_survive_reload(self) -> None:
        account = Account(
            id="acc1",
            provider="aws",
            email="a@b.c",
            password="pw",
            identity_id="id1",
            created_at=1_700_000_000.0,
        )
        self.pool.add_account(account)
        vm = VM(
            id="i-123",
            provider="aws",
            account_id="acc1",
            ip="10.0.0.1",
            ssh_user="ubuntu",
            ssh_port=22,
            key_name="/k",
            region="ap-southeast-1",
            specs="t3.small",
        )
        self.pool.add_vm(vm)

        fresh = Pool(self.cfg)
        reloaded = fresh.account("acc1")
        self.assertEqual(reloaded.created_at, 1_700_000_000.0)
        self.assertGreater(reloaded.age_days, 0)
        self.assertEqual(fresh.accounts("aws")[0].email, "a@b.c")
        self.assertEqual(fresh.vms(provider="aws")[0].ip, "10.0.0.1")

    def test_inventory_is_atomic_and_events_capped(self) -> None:
        self.pool.save_identity(Identity(id="i", email="e@x", password="p"))
        raw = json.loads(self.cfg.inventory_path.read_text(encoding="utf-8"))
        self.assertIn("identities", raw)
        self.assertFalse(self.cfg.inventory_path.with_suffix(".tmp").exists())
        for n in range(510):
            self.pool._event(raw, "noise", str(n))
        self.assertEqual(len(raw["events"]), 500)
        self.assertEqual(raw["events"][-1]["detail"], "509")

    def test_missing_account_raises(self) -> None:
        with self.assertRaises(Exception):
            self.pool.account("nope")


class MailTests(unittest.TestCase):
    def test_code_extraction_prefers_standalone_six_digits(self) -> None:
        bodies = ["Your code is 483920. Order 1234567.", "no code here"]
        self.assertEqual(mail.extract_codes(bodies)[0], "483920")

    def test_dropmail_requires_server_session(self) -> None:
        cfg = config.Config()
        cfg.mail_provider = "dropmail"
        client = mail.provider(cfg)
        self.assertIsInstance(client, mail.DropmailMail)

    def test_unknown_provider_message(self) -> None:
        cfg = config.Config()
        with self.assertRaises(mail.MailError):
            mail.provider(cfg, "nope")


class FakeSolver(captcha.Solver):
    name = "fake"

    def __init__(self) -> None:
        self.cfg = config.Config()
        self.tasks: list[dict] = []

    def solve(self, task: dict, timeout: float = 180.0) -> str:
        self.tasks.append(task)
        return "token"


class CaptchaTests(unittest.TestCase):
    def test_task_shapes(self) -> None:
        solver = FakeSolver()
        self.assertEqual(solver.solve_recaptcha_v2("k", "https://a"), "token")
        solver.solve_recaptcha_v3("k", "https://a", action="login")
        solver.solve_turnstile("k", "https://a")
        solver.solve_hcaptcha("k", "https://a")
        kinds = [task["type"] for task in solver.tasks]
        self.assertEqual(
            kinds,
            [
                "ReCaptchaV2TaskProxyLess",
                "ReCaptchaV3TaskProxyLess",
                "AntiTurnstileTaskProxyLess",
                "HCaptchaTaskProxyLess",
            ],
        )
        self.assertEqual(solver.tasks[1]["pageAction"], "login")
        for task in solver.tasks:
            self.assertEqual(task["websiteURL"], "https://a")


class RegistryTests(unittest.TestCase):
    def test_aliases_resolve_to_adapters(self) -> None:
        cfg = config.Config()
        for alias, expected in (("oci", "oracle"), ("azure", "azure-student"), ("lightning-ai", "lightning")):
            self.assertEqual(providers.get(cfg, alias).name, expected)

    def test_unknown_provider_lists_known(self) -> None:
        with self.assertRaises(providers.ProviderError) as caught:
            providers.get(config.Config(), "nope")
        self.assertIn("aws", str(caught.exception))


class ContractTests(unittest.TestCase):
    def test_base_provider_refuses_by_default(self) -> None:
        base = providers.Provider(config.Config())
        with self.assertRaises(NotImplementedError):
            base.signup(Identity(id="i", email="e", password="p"))

    def test_vm_spec_defaults(self) -> None:
        spec = VMSpec()
        self.assertEqual(spec.user_data, "")
        self.assertEqual(spec.region, "")


class SshTests(unittest.TestCase):
    def test_key_is_created_once_and_private(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_config(Path(tmp))
            key = ssh.ensure_key(cfg, "test")
            self.assertTrue(key.is_file())
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            self.assertIn("ssh-ed25519", ssh.public_key(key))
            again = ssh.ensure_key(cfg, "test")
            self.assertEqual(again, key)

    def test_run_without_check_returns_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = temp_config(Path(tmp))
            key = ssh.ensure_key(cfg, "test")
            result = ssh.run(
                "127.0.0.1",
                key,
                "true",
                user="nobody",
                port=1,
                timeout=5,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)


class CloudInitTests(unittest.TestCase):
    def test_unit_files_present(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "cloud-init" / "engine.yaml").read_text(encoding="utf-8")
        self.assertIn("l4m-engine.service", text)
        self.assertIn("l4m-xvfb.service", text)
        self.assertIn("HOST=127.0.0.1", text)
        self.assertNotIn("\t", text)


if __name__ == "__main__":
    unittest.main()
