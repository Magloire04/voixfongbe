import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from voixfongbe.demandes import ChampInvalide, Demandes, DemandesFermees, TropDeDemandes, proposer_nom, valider
from voixfongbe.quotas import FUSEAU

T = datetime(2026, 11, 9, 22, 30, tzinfo=FUSEAU)
DESCRIPTION = "Application d'alphabétisation en fon pour des adultes."


def donnees(**autres):
    return {"nom": "Koffi A.", "courriel": "koffi@exemple.bj", "organisation": "UAC",
            "description": DESCRIPTION, "accord": True, **autres}


class TestValider(unittest.TestCase):
    def champ(self, **autres):
        with self.assertRaises(ChampInvalide) as e:
            valider(donnees(**autres))
        self.assertTrue(e.exception.message)
        return e.exception.champ

    def test_valider_retire_les_blancs(self):
        self.assertEqual(valider(donnees(nom="  Koffi A. ", organisation=" UAC ", description=f" {DESCRIPTION} ")),
                         {"nom": "Koffi A.", "courriel": "koffi@exemple.bj", "organisation": "UAC",
                          "description": DESCRIPTION})

    def test_organisation_facultative(self):
        sans = donnees()
        del sans["organisation"]
        self.assertEqual(valider(sans)["organisation"], "")

    def test_longueurs(self):
        self.assertEqual(self.champ(description="x" * 19), "description")
        self.assertEqual(self.champ(description="x" * 1001), "description")
        self.assertEqual(self.champ(nom=" "), "nom")
        self.assertEqual(self.champ(nom="x" * 101), "nom")
        self.assertEqual(self.champ(organisation="x" * 121), "organisation")
        self.assertEqual(self.champ(courriel="pas-une-adresse"), "courriel")
        self.assertEqual(valider(donnees(description="x" * 1000))["description"], "x" * 1000)

    def test_champ_qui_n_est_pas_du_texte(self):
        self.assertEqual(self.champ(nom=12), "nom")
        self.assertEqual(self.champ(description=None), "description")

    def test_accord_obligatoire(self):
        for valeur in (False, "true", 1):
            self.assertEqual(self.champ(accord=valeur), "accord", valeur)
        sans = donnees()
        del sans["accord"]
        with self.assertRaises(ChampInvalide):
            valider(sans)

    def test_retour_a_la_ligne_refuse_dans_les_champs_d_une_ligne(self):  # point de vigilance 5
        self.assertEqual(self.champ(nom="Koffi\r\nBcc: x@y.bj"), "nom")
        self.assertEqual(self.champ(courriel="k@exemple.bj\nBcc: x@y.bj"), "courriel")
        self.assertEqual(self.champ(organisation="UAC Bcc"), "organisation")
        deux_lignes = valider(donnees(description="Première ligne du projet.\r\nSeconde ligne\x00 ici."))
        self.assertEqual(deux_lignes["description"], "Première ligne du projet.\nSeconde ligne ici.")

    def test_balises_gardees_en_texte(self):
        self.assertEqual(valider(donnees(nom="<img src=x onerror=alert(1)>"))["nom"], "<img src=x onerror=alert(1)>")


class TestProposerNom(unittest.TestCase):
    def test_proposer_nom(self):
        self.assertEqual(proposer_nom("Koffi A.", "Université d'Abomey-Calavi", set()), "universite-d-abomey-calavi")
        self.assertEqual(proposer_nom("Ɖokpɔ́ Sɛ́", "", set()), "dokpo-se")
        self.assertEqual(proposer_nom("Alpha", "", {"alpha", "alpha-2"}), "alpha-3")
        self.assertEqual(proposer_nom("李雷", "", {"projet"}), "projet-2")
        long = proposer_nom("x", "Organisation " * 6, {proposer_nom("x", "Organisation " * 6, set())})
        self.assertRegex(long, r"^[a-z0-9-]{2,40}$")
        self.assertTrue(long.endswith("-2"))


