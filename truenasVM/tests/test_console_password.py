import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("console_password", Path(__file__).parents[1] / "scripts/console_password.py")
console = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(console)


class ConsolePasswordTests(unittest.TestCase):
    def test_password_is_fixed_for_every_vm(self):
        self.assertEqual(console.password_for_vm("test_IP40"), "fenkil")
        self.assertEqual(console.password_for_vm("other_IP50"), "fenkil")

    def test_password_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            console.password_for_vm("../other")


if __name__ == "__main__":
    unittest.main()
