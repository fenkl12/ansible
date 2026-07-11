import importlib.util
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
