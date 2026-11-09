import os
import shutil
import tempfile
import unittest
from pathlib import Path

from voixfongbe.stockage import ecrire_json, lire_json, verrou


class TestStockage(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dossier)

    def test_lire_un_fichier_absent_rend_le_defaut(self):
        self.assertEqual(lire_json(self.dossier / "absent.json", {"a": 1}), {"a": 1})

    def test_ecrire_puis_relire(self):
        ecrire_json(self.dossier / "x.json", {"projets": {"démo": 1}})
        self.assertEqual(lire_json(self.dossier / "x.json", None), {"projets": {"démo": 1}})

    def test_ecriture_atomique_ne_laisse_pas_de_fichier_temporaire(self):
        ecrire_json(self.dossier / "x.json", [1, 2])
        ecrire_json(self.dossier / "x.json", [3])
        self.assertEqual(sorted(p.name for p in self.dossier.iterdir()), ["x.json"])

    @unittest.skipIf(os.name == "nt", "droits Unix")
    def test_ecrit_en_droits_600(self):
        ecrire_json(self.dossier / "x.json", {})
        self.assertEqual((self.dossier / "x.json").stat().st_mode & 0o777, 0o600)

    def test_verrou_se_reprend_apres_liberation(self):
        with verrou(self.dossier / "x.json"):
            pass
        with verrou(self.dossier / "x.json"):
            pass


if __name__ == "__main__":
    unittest.main()
