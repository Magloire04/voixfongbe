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
        self.assertEqual(self.reglages().lire(), {"adresse": "eliseeatonde@gmail.com", "plafond": 300,
                                                  "api_coupee": False})

    def test_couper_et_retablir_l_api(self):
        r = self.reglages()
        r.modifier(api_coupee=True)
        self.assertTrue(self.reglages().lire()["api_coupee"])
        r.modifier(api_coupee=False)
        self.assertFalse(self.reglages().lire()["api_coupee"])
        for mauvaise in ("oui", 1):
            with self.assertRaises(ValueError):
                r.modifier(api_coupee=mauvaise)
        r.modifier(plafond=400)  # sans api_coupee : rien ne change
        self.assertFalse(self.reglages().lire()["api_coupee"])

    def test_reglages_modifies_et_controles(self):
        r = self.reglages()
        with self.assertRaises(ValueError):
            r.modifier(plafond=0)
        with self.assertRaises(ValueError):
            r.modifier(adresse="pas-une-adresse")
        r.modifier(plafond=500)
        self.assertEqual(self.reglages().lire(), {"adresse": "eliseeatonde@gmail.com", "plafond": 500, "api_coupee": False})
        r.modifier(adresse=" elisee@exemple.bj ")
        self.assertEqual(self.reglages().lire(), {"adresse": "elisee@exemple.bj", "plafond": 500, "api_coupee": False})


if __name__ == "__main__":
    unittest.main()
