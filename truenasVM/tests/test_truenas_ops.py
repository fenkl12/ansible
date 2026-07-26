import importlib.util
import io
import json
import tempfile
from pathlib import Path
import subprocess
import unittest
from unittest.mock import call, patch

SPEC = importlib.util.spec_from_file_location("truenas_ops", Path(__file__).parents[1] / "scripts/truenas_ops.py")
ops = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ops)


class SecretTests(unittest.TestCase):
    def test_secret_is_read_literally(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secret.env"
            path.write_text("TRUENAS_API_KEY='value;$PATH`unsafe`'\n")
            with patch.object(ops, "SECRET_FILE", path), patch.dict(ops.os.environ, {}, clear=True):
                self.assertEqual(ops.token(), "value;$PATH`unsafe`")


class BackupStorageTests(unittest.TestCase):
    def healthy_responses(self):
        return [
            [
                {"id": ops.BACKUP_PARENT_DATASET, "type": "FILESYSTEM"},
                {"id": ops.BACKUP_DATASET, "type": "FILESYSTEM"},
            ],
            [
                {
                    "path": ops.BACKUP_EXPORT_PATH,
                    "enabled": True,
                    "ro": False,
                    "networks": [ops.BACKUP_NETWORK],
                    "maproot_user": "root",
                }
            ],
            [
                {
                    "dataset": ops.BACKUP_DATASET,
                    "enabled": True,
                    "lifetime_value": 30,
                    "lifetime_unit": "DAY",
                    "schedule": {"hour": "2", "minute": "0"},
                }
            ],
        ]

    @patch.object(ops, "api")
    def test_healthy_storage_uses_read_only_queries(self, api):
        api.side_effect = self.healthy_responses()

        self.assertEqual(ops.backup_storage_problems(), [])
        self.assertEqual(
            api.call_args_list,
            [call("pool/dataset"), call("sharing/nfs"), call("pool/snapshottask")],
        )

    @patch.object(ops, "api")
    def test_missing_storage_reports_every_required_resource(self, api):
        api.side_effect = [[], [], []]

        problems = ops.backup_storage_problems()

        self.assertTrue(any(ops.BACKUP_PARENT_DATASET in item for item in problems))
        self.assertTrue(any(ops.BACKUP_DATASET in item for item in problems))
        self.assertTrue(any("NFS export" in item for item in problems))
        self.assertTrue(any("snapshot task" in item for item in problems))

    @patch.object(ops, "api")
    def test_misconfigured_share_and_snapshot_are_rejected(self, api):
        responses = self.healthy_responses()
        responses[1][0].update(
            {"enabled": False, "ro": True, "networks": [], "maproot_user": "nobody"}
        )
        responses[2][0].update(
            {"enabled": False, "lifetime_value": 7, "schedule": {"hour": "1", "minute": "30"}}
        )
        api.side_effect = responses

        problems = ops.backup_storage_problems()

        self.assertIn("backup NFS export is disabled", problems)
        self.assertIn("backup NFS export is read-only", problems)
        self.assertIn("backup snapshot task is disabled", problems)
        self.assertIn("backup snapshot retention is not 30 days", problems)
        self.assertIn("backup snapshot schedule is not daily at 02:00", problems)

    @patch.object(ops, "backup_storage_problems", return_value=["missing dataset"])
    def test_check_instructs_one_time_apply(self, _problems):
        with self.assertRaisesRegex(ops.OpsError, "backup-storage-apply once"):
            ops.cmd_backup_storage_check(type("Args", (), {})())


class RetireDiskTests(unittest.TestCase):
    def setUp(self):
        self.deployment = {"vm_name": "test_IP40", "storage_pool": "WD1TB"}

    @patch.object(ops, "deployment")
    @patch.object(ops, "api")
    def test_retire_disk_refuses_existing_vm(self, api, deployment):
        deployment.return_value = self.deployment
        api.return_value = [{"name": "test_IP40"}]

        with self.assertRaisesRegex(ops.OpsError, "VM still exists"):
            ops.cmd_retire_disk(type("Args", (), {"vm": "test_IP40"})())

        api.assert_called_once_with("vm")

    @patch.object(ops, "deployment")
    @patch.object(ops, "api")
    def test_retire_disk_deletes_expected_zvol(self, api, deployment):
        deployment.return_value = self.deployment
        api.side_effect = [[], [{"id": "WD1TB/test-ip40-disk0", "type": "VOLUME"}], True]

        ops.cmd_retire_disk(type("Args", (), {"vm": "test_IP40"})())

        self.assertEqual(
            api.call_args_list,
            [
                call("vm"),
                call("pool/dataset"),
                call("pool/dataset/id/WD1TB%2Ftest-ip40-disk0", method="DELETE"),
            ],
        )

    @patch.object(ops, "deployment")
    @patch.object(ops, "api")
    def test_retire_disk_keeps_state_cleanup_blocked_when_zvol_missing(self, api, deployment):
        deployment.return_value = self.deployment
        api.side_effect = [[], []]

        with self.assertRaisesRegex(ops.OpsError, "state was left unchanged"):
            ops.cmd_retire_disk(type("Args", (), {"vm": "test_IP40"})())

        self.assertEqual(api.call_args_list, [call("vm"), call("pool/dataset")])

    @patch.object(ops, "deployment")
    @patch.object(ops, "api")
    def test_retire_disk_does_not_confirm_failed_deletion(self, api, deployment):
        deployment.return_value = self.deployment
        api.side_effect = [[], [{"id": "WD1TB/test-ip40-disk0", "type": "VOLUME"}], None]

        with self.assertRaisesRegex(ops.OpsError, "did not confirm deletion"):
            ops.cmd_retire_disk(type("Args", (), {"vm": "test_IP40"})())



class VerifyVmTests(unittest.TestCase):
    def deployment(self):
        return {
            "vm_name": "test_IP40",
            "storage_pool": "WD1TB",
            "nic_attach": "enp3s0",
            "provisioning_phase": "install",
            "ubuntu_iso_path": "/mnt/WD1TB/ISOs/ubuntu.iso",
        }

    def vm(self):
        return {
            "id": 40,
            "status": {"state": "STOPPED"},
            "display_available": True,
            "devices": [
                {"dtype": "DISK", "attributes": {"path": "/dev/zvol/WD1TB/test-ip40-disk0"}},
                {"dtype": "NIC", "attributes": {"nic_attach": "enp3s0"}},
                {"dtype": "DISPLAY", "attributes": {}},
                {"dtype": "CDROM", "attributes": {"path": "/mnt/WD1TB/ISOs/ubuntu.iso"}},
                {"dtype": "CDROM", "attributes": {"path": "/mnt/WD1TB/ISOs/cloud-init-test_IP40.iso"}},
            ],
        }

    @patch.object(ops, "file_stat", return_value={"type": "FILE", "size": 100})
    @patch.object(ops, "find_vm")
    @patch.object(ops, "deployment")
    def test_verify_checks_exact_install_devices(self, deployment, find_vm, _file_stat):
        deployment.return_value = self.deployment()
        find_vm.return_value = self.vm()

        ops.cmd_verify(type("Args", (), {"vm": "test_IP40"})())

    @patch.object(ops, "file_stat", return_value={"type": "FILE", "size": 100})
    @patch.object(ops, "find_vm")
    @patch.object(ops, "deployment")
    def test_verify_rejects_wrong_attached_disk(self, deployment, find_vm, _file_stat):
        deployment.return_value = self.deployment()
        vm = self.vm()
        vm["devices"][0]["attributes"]["path"] = "/dev/zvol/WD1TB/wrong-disk"
        find_vm.return_value = vm

        with self.assertRaisesRegex(ops.OpsError, "expected disk is not attached"):
            ops.cmd_verify(type("Args", (), {"vm": "test_IP40"})())


class DetachInstallerTests(unittest.TestCase):
    @patch.object(ops, "deployment", return_value={"vm_name": "test_IP40", "ubuntu_iso_path": "/mnt/WD1TB/ISOs/ubuntu.iso"})
    @patch.object(ops, "find_vm")
    @patch.object(ops, "api", return_value=True)
    def test_detaches_only_matching_installer_iso(self, api, find_vm, _deployment):
        installer = {"id": 8, "dtype": "CDROM", "attributes": {"path": "/mnt/WD1TB/ISOs/ubuntu.iso"}}
        cloud_init = {"id": 9, "dtype": "CDROM", "attributes": {"path": "/mnt/WD1TB/ISOs/cloud-init-test.iso"}}
        find_vm.side_effect = [
            {"id": 40, "status": {"state": "STOPPED"}, "devices": [installer, cloud_init]},
            {"id": 40, "status": {"state": "STOPPED"}, "devices": [cloud_init]},
        ]

        ops.cmd_detach_installer(type("Args", (), {"vm": "test_IP40"})())

        api.assert_called_once_with(
            "vm/device/id/8", {"force": False}, method="DELETE"
        )

    @patch.object(ops, "deployment", return_value={"vm_name": "test_IP40"})
    @patch.object(ops, "find_vm", return_value={"id": 40, "status": {"state": "RUNNING"}})
    @patch.object(ops, "api")
    def test_refuses_to_detach_while_running(self, api, _find_vm, _deployment):
        with self.assertRaisesRegex(ops.OpsError, "while VM 40 is running"):
            ops.cmd_detach_installer(type("Args", (), {"vm": "test_IP40"})())

        api.assert_not_called()


class StatusTests(unittest.TestCase):
    @patch.object(ops, "installed_guest_ready", return_value=False)
    @patch.object(ops, "api", return_value=[{"id": "WD1TB/test-ip40-disk0"}])
    @patch.object(
        ops,
        "find_vm",
        return_value={
            "id": 40,
            "status": {"state": "STOPPED"},
            "command_line_args": "-kernel k",
            "display_available": True,
            "devices": [],
        },
    )
    @patch.object(
        ops,
        "deployment",
        return_value={
            "vm_name": "test_IP40",
            "ip_address": "10.0.203.40",
            "storage_pool": "WD1TB",
            "provisioning_phase": "install",
        },
    )
    def test_status_is_read_only_and_reports_provisioning_state(
        self, _deployment, _find_vm, api, ready
    ):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            ops, "ROOT", Path(directory)
        ), patch("sys.stdout", new_callable=io.StringIO) as stdout:
            ops.cmd_status(type("Args", (), {"vm": "test_IP40"})())

        report = json.loads(stdout.getvalue())
        self.assertEqual(report["phase"], "install")
        self.assertTrue(report["zvol_present"])
        self.assertEqual(report["status"]["state"], "STOPPED")
        api.assert_called_once_with("pool/dataset")
        ready.assert_called_once_with("10.0.203.40")


