import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.aides import CourrielFactice
from voixfongbe.cles import Cles
from voixfongbe.connexion import Connexion, mdp_correct

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def charger(nom: str):
    spec = importlib.util.spec_from_file_location(f"script_{nom}", SCRIPTS / f"{nom}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestScripts(unittest.TestCase):
    def setUp(self):
        self.stockage = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.stockage)
        environnement = mock.patch.dict(os.environ, {"VOIX_STOCKAGE_DIR": str(self.stockage)})
        environnement.start()
        self.addCleanup(environnement.stop)
        self.admin = charger("admin")

    def lancer(self, module, argv, saisies=(), secrets=()):
        sortie, erreurs = io.StringIO(), io.StringIO()
        with mock.patch("builtins.input", side_effect=list(saisies)), \
                mock.patch("getpass.getpass", side_effect=list(secrets)), \
                contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(erreurs):
            code = module.main(argv)
        return code, sortie.getvalue() + erreurs.getvalue()

    def test_mot_de_passe_enregistre(self):
        code, sortie = self.lancer(self.admin, ["mot-de-passe"], secrets=["un-mot-de-passe-solide"] * 2)
        self.assertEqual(code, 0)
        self.assertIn("Toutes les sessions sont fermées", sortie)
        self.assertTrue(Connexion(self.stockage / "admin.json").configure())
        empreinte = json.loads((self.stockage / "admin.json").read_text(encoding="utf-8"))["mdp"]
        self.assertTrue(mdp_correct("un-mot-de-passe-solide", empreinte))
        self.assertNotIn("un-mot-de-passe-solide", sortie)

    def test_mot_de_passe_differents_ou_court(self):
        code, _ = self.lancer(self.admin, ["mot-de-passe"], secrets=["un-mot-de-passe-solide", "un-autre-mot-de-passe"])
        self.assertEqual(code, 1)
        code, _ = self.lancer(self.admin, ["mot-de-passe"], secrets=["court", "court"])
        self.assertEqual(code, 1)
        self.assertFalse(Connexion(self.stockage / "admin.json").configure())

    def test_mot_de_passe_envoie_l_alerte_si_l_envoi_est_configure(self):
        courriel = CourrielFactice()
        with mock.patch.object(self.admin, "Courriel", return_value=courriel):
            self.lancer(self.admin, ["mot-de-passe"], secrets=["un-mot-de-passe-solide"] * 2)
        self.assertEqual([e["a"] for e in courriel.envoyes], ["eliseeatonde@gmail.com"])

    def test_smtp_ecrit_sans_afficher_le_mot_de_passe(self):
        code, sortie = self.lancer(self.admin, ["smtp"], saisies=["", "", "envoi@bytechnum.com", ""],
                                   secrets=["mdp-de-la-boite-42"])
        self.assertEqual(code, 0)
        reglages = json.loads((self.stockage / "smtp.json").read_text(encoding="utf-8"))
        self.assertEqual(reglages, {"hote": "mail.spacemail.com", "port": 465, "utilisateur": "envoi@bytechnum.com",
                                    "mot_de_passe": "mdp-de-la-boite-42", "expediteur": "envoi@bytechnum.com"})
        self.assertNotIn("mdp-de-la-boite-42", sortie)

    def test_smtp_adresse_invalide(self):
        code, _ = self.lancer(self.admin, ["smtp"], saisies=["", "", "pas-une-adresse", ""], secrets=["x"])
        self.assertEqual(code, 1)
        self.assertFalse((self.stockage / "smtp.json").exists())

    def test_essai_smtp(self):
        code, sortie = self.lancer(self.admin, ["essai-smtp"])
        self.assertEqual(code, 1)
        self.assertIn("pas configurée", sortie)
        courriel = CourrielFactice()
        with mock.patch.object(self.admin, "Courriel", return_value=courriel):
            code, sortie = self.lancer(self.admin, ["essai-smtp"])
        self.assertEqual((code, courriel.envoyes[0]["a"]), (0, "eliseeatonde@gmail.com"))

    def test_lister_affiche_etat_et_limite(self):
        cles_script = charger("cles")
        cles = Cles(self.stockage / "cles.json")
        cles.creer("demo")
        cles.changer_limite("demo", 250)
        cles.creer("ancien")
        cles.revoquer("ancien")
        code, sortie = self.lancer(cles_script, ["lister"])
        self.assertEqual(code, 0)
        ligne = next(x for x in sortie.splitlines() if x.startswith("demo"))
        self.assertIn("active", ligne)
        self.assertIn("250", ligne)
        self.assertIn("révoquée", next(x for x in sortie.splitlines() if x.startswith("ancien")))


if __name__ == "__main__":
    unittest.main()