class TestDemandes(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dossier)
        self.chemin = self.dossier / "demandes.json"
        self.demandes = Demandes(self.chemin)

    def deposer(self, ip="203.0.113.7", maintenant=T, demandes=None, **autres):
        return (demandes or self.demandes).deposer(valider(donnees(**autres)), ip=ip, maintenant=maintenant,
                                                   pris=set())

    def test_depot_garde_la_demande_et_propose_un_nom(self):
        fiche = self.deposer()
        seconde = self.deposer()
        self.assertRegex(fiche["id"], r"^[0-9a-f]{16}$")
        self.assertEqual((fiche["etat"], fiche["projet_propose"], fiche["nom"]), ("en_attente", "uac", "Koffi A."))
        self.assertEqual(seconde["projet_propose"], "uac-2")
        self.assertEqual([d["id"] for d in Demandes(self.chemin).en_attente()], [fiche["id"], seconde["id"]])
        self.assertEqual(Demandes(self.chemin).obtenir(fiche["id"])["courriel"], "koffi@exemple.bj")
        self.assertIsNone(self.demandes.obtenir("0" * 16))

    def test_trois_demandes_par_ip_et_par_jour(self):
        for _ in range(3):
            self.deposer()
        with self.assertRaises(TropDeDemandes):
            self.deposer()
        self.deposer(ip="198.51.100.4")
        self.deposer(maintenant=T + timedelta(hours=2))  # le lendemain à Porto-Novo

    def test_ip_jamais_en_clair(self):
        self.deposer()
        self.assertNotIn("203.0.113.7", self.chemin.read_text(encoding="utf-8"))

    def test_fermees_a_50_en_attente(self):
        demandes = Demandes(self.chemin, max_en_attente=50, par_ip=1000)
        for _ in range(50):
            self.deposer(demandes=demandes)
        self.assertTrue(demandes.fermees())
        with self.assertRaises(DemandesFermees):
            self.deposer(demandes=demandes)

    def test_decision_unique(self):  # point de vigilance 3
        ident = self.deposer()["id"]
        self.demandes.marquer_approuvee(ident, "uac", T)
        with self.assertRaises(ValueError):
            self.demandes.marquer_approuvee(ident, "uac", T)
        with self.assertRaises(ValueError):
            self.demandes.marquer_refusee(ident, None, T)
        with self.assertRaises(KeyError):
            self.demandes.marquer_refusee("0" * 16, None, T)
        fiche = self.demandes.obtenir(ident)
        self.assertEqual((fiche["etat"], fiche["projet"]), ("approuvee", "uac"))
        self.assertEqual(self.demandes.en_attente(), [])

    def test_historique_plus_recentes_d_abord(self):
        a = self.deposer()["id"]
        b = self.deposer(ip="198.51.100.4")["id"]
        self.demandes.marquer_refusee(a, "Projet commercial.", T)
        self.demandes.marquer_approuvee(b, "uac", T + timedelta(minutes=1))
        historique = self.demandes.historique(T + timedelta(minutes=2))
        self.assertEqual([d["id"] for d in historique], [b, a])
        self.assertEqual(historique[1]["motif"], "Projet commercial.")

    def test_refusees_effacees_apres_90_jours(self):
        refusee = self.deposer()["id"]
        approuvee = self.deposer(ip="198.51.100.4")["id"]
        self.demandes.marquer_refusee(refusee, None, T)
        self.demandes.marquer_approuvee(approuvee, "uac", T)
        self.assertEqual(len(self.demandes.historique(T + timedelta(days=89))), 2)
        self.assertEqual([d["id"] for d in self.demandes.historique(T + timedelta(days=91))], [approuvee])
        self.assertIsNone(self.demandes.obtenir(refusee))

    def test_effacer_projet(self):
        ident = self.deposer()["id"]
        self.demandes.marquer_approuvee(ident, "alpha", T)
        self.demandes.effacer_projet("alpha")
        self.assertIsNone(self.demandes.obtenir(ident))
        self.assertEqual(self.demandes.historique(T), [])


if __name__ == "__main__":
    unittest.main()
