import shutil
import tempfile
import unittest
from pathlib import Path

from voixfongbe.cles import Cles


class TestCles(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dossier)
        self.chemin = self.dossier / "cles.json"

    def test_cle_creee_est_reconnue(self):
        cle = Cles(self.chemin).creer("demo-collegue")
        self.assertGreaterEqual(len(cle), 40)
        self.assertEqual(Cles(self.chemin).verifier(cle), "demo-collegue")

    def test_cle_inconnue_rend_none(self):
        Cles(self.chemin).creer("demo")
        self.assertIsNone(Cles(self.chemin).verifier("pas-la-bonne"))
        self.assertIsNone(Cles(self.chemin).verifier(""))

    def test_fichier_ne_contient_pas_la_cle_en_clair(self):
        cle = Cles(self.chemin).creer("demo")
        self.assertNotIn(cle, self.chemin.read_text(encoding="utf-8"))

    def test_revoquer_rend_la_cle_inutilisable(self):
        cles = Cles(self.chemin)
        cle = cles.creer("demo")
        self.assertTrue(cles.revoquer("demo"))
        self.assertIsNone(cles.verifier(cle))
        self.assertFalse(cles.revoquer("demo"))

    def test_nom_de_projet_invalide_refuse(self):
        for nom in ("Mon Projet", "a", "x" * 41, "démo"):
            with self.assertRaises(ValueError, msg=nom):
                Cles(self.chemin).creer(nom)

    def test_projet_en_double_refuse(self):
        Cles(self.chemin).creer("demo")
        with self.assertRaises(ValueError):
            Cles(self.chemin).creer("demo")

    def test_lister_donne_projets_et_dates_sans_empreinte(self):
        Cles(self.chemin).creer("demo")
        liste = Cles(self.chemin).lister()
        self.assertEqual([x["projet"] for x in liste], ["demo"])
        self.assertEqual(set(liste[0]), {"projet", "cree_le"})


if __name__ == "__main__":
    unittest.main()
