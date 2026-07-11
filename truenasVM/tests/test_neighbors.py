import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("neighbor_factory", Path(__file__).parents[1] / "scripts/vm_factory.py")
factory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(factory)


class NeighborTests(unittest.TestCase):
    @patch.object(factory.subprocess, "run")
    def test_failed_probes_are_not_allocations(self, run):
        run.return_value.stdout = (
            "10.0.203.40 dev ens18 FAILED\n"
            "10.0.203.50 dev ens18 INCOMPLETE\n"
            "10.0.203.60 dev ens18 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n"
        )
        self.assertEqual(factory.neighbor_addresses(), {"10.0.203.60"})


if __name__ == "__main__":
    unittest.main()
