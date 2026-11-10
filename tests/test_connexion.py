import json
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from voixfongbe.connexion import Bloque, Connexion, PasConfigure, TropDeCodes, empreinte_mdp, mdp_correct
from voixfongbe.quotas import FUSEAU

T = datetime(2026, 11, 9, 22, 30, tzinfo=FUSEAU)
MDP = "un-mot-de-passe-solide"
IP = "203.0.113.7"


def apres(**duree):
    return T + timedelta(**duree)


class TestEmpreinte(unittest.TestCase):
    def test_format_d_empreinte(self):
        e = empreinte_mdp(MDP)
        self.assertRegex(e, r"^scrypt:[0-9a-f]{32}:[0-9a-f]{128}$")
        self.assertTrue(mdp_correct(MDP, e))
        self.assertFalse(mdp_correct("un-autre-mot-de-passe", e))
        self.assertFalse(mdp_correct(MDP, "pas-une-empreinte"))
        self.assertNotEqual(empreinte_mdp(MDP), e)  # sel différent à chaque fois


class TestConnexion(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dossier)
        self.chemin = self.dossier / "admin.json"
        self.c = Connexion(self.chemin)
        self.c.definir_mdp(MDP, T)

    def test_mdp_trop_court(self):
        with self.assertRaises(ValueError):
            self.c.definir_mdp("x" * 11, T)
        self.c.definir_mdp("x" * 12, T)

    def test_session_ouverte_et_jeton_absent_du_fichier(self):
        self.assertTrue(self.c.configure())
        jeton = self.c.ouvrir(MDP, IP, T)
        self.assertGreaterEqual(len(jeton), 43)
        self.assertTrue(self.c.valide(jeton, T))
        self.assertFalse(self.c.valide("pas-le-bon", T))
        self.assertFalse(self.c.valide(None, T))
        contenu = self.chemin.read_text(encoding="utf-8")
        self.assertNotIn(jeton, contenu)
        self.assertNotIn(MDP, contenu)

    def test_mauvais_mdp(self):
        self.assertIsNone(self.c.ouvrir("pas-le-bon-mot-de-passe", IP, T))

    def test_session_expire_apres_10_minutes_sans_activite(self):
        jeton = self.c.ouvrir(MDP, IP, T)
        self.assertTrue(self.c.valide(jeton, apres(minutes=9)))
        self.assertTrue(self.c.valide(jeton, apres(minutes=18)))
        self.assertFalse(self.c.valide(jeton, apres(minutes=28, seconds=1)))

    def test_fermer(self):
        jeton = self.c.ouvrir(MDP, IP, T)
        self.c.fermer(jeton)
        self.assertFalse(self.c.valide(jeton, T))

    def test_sessions_partagees_entre_instances(self):
        jeton = self.c.ouvrir(MDP, IP, T)
        self.assertTrue(Connexion(self.chemin).valide(jeton, T))

    def test_trois_echecs_bloquent_l_ip_10_minutes(self):
        for _ in range(3):
            self.assertIsNone(self.c.ouvrir("faux-faux-faux", IP, T))
        with self.assertRaises(Bloque) as e:
            self.c.ouvrir(MDP, IP, T)
        self.assertEqual(e.exception.attente_s, 600)
        self.assertIsNotNone(self.c.ouvrir(MDP, "198.51.100.4", T))
        self.assertIsNotNone(self.c.ouvrir(MDP, IP, apres(minutes=10, seconds=1)))

    def test_confirmer_le_mot_de_passe_sans_ouvrir_de_session(self):
        avant = len(json.loads(self.chemin.read_text(encoding="utf-8"))["sessions"])
        self.assertTrue(self.c.confirmer(MDP, IP, T))
        self.assertEqual(len(json.loads(self.chemin.read_text(encoding="utf-8"))["sessions"]), avant)
        for _ in range(3):
            self.assertFalse(self.c.confirmer("faux-faux-faux", IP, T))
        with self.assertRaises(Bloque):  # les erreurs de confirmation comptent comme celles de connexion
            self.c.ouvrir(MDP, IP, T)

    def test_alerte_apres_dix_echecs_par_heure_toutes_adresses(self):
        # Un attaquant qui change d'adresse échappe au blocage par adresse : l'administrateur est prévenu.
        for i in range(9):
            self.c.ouvrir("faux-faux-faux", f"203.0.113.{i}", T)
            self.assertIsNone(self.c.alerte_due(T))
        self.c.ouvrir("faux-faux-faux", "203.0.113.9", T)
        self.assertEqual(self.c.alerte_due(T), 10)
        self.c.ouvrir("faux-faux-faux", "203.0.113.10", T)
        self.assertIsNone(self.c.alerte_due(T))  # une seule alerte par heure
        plus_tard = apres(hours=1, minutes=1)
        self.assertIsNone(self.c.alerte_due(plus_tard))  # les échecs de l'heure passée ne comptent plus
        for i in range(10):
            self.c.confirmer("faux-faux-faux", f"198.51.100.{i}", plus_tard)
        self.assertEqual(self.c.alerte_due(plus_tard), 10)

    def test_ip_jamais_en_clair(self):
        self.c.ouvrir("faux-faux-faux", IP, T)
        self.assertNotIn(IP, self.chemin.read_text(encoding="utf-8"))

    def test_succes_remet_le_compteur(self):
        for essai in ("faux-1", "faux-2", MDP, "faux-3", "faux-4"):
            self.c.ouvrir(essai, IP, T)
        self.assertIsNotNone(self.c.ouvrir(MDP, IP, T))

    def test_code_change_le_mdp_et_ferme_les_sessions(self):
        jeton = self.c.ouvrir(MDP, IP, T)
        for _ in range(3):
            self.c.ouvrir("faux-faux-faux", IP, T)
        code = self.c.demander_code(T)
        self.assertRegex(code, r"^[0-9]{8}$")
        self.assertTrue(self.c.changer_avec_code(code, "nouveau-mot-de-passe", apres(minutes=2)))
        self.assertFalse(self.c.valide(jeton, apres(minutes=2)))
        self.assertIsNone(self.c.ouvrir(MDP, IP, apres(minutes=2)))
        self.assertIsNotNone(self.c.ouvrir("nouveau-mot-de-passe", IP, apres(minutes=2)))
        self.assertFalse(self.c.changer_avec_code(code, "encore-un-autre-mdp", apres(minutes=3)))  # code usé

    def test_echecs_anciens_oublies_apres_10_minutes(self):
        for _ in range(2):
            self.c.ouvrir("faux-faux-faux", IP, T)
        self.assertIsNone(self.c.ouvrir("faux-faux-faux", IP, apres(minutes=10, seconds=1)))
        self.assertIsNotNone(self.c.ouvrir(MDP, IP, apres(minutes=10, seconds=2)))

    def test_nouveau_mdp_trop_court_ne_consomme_pas_d_essai(self):
        code = self.c.demander_code(T)
        with self.assertRaises(ValueError):
            self.c.changer_avec_code(code, "court", T)
        self.assertTrue(self.c.changer_avec_code(code, "nouveau-mot-de-passe", T))

    def test_code_expire_apres_10_minutes(self):
        code = self.c.demander_code(T)
        self.assertFalse(self.c.changer_avec_code(code, "nouveau-mot-de-passe", apres(minutes=10, seconds=1)))

    def test_cinq_essais_par_code(self):
        code = self.c.demander_code(T)
        faux = f"{(int(code) + 1) % 10**8:08d}"
        for _ in range(5):
            self.assertFalse(self.c.changer_avec_code(faux, "nouveau-mot-de-passe", T))
        self.assertFalse(self.c.changer_avec_code(code, "nouveau-mot-de-passe", T))

    def test_un_code_par_10_minutes_et_3_par_jour(self):
        self.c.demander_code(T)
        with self.assertRaises(TropDeCodes) as e:
            self.c.demander_code(apres(minutes=5))
        self.assertEqual(e.exception.attente_s, 300)
        self.c.demander_code(apres(minutes=10))
        self.c.demander_code(apres(minutes=20))
        with self.assertRaises(TropDeCodes):
            self.c.demander_code(apres(minutes=30))
        self.c.demander_code(apres(hours=2))  # le lendemain à Porto-Novo

    def test_une_adresse_n_epuise_pas_les_codes_des_autres(self):
        for minutes in (0, 10, 20):
            self.c.demander_code(apres(minutes=minutes), "203.0.113.66")
        with self.assertRaises(TropDeCodes):
            self.c.demander_code(apres(minutes=30), "203.0.113.66")
        self.assertRegex(self.c.demander_code(apres(minutes=30), IP), r"^[0-9]{8}$")

    def test_plafond_commun_de_dix_codes_par_jour(self):
        for i in range(10):
            self.c.demander_code(T, f"203.0.113.{i}")
        with self.assertRaises(TropDeCodes):
            self.c.demander_code(T, IP)
        self.c.demander_code(apres(hours=2), IP)  # le lendemain à Porto-Novo

    def test_un_nouveau_code_ne_remplace_pas_celui_en_cours(self):
        premier = self.c.demander_code(T, IP)
        self.c.demander_code(apres(minutes=1), "203.0.113.66")
        self.assertTrue(self.c.changer_avec_code(premier, "nouveau-mot-de-passe", apres(minutes=2)))

    def test_cinq_essais_en_tout_meme_avec_plusieurs_codes(self):
        premier = self.c.demander_code(T, IP)
        second = self.c.demander_code(T, "203.0.113.66")
        faux = next(f"{n:08d}" for n in range(10 ** 8) if f"{n:08d}" not in (premier, second))
        for _ in range(5):
            self.assertFalse(self.c.changer_avec_code(faux, "nouveau-mot-de-passe", T))
        for code in (premier, second):
            self.assertFalse(self.c.changer_avec_code(code, "nouveau-mot-de-passe", T))

    def test_ancien_format_du_code_encore_lu(self):
        code = self.c.demander_code(T, IP)
        donnees = json.loads(self.chemin.read_text(encoding="utf-8"))
        donnees["code"] = donnees.pop("codes")[0]  # tel que l'écrivait la première version
        self.chemin.write_text(json.dumps(donnees), encoding="utf-8")
        self.assertTrue(self.c.changer_avec_code(code, "nouveau-mot-de-passe", apres(minutes=1)))

    def test_code_jamais_en_clair(self):
        code = self.c.demander_code(T)
        self.assertNotIn(code, self.chemin.read_text(encoding="utf-8"))

    def test_sans_mdp_defini(self):
        vide = Connexion(self.dossier / "vide.json")
        self.assertFalse(vide.configure())
        self.assertIsNone(vide.ouvrir(MDP, IP, T))
        with self.assertRaises(PasConfigure):
            vide.demander_code(T)


if __name__ == "__main__":
    unittest.main()
