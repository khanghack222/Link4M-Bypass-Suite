"""Oracle Cloud: A1.Flex (Always Free) through the `oci` CLI.

Signup is deliberately not automated: Oracle asks for a card and a phone, and a
tenancy created by a bot gets reclaimed during the manual fraud review. This
adapter starts from an existing tenancy and does the network + instance work,
which is the part that is actually tedious.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid

from ..config import Config
from ..ssh import ensure_key, public_key
from .base import Account, Identity, Provider, ProviderError, VM, VMSpec

SHAPE = "VM.Standard.A1.Flex"


class OracleProvider(Provider):
    name = "oracle"
    automated_signup = False

    def __init__(self, cfg: Config) -> None:
        super().__init__(cfg)
        self.config_file = str(__import__("pathlib").Path(cfg.oci_config).expanduser())

    # --- oci plumbing -------------------------------------------------------

    def _oci(self, *args: str, timeout: float = 300.0) -> dict:
        argv = [
            "oci",
            *args,
            "--config-file",
            self.config_file,
            "--profile",
            self.cfg.oci_profile,
            "--output",
            "json",
        ]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise ProviderError(
                f"oci {' '.join(args[:2])} failed: {result.stderr.strip()[:500]}"
            )
        return json.loads(result.stdout or "{}")

    def _compartment(self, account: Account) -> str:
        return (
            account.extra.get("compartment")
            or self.cfg.oci_compartment
            or account.extra.get("tenancy", "")
        )

    def _tenancy(self) -> str:
        data = self._oci("iam", "tenancy", "get")
        return data["data"]["id"]

    # --- network ------------------------------------------------------------

    def ensure_subnet(self, account: Account) -> str:
        compartment = self._compartment(account)
        vcns = self._oci(
            "network", "vcn", "list", "--compartment-id", compartment
        ).get("data", [])
        if vcns:
            vcn_id = vcns[0]["id"]
        else:
            vcn = self._oci(
                "network",
                "vcn",
                "create",
                "--compartment-id",
                compartment,
                "--cidr-blocks",
                '["10.0.0.0/16"]',
                "--display-name",
                "l4m-vcn",
                "--wait-for-state",
                "AVAILABLE",
            )["data"]
            vcn_id = vcn["id"]
            self._oci(
                "network",
                "internet-gateway",
                "create",
                "--compartment-id",
                compartment,
                "--vcn-id",
                vcn_id,
                "--display-name",
                "l4m-igw",
                "--is-enabled",
                "true",
                "--wait-for-state",
                "AVAILABLE",
            )
            gateways = self._oci(
                "network", "internet-gateway", "list", "--compartment-id", compartment, "--vcn-id", vcn_id
            )["data"]
            igw_id = gateways[0]["id"]
            route_rules = json.dumps(
                [{"destination": "0.0.0.0/0", "destinationType": "CIDR_BLOCK", "networkEntityId": igw_id}]
            )
            route_tables = self._oci(
                "network", "route-table", "list", "--compartment-id", compartment, "--vcn-id", vcn_id
            )["data"]
            self._oci(
                "network",
                "route-table",
                "update",
                "--rt-id",
                route_tables[0]["id"],
                "--route-rules",
                route_rules,
                "--force",
            )
            security_lists = self._oci(
                "network", "security-list", "list", "--compartment-id", compartment, "--vcn-id", vcn_id
            )["data"]
            rules = json.dumps(
                [
                    {
                        "direction": "INGRESS",
                        "protocol": "6",
                        "source": "0.0.0.0/0",
                        "tcpOptions": {"destinationPortRange": {"min": 22, "max": 22}},
                    }
                ]
            )
            self._oci(
                "network",
                "security-list",
                "update",
                "--security-list-id",
                security_lists[0]["id"],
                "--ingress-security-rules",
                rules,
                "--force",
            )

        subnets = self._oci(
            "network", "subnet", "list", "--compartment-id", compartment, "--vcn-id", vcn_id
        ).get("data", [])
        if subnets:
            return subnets[0]["id"]
        subnet = self._oci(
            "network",
            "subnet",
            "create",
            "--compartment-id",
            compartment,
            "--vcn-id",
            vcn_id,
            "--cidr-block",
            "10.0.1.0/24",
            "--display-name",
            "l4m-subnet",
            "--wait-for-state",
            "AVAILABLE",
        )["data"]
        return subnet["id"]

    # --- image --------------------------------------------------------------

    def _image(self, shape: str) -> str:
        data = self._oci(
            "compute",
            "image",
            "list",
            "--compartment-id",
            self._tenancy(),
            "--operating-system",
            "Canonical Ubuntu",
            "--operating-system-version",
            "24.04",
            "--shape",
            shape,
            "--sort-by",
            "TIMECREATED",
            "--sort-order",
            "DESC",
        )
        images = data.get("data", [])
        if not images:
            raise ProviderError(f"no Ubuntu 24.04 image for {shape}")
        return images[0]["id"]

    # --- compute ------------------------------------------------------------

    def provision(self, account: Account, spec: VMSpec) -> VM:
        shape = spec.instance_type or self.cfg.oci_shape or SHAPE
        ocpus = int(self.cfg.oci_ocpus)
        memory = int(self.cfg.oci_memory_gb)
        compartment = self._compartment(account)
        subnet_id = self.ensure_subnet(account)
        image_id = self._image(shape)

        key_name = f"oracle-{uuid.uuid4().hex[:8]}"
        key_path = ensure_key(self.cfg, key_name)
        shape_config = json.dumps({"ocpus": ocpus, "memoryInGBs": memory})

        launched = self._oci(
            "compute",
            "instance",
            "launch",
            "--compartment-id",
            compartment,
            "--availability-domain",
            self._availability_domain(compartment),
            "--shape",
            shape,
            "--shape-config",
            shape_config,
            "--image-id",
            image_id,
            "--subnet-id",
            subnet_id,
            "--assign-public-ip",
            "true",
            "--display-name",
            spec.name or "l4m-engine",
            "--metadata",
            json.dumps({"ssh_authorized_keys": public_key(key_path)}),
            "--wait-for-state",
            "RUNNING",
            timeout=900,
        )["data"]
        instance_id = launched["id"]

        ip = self._public_ip(instance_id)
        account.extra["last_used"] = time.time()
        return VM(
            id=instance_id,
            provider=self.name,
            account_id=account.id,
            ip=ip,
            ssh_user="ubuntu",
            ssh_port=22,
            key_name=str(key_path),
            region=launched.get("availability-domain", ""),
            specs=f"{shape} {ocpus}ocpu/{memory}gb",
            extra={"compartment": compartment, "subnet": subnet_id},
        )

    def _availability_domain(self, compartment: str) -> str:
        data = self._oci(
            "iam", "availability-domain", "list", "--compartment-id", compartment
        )
        domains = data.get("data", [])
        if not domains:
            raise ProviderError("no availability domain in this compartment")
        return domains[0]["name"]

    def _public_ip(self, instance_id: str) -> str:
        for _ in range(30):
            vnics = self._oci(
                "compute", "instance", "list-vnics", "--instance-id", instance_id
            ).get("data", [])
            for vnic in vnics:
                ip = vnic.get("public-ip")
                if ip:
                    return ip
            time.sleep(5)
        raise ProviderError(f"instance {instance_id} has no public IP yet")

    def destroy(self, account: Account, vm: VM) -> None:
        self._oci(
            "compute",
            "instance",
            "terminate",
            "--instance-id",
            vm.id,
            "--force",
            "--wait-for-state",
            "TERMINATED",
            timeout=900,
        )

    def list_vms(self, account: Account) -> list[VM]:
        data = self._oci(
            "compute",
            "instance",
            "list",
            "--compartment-id",
            self._compartment(account),
        )
        out: list[VM] = []
        for row in data.get("data", []):
            if row.get("lifecycle-state") in {"TERMINATED", "TERMINATING"}:
                continue
            out.append(
                VM(
                    id=row["id"],
                    provider=self.name,
                    account_id=account.id,
                    ip="",
                    ssh_user="ubuntu",
                    ssh_port=22,
                    key_name="",
                    region=row.get("availability-domain", ""),
                    specs=row.get("shape", ""),
                    status=str(row.get("lifecycle-state", "")).lower(),
                )
            )
        return out
