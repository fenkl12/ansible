import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import call, patch


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("restart_vm", SCRIPTS / "restart_vm.py")
restart = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restart)
sys.path.pop(0)


class RestartTests(unittest.TestCase):
    def deployment(self, root: Path) -> None:
        path = root / "deployments" / "test_IP40"
        path.mkdir(parents=True)
        (path / "deployment.auto.tfvars.json").write_text(
            '{"vm_name": "test_IP40"}\n', encoding="utf-8"
        )

    @patch.object(restart.time, "sleep")
    @patch.object(restart, "api")
    def test_waits_for_stop_job_before_starting(self, api, _sleep):
        api.side_effect = [
            [{"id": 40, "name": "test_IP40", "status": {"state": "RUNNING"}}],
            123,
            [{"id": 123, "state": "RUNNING"}],
            [{"id": 123, "state": "SUCCESS"}],
            [{"id": 40, "status": {"state": "STOPPED"}}],
            True,
            [{"id": 40, "status": {"state": "RUNNING"}}],
            [{"id": 40, "status": {"state": "RUNNING"}}],
        ]
        with tempfile.TemporaryDirectory() as directory, patch.object(restart, "ROOT", Path(directory)):
            self.deployment(Path(directory))
            restart.restart("test_IP40")

        self.assertEqual(
            api.call_args_list,
            [
                call("vm"),
                call("vm/id/40/stop", {"force": False, "force_after_timeout": True}),
                call("core/get_jobs"),
                call("core/get_jobs"),
                call("vm"),
                call("vm/id/40/start", {}),
                call("vm"),
                call("vm"),
            ],
        )

    @patch.object(restart.time, "sleep")
    @patch.object(restart, "api")
    def test_already_stopped_vm_starts_without_stop_job(self, api, _sleep):
        api.side_effect = [
            [{"id": 40, "name": "test_IP40", "status": {"state": "STOPPED"}}],
            True,
            [{"id": 40, "status": {"state": "RUNNING"}}],
            [{"id": 40, "status": {"state": "RUNNING"}}],
        ]
        with tempfile.TemporaryDirectory() as directory, patch.object(restart, "ROOT", Path(directory)):
            self.deployment(Path(directory))
            restart.restart("test_IP40")

        self.assertEqual(
            api.call_args_list,
            [call("vm"), call("vm/id/40/start", {}), call("vm"), call("vm")],
        )

    @patch.object(restart, "api", return_value=False)
    def test_start_requires_true_nas_confirmation(self, _api):
        with self.assertRaisesRegex(restart.RestartError, "rejected start"):
            restart.start_and_wait(40)

    @patch.object(restart.time, "sleep")
    @patch.object(restart, "api")
    def test_null_start_response_is_confirmed_by_observed_state(self, api, _sleep):
        api.side_effect = [
            None,
            [{"id": 40, "status": {"state": "RUNNING"}}],
            [{"id": 40, "status": {"state": "RUNNING"}}],
        ]

        result = restart.start_and_wait(40)

        self.assertEqual(result["status"]["state"], "RUNNING")

    @patch.object(restart.time, "sleep")
    @patch.object(restart, "api")
    def test_transient_running_state_is_rejected(self, api, _sleep):
        api.side_effect = [
            True,
            [{"id": 40, "status": {"state": "RUNNING"}}],
            [{"id": 40, "status": {"state": "STOPPED"}}],
        ]
        with self.assertRaisesRegex(restart.RestartError, "was not stable"):
            restart.start_and_wait(40)

    @patch.object(restart, "api")
    def test_terminal_stop_job_failure_does_not_start_vm(self, api):
        for state in ("FAILED", "ABORTED"):
            with self.subTest(state=state):
                api.reset_mock()
                api.side_effect = [
                    [{"id": 40, "name": "test_IP40", "status": {"state": "RUNNING"}}],
                    123,
                    [{"id": 123, "state": state, "error": "guest did not stop"}],
                ]
                with tempfile.TemporaryDirectory() as directory, patch.object(restart, "ROOT", Path(directory)):
                    self.deployment(Path(directory))
                    with self.assertRaisesRegex(restart.RestartError, "guest did not stop"):
                        restart.restart("test_IP40")
                self.assertNotIn(call("vm/id/40/start", {}), api.call_args_list)

    @patch.object(restart, "api", return_value=[])
    def test_disappeared_stop_job_fails(self, _api):
        with self.assertRaisesRegex(restart.RestartError, "job disappeared"):
            restart.wait_for_job(123)

    @patch.object(restart.time, "monotonic", side_effect=[0, 181])
    @patch.object(restart, "api", return_value=[{"id": 123, "state": "RUNNING"}])
    def test_stop_job_timeout_fails(self, _api, _monotonic):
        with self.assertRaisesRegex(restart.RestartError, "Timed out"):
            restart.wait_for_job(123)


if __name__ == "__main__":
    unittest.main()
