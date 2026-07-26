import argparse
import importlib.util
import io
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("vm_factory", Path(__file__).parents[1] / "scripts/vm_factory.py")
factory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(factory)


class FactoryTests(unittest.TestCase):
    def test_name_validation(self):
        self.assertEqual(factory.validate_base_name("web-1"), "web-1")
        for value in ("", "1web", "web_name", "web name"):
            with self.assertRaises(factory.FactoryError):
                factory.validate_base_name(value)

    @patch.object(factory, "ping_in_use", return_value=False)
    @patch.object(factory, "discovered_allocations")
    def test_suggestions_skip_allocated_tens(self, allocations, _ping):
        allocations.return_value = ({"web_IP20"}, {"10.0.203.30"})
        self.assertEqual(
            factory.suggestions("web", count=3),
            [("web_IP40", "10.0.203.40"), ("web_IP50", "10.0.203.50"), ("web_IP60", "10.0.203.60")],
        )

    @patch.object(factory, "find_public_key", return_value=(Path("key.pub"), "ssh-ed25519 test"))
    def test_register_configures_default_dotfiles_playbooks(self, _key):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deployments = root / "deployments"
            fleet_path = root / "fleet.json"
            with patch.object(factory, "DEPLOYMENTS", deployments), patch.object(factory, "FLEET", fleet_path):
                factory.register("test", "test_IP40", "10.0.203.40")

            config = (deployments / "test_IP40" / "ansible-vars.yml").read_text(encoding="utf-8")
            for playbook in factory.DEFAULT_DOTFILES_PLAYBOOKS:
                self.assertIn(f"  - {factory.json.dumps(playbook)}\n", config)
            registry = factory.json.loads(fleet_path.read_text(encoding="utf-8"))
            self.assertIsNone(registry["deployments"]["test_IP40"]["core_profile"])
            tfvars = factory.json.loads(
                (deployments / "test_IP40" / "deployment.auto.tfvars.json").read_text()
            )
            self.assertEqual(tfvars["provisioning_phase"], "install")

    def test_list_flags_missing_deployment_config(self):
        fleet = {
            "deployments": {
                "missing_IP40": {
                    "ip_address": "10.0.203.40",
                    "core_profile": None,
                }
            }
        }
        with tempfile.TemporaryDirectory() as directory, patch.object(
            factory, "DEPLOYMENTS", Path(directory) / "deployments"
        ), patch.object(factory, "load_fleet", return_value=fleet), patch(
            "sys.stdout", new_callable=io.StringIO
        ) as stdout:
            factory.cmd_list(argparse.Namespace())

        self.assertIn("missing-config", stdout.getvalue())

    def test_remove_deployment_refuses_existing_vm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deployment_dir = root / "deployments" / "test_IP40"
            deployment_dir.mkdir(parents=True)
            (deployment_dir / "deployment.auto.tfvars.json").write_text(
                "{\"vm_name\": \"test_IP40\", \"ip_address\": \"10.0.203.40\", \"storage_pool\": \"WD1TB\"}\n",
                encoding="utf-8",
            )
            with patch.object(factory, "DEPLOYMENTS", root / "deployments"), patch.object(factory, "api_get", return_value=[{"name": "test_IP40"}]):
                with self.assertRaisesRegex(factory.FactoryError, "VM still exists"):
                    factory.cmd_remove(argparse.Namespace(vm="test_IP40"))

    def test_remove_deployment_refuses_existing_zvol(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deployment_dir = root / "deployments" / "test_IP40"
            deployment_dir.mkdir(parents=True)
            (deployment_dir / "deployment.auto.tfvars.json").write_text(
                "{\"vm_name\": \"test_IP40\", \"ip_address\": \"10.0.203.40\", \"storage_pool\": \"WD1TB\"}\n",
                encoding="utf-8",
            )
            with patch.object(factory, "DEPLOYMENTS", root / "deployments"), patch.object(
                factory, "api_get", side_effect=[[], [{"id": "WD1TB/test-ip40-disk0"}]]
            ):
                with self.assertRaisesRegex(factory.FactoryError, "Zvol still exists"):
                    factory.cmd_remove(argparse.Namespace(vm="test_IP40"))

    def test_remove_deployment_removes_vm_files_and_fleet_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deployments = root / "deployments"
            deployment_dir = deployments / "test_IP40"
            deployment_dir.mkdir(parents=True)
            (deployment_dir / "deployment.auto.tfvars.json").write_text(
                "{\"vm_name\": \"test_IP40\", \"ip_address\": \"10.0.203.40\", \"storage_pool\": \"WD1TB\"}\n",
                encoding="utf-8",
            )
            build_dir = root / "build" / "test_IP40"
            build_dir.mkdir(parents=True)
            (build_dir / "inventory.yml").write_text("all:\n", encoding="utf-8")
            secrets_dir = root / ".secrets"
            secrets_dir.mkdir()
            for suffix in ("console_password", "login_password", "login_password_hash"):
                (secrets_dir / f"test_IP40.{suffix}").write_text("secret\n", encoding="utf-8")
            fleet_path = root / "fleet.json"
            fleet_path.write_text(
                "{\"deployments\": {\"test_IP40\": {\"ip_address\": \"10.0.203.40\"}, \"other_IP50\": {\"ip_address\": \"10.0.203.50\"}}}\n",
                encoding="utf-8",
            )
            with patch.object(factory, "ROOT", root), patch.object(factory, "DEPLOYMENTS", deployments), patch.object(
                factory, "FLEET", fleet_path
            ), patch.object(factory, "api_get", side_effect=[[], []]):
                factory.cmd_remove(argparse.Namespace(vm="test_IP40"))

            self.assertFalse(deployment_dir.exists())
            self.assertFalse(build_dir.exists())
            self.assertFalse(any((root / ".secrets").iterdir()))
            self.assertEqual(set(factory.json.loads(fleet_path.read_text())["deployments"]), {"other_IP50"})

    def test_remove_deployment_allows_missing_build_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deployments = root / "deployments"
            deployment_dir = deployments / "test_IP40"
            deployment_dir.mkdir(parents=True)
            (deployment_dir / "deployment.auto.tfvars.json").write_text(
                "{\"vm_name\": \"test_IP40\", \"ip_address\": \"10.0.203.40\", \"storage_pool\": \"WD1TB\"}\n",
                encoding="utf-8",
            )
            fleet_path = root / "fleet.json"
            fleet_path.write_text("{\"deployments\": {\"test_IP40\": {}}}\n", encoding="utf-8")
            with patch.object(factory, "ROOT", root), patch.object(factory, "DEPLOYMENTS", deployments), patch.object(
                factory, "FLEET", fleet_path
            ), patch.object(factory, "api_get", side_effect=[[], []]):
                factory.cmd_remove(argparse.Namespace(vm="test_IP40"))

            self.assertFalse(deployment_dir.exists())
            self.assertEqual(factory.json.loads(fleet_path.read_text())["deployments"], {})

    def test_remove_unknown_deployment_keeps_fleet_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fleet_path = root / "fleet.json"
            original = "{\"deployments\": {\"other_IP50\": {}}}\n"
            fleet_path.write_text(original, encoding="utf-8")
            with patch.object(factory, "DEPLOYMENTS", root / "deployments"), patch.object(factory, "FLEET", fleet_path):
                with self.assertRaisesRegex(factory.FactoryError, "Unknown deployment"):
                    factory.cmd_remove(argparse.Namespace(vm="missing_IP60"))

            self.assertEqual(fleet_path.read_text(encoding="utf-8"), original)

    def test_env_file_does_not_override_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "env"
            path.write_text("TRUENAS_API_KEY=file-value\n")
            with patch.dict(factory.os.environ, {"TRUENAS_API_KEY": "session-value"}, clear=False):
                factory.load_env_file(path)
                self.assertEqual(factory.os.environ["TRUENAS_API_KEY"], "session-value")

    @patch.object(factory, "api_get")
    @patch.object(factory, "ping_in_use", return_value=False)
    def test_preflight_blocks_existing_vm_without_state(self, _ping, api_get):
        api_get.side_effect = [
            {"version": "24.04.2.5"},
            [{"name": "test_IP40"}],
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deployment_dir = root / "test_IP40"
            deployment_dir.mkdir(parents=True)
            (deployment_dir / "deployment.auto.tfvars.json").write_text(
                "{\"vm_name\": \"test_IP40\", \"ip_address\": \"10.0.203.40\", \"storage_pool\": \"WD1TB\"}\n",
                encoding="utf-8",
            )
            with patch.object(factory, "DEPLOYMENTS", root):
                with self.assertRaises(factory.FactoryError):
                    factory.cmd_preflight(argparse.Namespace(vm="test_IP40"))


if __name__ == "__main__":
    unittest.main()