class InstalledGuestTests(unittest.TestCase):
    @patch.object(ops.subprocess, "run")
    def test_ready_requires_marker_and_non_overlay_root(self, run):
        run.return_value.returncode = 0

        self.assertTrue(ops.installed_guest_ready("10.0.203.40"))

        command = run.call_args.args[0]
        self.assertIn("fenkil@10.0.203.40", command)
        self.assertIn(ops.INSTALL_MARKER, command[-1])
        self.assertIn("!= overlay", command[-1])
        self.assertEqual(run.call_args.kwargs["timeout"], 10)

    @patch.object(ops, "installed_guest_ready", return_value=True)
    @patch.object(ops, "deployment", return_value={"vm_name": "test_IP40", "ip_address": "10.0.203.40"})
    def test_wait_installed_returns_only_for_installed_guest(self, _deployment, ready):
        args = type("Args", (), {"vm": "test_IP40", "timeout": 30})()

        ops.cmd_wait_installed(args)

        ready.assert_called_once_with("10.0.203.40")

    @patch.object(ops.subprocess, "run", side_effect=subprocess.TimeoutExpired("ssh", 10))
    def test_ssh_timeout_is_not_ready(self, _run):
        self.assertFalse(ops.installed_guest_ready("10.0.203.40"))
if __name__ == "__main__":
    unittest.main()
