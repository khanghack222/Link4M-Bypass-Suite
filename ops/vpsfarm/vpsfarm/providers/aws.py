"""AWS Free plan: SSO signup, IAM access key, EC2 provisioning.

The signup form changes often, so the adapter drives what it can and, when a
selector disappears, either waits for the human (``interactive=True``) or fails
with the page text so the selector can be updated. Everything after the account
exists is plain boto3 and does not touch a browser.
"""

from __future__ import annotations

import json
import re
import secrets
import time
import uuid
from pathlib import Path

from ..browser import Session, open_session
from ..config import Config
from ..mail import MailProvider
from ..pool import Pool
from ..ssh import ensure_key, public_key
from .base import Account, Identity, Provider, ProviderError, VM, VMSpec

SIGNUP_URL = "https://signin.aws.amazon.com/signup?request_type=builderId"

UBUNTU_SSM = (
    "/aws/service/canonical/ubuntu/server/24.04/stable/current/"
    "amd64/hvm/ebs-gp3/ami-id"
)


class AwsProvider(Provider):
    name = "aws"
    automated_signup = False

    # --- signup -------------------------------------------------------------

    def signup(
        self,
        identity: Identity,
        interactive: bool = False,
        mail: MailProvider | None = None,
    ) -> Account:
        if mail is None:
            raise ProviderError("aws signup needs a mail provider")
        inbox = mail.create(local=identity.email.split("@")[0])

        with open_session(self.cfg, identity.id) as session:
            session.goto(SIGNUP_URL)
            self._fill_email(session, inbox.address)
            code = mail.wait_for_code(inbox, timeout=240)
            self._fill_code(session, code)
            self._fill_profile(session, identity)
            if interactive:
                print("finish the remaining AWS screens, then press Enter")
                input()
            else:
                self._fill_phone(session, identity)
                if identity.phone:
                    sms_code = self._wait_sms(identity.phone)
                    self._fill_code(session, sms_code)
            session.wait_url("console.aws.amazon.com", timeout=300)

        account = Account(
            id=uuid.uuid4().hex[:16],
            provider=self.name,
            email=inbox.address,
            password=identity.password,
            identity_id=identity.id,
            extra={"region": self.cfg.aws_region, "keys": {}},
        )
        return account

    def _fill_email(self, session: Session, email: str) -> None:
        session.fill_any(
            [
                'input[type="email"]',
                'input[name="email"]',
                'input[name="accountEmail"]',
                "#email",
            ],
            email,
        )
        session.click_any(
            [
                'button[type="submit"]',
                'button:has-text("Continue")',
                'button:has-text("Next")',
                'input[type="submit"]',
            ]
        )

    def _fill_code(self, session: Session, code: str) -> None:
        session.fill_any(
            [
                'input[name="code"]',
                'input[autocomplete="one-time-code"]',
                'input[type="tel"]',
                'input[type="text"][maxlength="6"]',
            ],
            code,
        )
        session.click_any(
            [
                'button[type="submit"]',
                'button:has-text("Verify")',
                'button:has-text("Continue")',
                'button:has-text("Create")',
            ]
        )

    def _fill_profile(self, session: Session, identity: Identity) -> None:
        session.fill_any(
            ['input[name="name"]', 'input[name="fullName"]', "#name"], identity.first_name
        )
        session.fill_any(
            ['input[name="password"]', 'input[type="password"]'], identity.password
        )
        session.click_any(
            [
                'button[type="submit"]',
                'button:has-text("Continue")',
                'button:has-text("Create")',
            ]
        )

    def _fill_phone(self, session: Session, identity: Identity) -> None:
        if not identity.phone:
            return
        session.fill_any(
            ['input[name="phoneNumber"]', 'input[type="tel"]'], identity.phone
        )
        session.click_any(
            [
                'button[type="submit"]',
                'button:has-text("Send")',
                'button:has-text("Continue")',
            ]
        )

    def _wait_sms(self, phone: str) -> str:
        from ..sms import provider as sms_provider

        client = sms_provider(self.cfg)
        activation = client.buy(product=self.cfg.sms_product)
        try:
            return client.wait_code(activation)
        finally:
            client.finish(activation)

    # --- keys ---------------------------------------------------------------

    def bootstrap_keys(
        self,
        identity: Identity,
        account: Account,
        interactive: bool = False,
    ) -> dict[str, str]:
        """Create an IAM user with an access key through the console.

        Root keys work too but are the first thing a fraud review looks at, so
        the adapter prefers a dedicated user. Returns
        ``{"access_key_id": ..., "secret_access_key": ...}``.
        """
        user = f"l4m-{secrets.token_hex(3)}"
        with open_session(self.cfg, identity.id) as session:
            session.goto("https://console.aws.amazon.com/iam/home#/users")
            session.click_any(
                [
                    'button:has-text("Create user")',
                    'a:has-text("Create user")',
                    '[data-testid="create-user"]',
                ],
                timeout=60000,
            )
            session.fill_any(['input[name="userName"]', "#user-name"], user)
            session.click_any(
                ['button:has-text("Next")', 'button[type="submit"]']
            )
            # Attach the broad managed policy; provisioning needs EC2 + SSM.
            session.click_any(
                [
                    'input[type="radio"][value="managed"]',
                    'label:has-text("Attach policies directly")',
                ],
                timeout=30000,
            )
            session.fill_any(
                ['input[placeholder*="Search"]', 'input[type="search"]'],
                "AdministratorAccess",
            )
            session.click_any(
                [
                    'input[type="checkbox"][value="AdministratorAccess"]',
                    'tr:has-text("AdministratorAccess") input[type="checkbox"]',
                ]
            )
            session.click_any(['button:has-text("Next")', 'button:has-text("Create user")'])
            if interactive:
                print("open the new user, create an access key, then press Enter")
                input()
            return self._read_keys_from_clipboard(session)

    def _read_keys_from_clipboard(self, session: Session) -> dict[str, str]:
        text = session.text()
        access = re.search(r"AKIA[0-9A-Z]{16}", text)
        secret = re.search(r"[A-Za-z0-9/+=]{40}", text)
        if not (access and secret):
            raise ProviderError(
                "access key not visible; open IAM -> Users -> Security credentials "
                "and re-run with --interactive"
            )
        return {
            "access_key_id": access.group(0),
            "secret_access_key": secret.group(0),
        }

    # --- compute ------------------------------------------------------------

    def _client(self, account: Account, service: str):
        import boto3

        keys = account.extra.get("keys") or {}
        if not keys.get("access_key_id"):
            raise ProviderError("account has no access key; run `vpsfarm aws keys <account>`")
        session = boto3.Session(
            aws_access_key_id=keys["access_key_id"],
            aws_secret_access_key=keys["secret_access_key"],
            region_name=account.extra.get("region") or self.cfg.aws_region,
        )
        return session.client(service)

    def provision(self, account: Account, spec: VMSpec) -> VM:
        region = spec.region or account.extra.get("region") or self.cfg.aws_region
        instance_type = spec.instance_type or self.cfg.aws_instance_type
        ec2 = self._client(account, "ec2")
        ssm = self._client(account, "ssm")

        key_name = f"l4m-{uuid.uuid4().hex[:8]}"
        key_path = ensure_key(self.cfg, key_name)
        created = ec2.create_key_pair(KeyName=key_name)
        # boto3 returns the private material once; the file is already the
        # canonical copy, so the response is only used to fail fast.
        if not created.get("KeyMaterial"):
            raise ProviderError("EC2 did not return key material")
        Path(key_path).chmod(0o600)

        group = ec2.create_security_group(
            GroupName=f"l4m-{uuid.uuid4().hex[:8]}",
            Description="l4m engine ssh",
        )
        group_id = group["GroupId"]
        ec2.authorize_security_group_ingress(
            GroupId=group_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
        )

        ami = ssm.get_parameter(Name=UBUNTU_SSM)["Parameter"]["Value"]
        user_data = spec.user_data or _cloud_init(public_key(key_path))
        response = ec2.run_instances(
            ImageId=ami,
            InstanceType=instance_type,
            KeyName=key_name,
            SecurityGroupIds=[group_id],
            MinCount=1,
            MaxCount=1,
            UserData=user_data,
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [{"Key": "Name", "Value": spec.name or "l4m-engine"}],
                }
            ],
        )
        instance_id = response["Instances"][0]["InstanceId"]

        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[instance_id], WaiterConfig={"Delay": 5, "MaxAttempts": 60})
        described = ec2.describe_instances(InstanceIds=[instance_id])
        instance = described["Reservations"][0]["Instances"][0]

        account.extra["last_used"] = time.time()
        return VM(
            id=instance_id,
            provider=self.name,
            account_id=account.id,
            ip=instance.get("PublicIpAddress", ""),
            ssh_user="ubuntu",
            ssh_port=22,
            key_name=str(key_path),
            region=region,
            specs=instance_type,
            extra={"security_group": group_id, "key_name": key_name},
        )

    def destroy(self, account: Account, vm: VM) -> None:
        ec2 = self._client(account, "ec2")
        ec2.terminate_instances(InstanceIds=[vm.id])
        waiter = ec2.get_waiter("instance_terminated")
        waiter.wait(InstanceIds=[vm.id], WaiterConfig={"Delay": 5, "MaxAttempts": 60})

    def list_vms(self, account: Account) -> list[VM]:
        ec2 = self._client(account, "ec2")
        out: list[VM] = []
        for reservation in ec2.describe_instances()["Reservations"]:
            for instance in reservation["Instances"]:
                if instance["State"]["Name"] in {"terminated", "shutting-down"}:
                    continue
                out.append(
                    VM(
                        id=instance["InstanceId"],
                        provider=self.name,
                        account_id=account.id,
                        ip=instance.get("PublicIpAddress", ""),
                        ssh_user="ubuntu",
                        ssh_port=22,
                        key_name="",
                        region=instance["Placement"]["AvailabilityZone"],
                        specs=instance["InstanceType"],
                        status=instance["State"]["Name"],
                    )
                )
        return out


def _cloud_init(ssh_pubkey: str) -> str:
    """Minimal first boot: user + key. The engine is installed by ssh.install_engine."""
    return (
        "#cloud-config\n"
        "users:\n"
        "  - name: ubuntu\n"
        "    sudo: ALL=(ALL) NOPASSWD:ALL\n"
        "    shell: /bin/bash\n"
        "    ssh_authorized_keys:\n"
        f"      - {ssh_pubkey}\n"
        "package_update: true\n"
        "packages: [curl, git, ca-certificates]\n"
    )
