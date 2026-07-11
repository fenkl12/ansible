import importlib.util
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

    def test_env_file_does_not_override_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "env"
            path.write_text("TRUENAS_API_KEY=file-value\n")
            with patch.dict(factory.os.environ, {"TRUENAS_API_KEY": "session-value"}, clear=False):
                factory.load_env_file(path)
                self.assertEqual(factory.os.environ["TRUENAS_API_KEY"], "session-value")


if __name__ == "__main__":
    unittest.main()

