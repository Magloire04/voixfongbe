import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

POINT_D_ENTREE = Path(__file__).resolve().parent.parent / "passenger_wsgi.py"


class TestPassenger(unittest.TestCase):
    def test_point_d_entree_se_charge_hors_du_dossier(self):
        """Le chargeur de Passenger n'ajoute pas forcément le dossier de l'application à sys.path."""
        with tempfile.TemporaryDirectory() as ailleurs:
            r = subprocess.run([sys.executable, "-c",
                                f"import runpy; m = runpy.run_path(r'{POINT_D_ENTREE}'); "
                                "assert callable(m['application'])"],
                               cwd=ailleurs, capture_output=True, text=True,
                               env={"VOIX_STOCKAGE_DIR": str(Path(ailleurs) / "stockage"), "SYSTEMROOT": "C:\\Windows"})
        self.assertEqual(r.returncode, 0, r.stderr[-500:])


if __name__ == "__main__":
    unittest.main()
