import argparse
import importlib.util
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "core_profiles", Path(__file__).parents[1] / "scripts/core_profiles.py"
)
profiles = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profiles)


class CoreProfileTests(unittest.TestCase):
    def environment(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        deployments = root / "deployments"
        deployment = deployments / "test_IP40"
        deployment.mkdir(parents=True)
        (deployment / "deployment.auto.tfvars.json").write_text("{}\n", encoding="utf-8")
        fleet = root / "fleet.json"
        fleet.write_text(
            json.dumps(
                {
                    "deployments": {
                        "test_IP40": {
                            "base_name": "test",
                            "ip_address": "10.0.203.40",
                            "core_profile": None,
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        patches = [
            patch.object(profiles, "ROOT", root),
            patch.object(profiles, "FLEET", fleet),
            patch.object(profiles, "DEPLOYMENTS", deployments),
            patch.object(profiles, "PROFILES", root / "ansible/core_profiles"),
            patch.object(profiles, "BUILD", root / "build"),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(temporary.cleanup)
        return root, fleet

    def create_profile(self, name="databases"):
        profiles.cmd_create(argparse.Namespace(profile=name))

    def test_profile_names_require_lowercase_kebab_case(self):
        for valid in ("docker", "databases", "vm2-tools"):
            self.assertEqual(profiles.validate_profile_name(valid), valid)
        for invalid in ("", "Docker", "docker_main", "-docker", "docker--main"):
            with self.assertRaises(profiles.ProfileError):
                profiles.validate_profile_name(invalid)

    def test_vm_names_reject_path_traversal(self):
        self.environment()
        for invalid in ("../test_IP40", "test", "/tmp/test_IP40"):
            with self.assertRaisesRegex(profiles.ProfileError, "Invalid deployment name"):
                profiles.require_base(invalid)

    def test_scaffold_creates_required_files_and_refuses_overwrite(self):
        root, _fleet = self.environment()
        self.create_profile()
        target = root / "ansible/core_profiles/databases"
        self.assertTrue((target / "site.yml").is_file())
        self.assertTrue((target / "vars.yml").is_file())
        metadata = json.loads((target / "profile.json").read_text(encoding="utf-8"))
        self.assertFalse(metadata["requires_backup_storage"])
        with self.assertRaisesRegex(profiles.ProfileError, "already exists"):
            self.create_profile()

    def test_select_validates_without_saving_assignment(self):
        _root, fleet = self.environment()
        self.create_profile()

        self.assertEqual(profiles.select_profile("test_IP40", "databases"), "databases")

        saved = json.loads(fleet.read_text(encoding="utf-8"))
        self.assertIsNone(saved["deployments"]["test_IP40"]["core_profile"])

    def test_profile_metadata_requires_boolean_storage_flag(self):
        root, _fleet = self.environment()
        self.create_profile()
        metadata = root / "ansible/core_profiles/databases/profile.json"
        metadata.write_text('{"requires_backup_storage": "yes"}\n', encoding="utf-8")
        with self.assertRaisesRegex(profiles.ProfileError, "Invalid requires_backup_storage"):
            profiles.profile_metadata("databases")

    def test_first_resolution_assigns_and_later_resolution_reuses_profile(self):
        _root, fleet = self.environment()
        self.create_profile()
        self.assertEqual(profiles.assign_profile("test_IP40", "databases"), "databases")
        self.assertEqual(profiles.assign_profile("test_IP40", None), "databases")
        saved = json.loads(fleet.read_text(encoding="utf-8"))
        self.assertEqual(saved["deployments"]["test_IP40"]["core_profile"], "databases")

    def test_resolution_rejects_a_different_assigned_profile(self):
        self.environment()
        self.create_profile("databases")
        self.create_profile("media-server")
        profiles.assign_profile("test_IP40", "databases")
        with self.assertRaisesRegex(profiles.ProfileError, "change-core-profile"):
            profiles.assign_profile("test_IP40", "media-server")

    def test_resolution_requires_profile_on_first_run(self):
        self.environment()
        with self.assertRaisesRegex(profiles.ProfileError, "has no core profile"):
            profiles.assign_profile("test_IP40", None)

    def test_base_gate_is_written_only_when_marked(self):
        self.environment()
        with self.assertRaisesRegex(profiles.ProfileError, "Base configuration has not completed"):
            profiles.require_base("test_IP40")
        profiles.cmd_mark_base(argparse.Namespace(vm="test_IP40"))
        profiles.require_base("test_IP40")
        marker = json.loads(profiles.base_marker("test_IP40").read_text(encoding="utf-8"))
        self.assertEqual(marker["vm"], "test_IP40")

    def test_explicit_change_updates_assignment(self):
        _root, fleet = self.environment()
        self.create_profile("databases")
        self.create_profile("media-server")
        profiles.assign_profile("test_IP40", "databases")
        profiles.cmd_change(argparse.Namespace(vm="test_IP40", profile="media-server", yes=True))
        saved = json.loads(fleet.read_text(encoding="utf-8"))
        self.assertEqual(saved["deployments"]["test_IP40"]["core_profile"], "media-server")


if __name__ == "__main__":
    unittest.main()
