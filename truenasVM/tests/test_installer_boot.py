import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import call, patch


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("installer_boot", SCRIPTS / "installer_boot.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)
sys.path.pop(0)


class ArtifactTests(unittest.TestCase):
    def test_artifacts_are_separate_from_stock_iso(self):
        item = {"storage_pool": "WD1TB"}
        identity = {
            "path": "/mnt/WD1TB/ISOs/ubuntu-24.04-live-server-amd64.iso",
            "size": 2754981888,
            "mtime": 1.0,
        }

        paths = installer.artifact_paths(item, identity)

        self.assertEqual(
            paths["kernel"],
            "/mnt/WD1TB/ISOs/.truenasVM-ubuntu-24.04-live-server-amd64-vmlinuz",
        )
        self.assertNotIn(identity["path"], paths.values())

    @patch.object(installer, "remote_file", return_value=True)
    @patch.object(installer, "load_remote_manifest")
    @patch.object(installer, "source_identity")
    def test_prepare_reuses_matching_artifacts(self, identity, load_manifest, _remote_file):
        identity.return_value = {
            "path": "/mnt/WD1TB/ISOs/ubuntu.iso",
            "size": 100,
            "mtime": 2.0,
        }
        load_manifest.return_value = {
            "source": identity.return_value,
            "source_sha256": "abc",
        }

        paths, manifest = installer.prepare({"storage_pool": "WD1TB"})

        self.assertEqual(manifest["source_sha256"], "abc")
        self.assertTrue(paths["kernel"].endswith("-vmlinuz"))


class LifecycleTests(unittest.TestCase):
    @patch.object(installer, "find_vm")
    @patch.object(installer, "wait_for_job")
    @patch.object(installer, "api")
    def test_stop_waits_for_true_nas_job(self, api, wait_for_job, find_vm):
        vm = {"id": 40, "status": {"state": "RUNNING"}}
        api.return_value = 123
        find_vm.return_value = {"id": 40, "status": {"state": "STOPPED"}}

        result = installer.stop_and_wait(vm)

        api.assert_called_once_with(
            "vm/id/40/stop", {"force": False, "force_after_timeout": True}
        )
        wait_for_job.assert_called_once_with(123)
        self.assertEqual(result["status"]["state"], "STOPPED")

    @patch.object(installer, "find_vm")
    @patch.object(installer, "api")
    def test_boot_arguments_are_verified(self, api, find_vm):
        find_vm.return_value = {"command_line_args": "-kernel k -initrd i"}

        installer.set_boot_arguments(40, "-kernel k -initrd i")

        api.assert_called_once_with(
            "vm/id/40", {"command_line_args": "-kernel k -initrd i"}, method="PUT"
        )

    def test_completion_is_tied_to_vm_uuid_and_iso(self):
        vm = {"uuid": "uuid-one", "id": 40}
        manifest = {"source_sha256": "abc"}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            installer, "ROOT", Path(directory)
        ):
            zvol = "/dev/zvol/WD1TB/test-ip40-disk0"
            installer.write_completion("test_IP40", vm, manifest, zvol)

            self.assertTrue(
                installer.completion_matches("test_IP40", vm, manifest, zvol)
            )
            self.assertFalse(
                installer.completion_matches(
                    "test_IP40", vm, manifest, "/dev/zvol/WD1TB/replaced-disk"
                )
            )
            self.assertFalse(
                installer.completion_matches(
                    "test_IP40", {"uuid": "new-vm", "id": 41}, manifest, zvol
                )
            )

    @patch.object(installer, "write_completion")
    @patch.object(installer, "run_installer")
    @patch.object(installer, "boot_installed_and_verify")
    @patch.object(installer, "completion_matches", return_value=False)
    @patch.object(installer, "find_vm")
    @patch.object(installer, "prepare")
    @patch.object(installer, "deployment")
    def test_stopped_installer_is_verified_not_assumed_complete(
        self,
        deployment,
        prepare,
        find_vm,
        _completion_matches,
        boot_installed,
        run_installer,
        write_completion,
    ):
        item = {
            "vm_name": "test_IP40",
            "ip_address": "10.0.203.40",
            "storage_pool": "WD1TB",
        }
        args = '-kernel k -initrd i -append "autoinstall ---"'
        stopped = {
            "id": 40,
            "uuid": "uuid-one",
            "command_line_args": args,
            "status": {"state": "STOPPED"},
        }
        running = {**stopped, "command_line_args": "", "status": {"state": "RUNNING"}}
        deployment.return_value = item
        prepare.return_value = ({"kernel": "k", "initrd": "i"}, {"source_sha256": "abc"})
        find_vm.side_effect = [stopped, stopped]
        boot_installed.side_effect = [installer.InstallerError("not bootable"), running]
        run_installer.return_value = stopped

        installer.install("test_IP40")

        run_installer.assert_called_once_with(item, stopped, args)
        self.assertEqual(boot_installed.call_count, 2)
        write_completion.assert_called_once_with(
            "test_IP40",
            running,
            {"source_sha256": "abc"},
            "/dev/zvol/WD1TB/test-ip40-disk0",
        )


class ProvisioningDefinitionTests(unittest.TestCase):
    def test_two_configured_cpus_are_one_socket_with_two_cores(self):
        main = (ROOT / "opentofu/main.tf").read_text(encoding="utf-8")
        self.assertIn("vcpus                 = 1", main)
        self.assertIn("cores                 = var.vcpus", main)
        self.assertNotIn("desired_state", main)

    def test_installer_powers_off_and_marks_target(self):
        template = (ROOT / "opentofu/templates/user-data.yml.tftpl").read_text(
            encoding="utf-8"
        )
        self.assertIn("shutdown: poweroff", template)
        self.assertIn("--target=/target -- touch /etc/truenas-vm-installed", template)

    def test_provision_uses_installer_orchestrator_before_ansible(self):
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        target = makefile.split("provision-base:", 1)[1].split("\ndeploy:", 1)[0]
        self.assertLess(target.index("installer_boot.py prepare"), target.index("apply-auto"))
        self.assertLess(target.index("installer_boot.py install"), target.index("configure-base"))
        self.assertIn("wait-installed", target)
        self.assertIn("apply-auto", target)
        self.assertIn(" -e;", target)
        self.assertLess(
            target.index("detach-installer"), target.index("set_phase.py")
        )
        self.assertIn("restart_vm.py", target)


if __name__ == "__main__":
    unittest.main()
