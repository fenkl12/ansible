import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("login_password", Path(__file__).parents[1] / "scripts/login_password.py")
login = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(login)


class LoginPasswordTests(unittest.TestCase):
    def test_password_and_hash_are_fixed(self):
        password, password_hash = login.password_and_hash("test_IP40")

        self.assertEqual(password, "fenkil")
        self.assertTrue(password_hash.startswith("$6$"))
        self.assertEqual(password_hash, login.password_and_hash("other_IP50")[1])

    def test_password_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            login.password_and_hash("../other")


if __name__ == "__main__":
    unittest.main()
