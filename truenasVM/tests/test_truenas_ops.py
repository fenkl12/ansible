import importlib.util
import tempfile
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
