import hashlib
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from voixfongbe.cles import Cles
from voixfongbe.quotas import FUSEAU

T = datetime(2026, 11, 9, 22, 30, tzinfo=FUSEAU)
CHAMPS_LISTE = {"projet", "cree_le", "limite", "courriel", "nom", "organisation", "etat", "lien_expire_le"}


class TestCles(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dossier)
        self.chemin = self.dossier / "cles.json"
        self.cles = Cles(self.chemin)

    def etat(self, projet, maintenant=T):
        return {x["projet"]: x["etat"] for x in self.cles.lister(maintenant)}[projet]

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
        self.assertFalse(cles.revoquer("inconnu"))

    def test_nom_de_projet_invalide_refuse(self):
        for nom in ("Mon Projet", "a", "x" * 41, "démo", "demo\n"):
            with self.assertRaises(ValueError, msg=repr(nom)):
                Cles(self.chemin).creer(nom)
            with self.assertRaises(ValueError, msg=repr(nom)):
                self.cles.preparer(nom, courriel="koffi@exemple.bj", maintenant=T)

    def test_projet_en_double_refuse(self):
        Cles(self.chemin).creer("demo")
        with self.assertRaises(ValueError):
            Cles(self.chemin).creer("demo")

    def test_lister_donne_projets_et_dates_sans_empreinte(self):
        Cles(self.chemin).creer("demo")
        liste = Cles(self.chemin).lister()
        self.assertEqual([x["projet"] for x in liste], ["demo"])
        self.assertEqual(set(liste[0]), CHAMPS_LISTE)

    # Ancien format, liens d'accès, limites
    def test_ancien_format_reste_valable(self):  # point de vigilance 2
        self.chemin.write_text(json.dumps({"projets": {"projet-collegue": {
            "empreinte": hashlib.sha256(b"cle-ancienne").hexdigest(), "cree_le": "2026-11-09T12:00:00+00:00"}}}))
        cles = Cles(self.chemin)
        self.assertEqual(cles.verifier("cle-ancienne"), "projet-collegue")
        self.assertEqual(cles.limite("projet-collegue"), 100)
        self.assertEqual(cles.lister(T)[0]["etat"], "active")

    def test_lien_utilise_une_seule_fois(self):
        jeton = self.cles.preparer("alpha", courriel="koffi@exemple.bj", maintenant=T)
        self.assertEqual(len(jeton), 43)
        self.assertEqual(self.cles.lien_valide(jeton, T), "alpha")
        self.assertEqual(self.etat("alpha"), "lien_en_attente")
        projet, cle = self.cles.utiliser_lien(jeton, T)
        self.assertEqual((projet, self.cles.verifier(cle)), ("alpha", "alpha"))
        self.assertIsNone(self.cles.utiliser_lien(jeton, T))
        self.assertIsNone(self.cles.lien_valide(jeton, T))
        self.assertEqual(self.etat("alpha"), "active")
        contenu = self.chemin.read_text(encoding="utf-8")
        self.assertNotIn(jeton, contenu)
        self.assertNotIn(cle, contenu)

    def test_preparer_garde_les_coordonnees(self):
        self.cles.preparer("alpha", courriel="koffi@exemple.bj", limite=200, nom="Koffi A.",
                           organisation="UAC", maintenant=T)
        fiche = self.cles.lister(T)[0]
        self.assertEqual((fiche["courriel"], fiche["limite"], fiche["nom"], fiche["organisation"]),
                         ("koffi@exemple.bj", 200, "Koffi A.", "UAC"))
        self.assertEqual(datetime.fromisoformat(fiche["lien_expire_le"]), T + timedelta(days=7))

    def test_lien_expire_apres_7_jours(self):
        jeton = self.cles.preparer("alpha", courriel="koffi@exemple.bj", maintenant=T)
        self.assertEqual(self.cles.lien_valide(jeton, T + timedelta(days=7, seconds=-1)), "alpha")
        apres = T + timedelta(days=7, seconds=1)
        self.assertIsNone(self.cles.lien_valide(jeton, apres))
        self.assertIsNone(self.cles.utiliser_lien(jeton, apres))
        self.assertEqual(self.etat("alpha", apres), "lien_expire")

    def test_nouveau_lien_revoque_la_cle_actuelle(self):
        jeton = self.cles.preparer("alpha", courriel="koffi@exemple.bj", maintenant=T)
        _, ancienne = self.cles.utiliser_lien(jeton, T)
        nouveau = self.cles.nouveau_lien("alpha", T)
        self.assertIsNone(self.cles.verifier(ancienne))
        self.assertIsNone(self.cles.lien_valide(jeton, T))
        self.assertEqual(self.etat("alpha"), "lien_en_attente")
        _, cle = self.cles.utiliser_lien(nouveau, T)
        self.assertEqual(self.cles.verifier(cle), "alpha")

    def test_nouveau_lien_sans_adresse_refuse(self):
        self.cles.creer("projet-collegue")
        with self.assertRaises(ValueError):
            self.cles.nouveau_lien("projet-collegue", T)

    def test_revoquer_annule_le_lien_en_attente(self):
        jeton = self.cles.preparer("alpha", courriel="koffi@exemple.bj", maintenant=T)
        self.assertTrue(self.cles.revoquer("alpha", T))
        self.assertIsNone(self.cles.lien_valide(jeton, T))
        self.assertIsNone(self.cles.utiliser_lien(jeton, T))
        self.assertEqual(self.etat("alpha"), "revoquee")

    def test_supprimer_seulement_un_projet_revoque(self):
        self.cles.creer("demo")
        with self.assertRaises(ValueError):
            self.cles.supprimer("demo")
        self.cles.revoquer("demo")
        self.assertTrue(self.cles.supprimer("demo"))
        self.assertEqual(self.cles.lister(), [])
        self.assertFalse(self.cles.supprimer("demo"))

    def test_creer_en_ssh_reactive_un_projet_revoque(self):
        self.cles.creer("demo")
        self.cles.revoquer("demo")
        cle = self.cles.creer("demo")
        self.assertEqual(self.cles.verifier(cle), "demo")
        self.assertEqual(self.etat("demo"), "active")

    def test_creer_en_ssh_annule_un_lien_en_attente(self):
        jeton = self.cles.preparer("alpha", courriel="koffi@exemple.bj", maintenant=T)
        self.cles.creer("alpha")
        self.assertIsNone(self.cles.lien_valide(jeton, T))

    def test_limite_bornee(self):
        self.cles.creer("demo")
        for mauvaise in (0, 1_000_001, True, "100", 2.5):
            with self.assertRaises(ValueError, msg=repr(mauvaise)):
                self.cles.changer_limite("demo", mauvaise)
        self.cles.changer_limite("demo", 1_000_000)
        self.assertEqual(self.cles.limite("demo"), 1_000_000)
        with self.assertRaises(KeyError):
            self.cles.changer_limite("inconnu", 10)
        self.assertEqual(self.cles.limite("inconnu"), 100)

    def test_changer_courriel(self):
        self.cles.creer("projet-collegue")
        with self.assertRaises(ValueError):
            self.cles.changer_courriel("projet-collegue", "pas-une-adresse")
        self.cles.changer_courriel("projet-collegue", "collegue@exemple.bj")
        self.assertEqual(self.cles.lister()[0]["courriel"], "collegue@exemple.bj")
        self.cles.nouveau_lien("projet-collegue", T)  # ne lève plus

    def test_preparer_nom_pris_refuse(self):
        self.cles.creer("alpha")
        with self.assertRaises(ValueError):
            self.cles.preparer("alpha", courriel="koffi@exemple.bj", maintenant=T)

    def test_preparer_courriel_invalide_refuse(self):
        with self.assertRaises(ValueError):
            self.cles.preparer("alpha", courriel="pas-une-adresse", maintenant=T)


if __name__ == "__main__":
    unittest.main()
