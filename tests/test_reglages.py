import shutil
import tempfile
import unittest
from pathlib import Path

from voixfongbe.reglages import Reglages


class TestReglages(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dossier)
        self.chemin = self.dossier / "reglages.json"

    def reglages(self):
        return Reglages(self.chemin, "eliseeatonde@gmail.com", 300)

    def test_reglages_par_defaut(self):
        self.assertEqual(self.reglages().lire(), {"adresse": "eliseeatonde@gmail.com", "plafond": 300})

    def test_reglages_modifies_et_controles(self):
        r = self.reglages()
        with self.assertRaises(ValueError):
            r.modifier(plafond=0)
        with self.assertRaises(ValueError):
            r.modifier(adresse="pas-une-adresse")
        r.modifier(plafond=500)
        self.assertEqual(self.reglages().lire(), {"adresse": "eliseeatonde@gmail.com", "plafond": 500})
        r.modifier(adresse=" elisee@exemple.bj ")
        self.assertEqual(self.reglages().lire(), {"adresse": "elisee@exemple.bj", "plafond": 500})


if __name__ == "__main__":
    unittest.main()
