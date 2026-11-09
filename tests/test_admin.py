import json
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from tests.aides import ORIGINE, CourrielFactice, MoteurFactice, appeler
from voixfongbe.app import creer_application
from voixfongbe.cles import Cles
from voixfongbe.config import Config
from voixfongbe.connexion import Connexion
from voixfongbe.demandes import Demandes, valider
from voixfongbe.quotas import FUSEAU

T = datetime(2026, 11, 9, 22, 30, tzinfo=FUSEAU)
MDP = "un-mot-de-passe-solide"
DEMANDE = {"nom": "Koffi A.", "courriel": "koffi@exemple.bj", "organisation": "UAC",
           "description": "Application d'alphabétisation en fon pour des adultes.", "accord": True}
LIEN = re.compile(r"https://voix\.bytechnum\.com/acces/([A-Za-z0-9_-]{43})")


class TestAdmin(unittest.TestCase):
    def setUp(self):
        self.racine = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.racine)
        self.config = Config(racine=self.racine, dossier_modele=self.racine / "modele",
                             dossier_stockage=self.racine / "stockage")
        stockage = self.config.dossier_stockage
        self.maintenant = T
        self.courriel = CourrielFactice()
        self.app = creer_application(self.config, MoteurFactice(), horloge=lambda: self.maintenant,
                                     courriel=self.courriel)
        self.cles = Cles(stockage / "cles.json")
        self.demandes = Demandes(stockage / "demandes.json", par_ip=1000)
        Connexion(stockage / "admin.json").definir_mdp(MDP, T)
        self.cookie = self.connecter()

    # Aides
    def connecter(self, mdp=MDP, ip="198.51.100.1"):
        statut, entetes, _ = appeler(self.app, "POST", "/api/admin/connexion", {"mot_de_passe": mdp},
                                     {**ORIGINE, "X-Forwarded-For": ip})
        return entetes["Set-Cookie"].split(";")[0] if statut == 200 else None

    def post(self, chemin, corps=None, entetes=None):
        return appeler(self.app, "POST", chemin, corps or {}, {**ORIGINE, "Cookie": self.cookie, **(entetes or {})})

    def get(self, chemin, requete=""):
        return appeler(self.app, "GET", chemin, None, {"Cookie": self.cookie}, requete)

    def lire(self, reponse):
        statut, _, corps = reponse
        return statut, json.loads(corps)

    def code(self, reponse):
        statut, donnees = self.lire(reponse)
        return statut, donnees["code"]

    def deposer_demande(self, **autres):
        return self.demandes.deposer(valider({**DEMANDE, **autres}), ip="10.0.0.1", maintenant=T, pris=set())["id"]

    def projet(self, nom):
        return {p["projet"]: p for p in self.cles.lister(self.maintenant)}[nom]

    def jeton_du_dernier_courriel(self):
        return LIEN.search(self.courriel.envoyes[-1]["texte"]).group(1)

    # Page et connexion
    def test_page_admin_protegee(self):
        statut, entetes, _ = appeler(self.app, "GET", "/admin")
        self.assertEqual(statut, 200)
        self.assertIn("frame-ancestors 'none'", entetes["Content-Security-Policy"])

    def test_etat_sans_session(self):
        self.assertEqual(self.lire(appeler(self.app, "GET", "/api/admin/etat")),
                         (200, {"configure": True, "connecte": False}))
        self.assertEqual(self.lire(self.get("/api/admin/etat")), (200, {"configure": True, "connecte": True}))

    def test_sans_mot_de_passe_defini(self):
        (self.config.dossier_stockage / "admin.json").unlink()
        self.assertEqual(self.lire(appeler(self.app, "GET", "/api/admin/etat"))[1]["configure"], False)
        r = appeler(self.app, "POST", "/api/admin/connexion", {"mot_de_passe": MDP}, ORIGINE)
        self.assertEqual(self.code(r), (503, "pas_configure"))

    def test_cookie_de_session_strict(self):
        _, entetes, _ = appeler(self.app, "POST", "/api/admin/connexion", {"mot_de_passe": MDP}, ORIGINE)
        cookie = entetes["Set-Cookie"]
        self.assertTrue(cookie.startswith("__Host-voix-admin="))
        for attribut in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/"):
            self.assertIn(attribut, cookie)
        self.assertNotIn("Domain", cookie)

    def test_donnees_refusees_sans_session(self):
        for chemin in ("/api/admin/demandes", "/api/admin/projets", "/api/admin/appels", "/api/admin/reglages"):
            self.assertEqual(self.code(appeler(self.app, "GET", chemin)), (401, "non_connecte"), chemin)
            r = appeler(self.app, "GET", chemin, None, {"Cookie": "__Host-voix-admin=pas-le-bon"})
            self.assertEqual(self.code(r), (401, "non_connecte"), chemin)

    def test_post_admin_d_ailleurs_403_meme_connecte(self):
        r = appeler(self.app, "POST", "/api/admin/reglages", {"plafond": 5},
                    {"Origin": "https://ailleurs.example", "Cookie": self.cookie})
        self.assertEqual(self.code(r), (403, "origine"))
        self.assertEqual(self.lire(self.get("/api/admin/reglages"))[1]["plafond"], 300)

    def test_mdp_faux_puis_blocage(self):
        for _ in range(3):
            r = appeler(self.app, "POST", "/api/admin/connexion", {"mot_de_passe": "faux-faux-faux"},
                        {**ORIGINE, "X-Forwarded-For": "203.0.113.9"})
            self.assertEqual(self.code(r), (401, "mdp_faux"))
        statut, entetes, corps = appeler(self.app, "POST", "/api/admin/connexion", {"mot_de_passe": MDP},
                                         {**ORIGINE, "X-Forwarded-For": "203.0.113.9"})
        self.assertEqual((statut, json.loads(corps)["code"], entetes["Retry-After"]), (429, "bloque", "600"))

    def test_deconnexion(self):
        _, entetes, _ = self.post("/api/admin/deconnexion")
        self.assertIn("Max-Age=0", entetes["Set-Cookie"])
        self.assertEqual(self.code(self.get("/api/admin/demandes")), (401, "non_connecte"))

    def test_session_expiree_apres_10_minutes(self):
        self.maintenant = T + timedelta(minutes=9)
        self.assertEqual(self.get("/api/admin/demandes")[0], 200)
        self.maintenant = T + timedelta(minutes=19, seconds=1)
        self.assertEqual(self.code(self.get("/api/admin/demandes")), (401, "non_connecte"))

    def test_reponses_admin_no_store(self):
        self.assertEqual(self.get("/api/admin/projets")[1]["Cache-Control"], "no-store")

    # Demandes
    def test_liste_des_demandes(self):
        ident = self.deposer_demande()
        statut, donnees = self.lire(self.get("/api/admin/demandes"))
        self.assertEqual((statut, [d["id"] for d in donnees["en_attente"]], donnees["historique"]), (200, [ident], []))
        self.assertEqual(donnees["en_attente"][0]["projet_propose"], "uac")

    def test_approuver_cree_le_projet_et_envoie_le_lien(self):
        ident = self.deposer_demande()
        r = self.post(f"/api/admin/demandes/{ident}/approuver", {"projet": "alpha-uac", "limite": 200})
        self.assertEqual(self.lire(r), (200, {"ok": True, "courriel_envoye": True}))
        fiche = self.projet("alpha-uac")
        self.assertEqual((fiche["etat"], fiche["limite"], fiche["courriel"]), ("lien_en_attente", 200, "koffi@exemple.bj"))
        self.assertEqual(self.courriel.envoyes[-1]["a"], "koffi@exemple.bj")
        jeton = self.jeton_du_dernier_courriel()
        cle = json.loads(appeler(self.app, "POST", f"/api/acces/{jeton}", {}, ORIGINE)[2])["cle"]
        r = appeler(self.app, "POST", "/v1/synthese", {"texte": "mi"}, {"Authorization": f"Bearer {cle}"})
        self.assertEqual(r[0], 200)
        self.assertEqual(self.demandes.obtenir(ident)["etat"], "approuvee")

    def test_approuver_sans_nom_prend_le_nom_propose(self):
        ident = self.deposer_demande()
        self.assertEqual(self.post(f"/api/admin/demandes/{ident}/approuver")[0], 200)
        self.assertEqual(self.projet("uac")["limite"], 100)

    def test_double_approbation(self):  # point de vigilance 3
        ident = self.deposer_demande()
        r1 = self.post(f"/api/admin/demandes/{ident}/approuver", {"projet": "alpha-uac", "limite": 200})
        r2 = self.post(f"/api/admin/demandes/{ident}/approuver", {"projet": "alpha-uac", "limite": 200})
        self.assertEqual(r1[0], 200)
        self.assertEqual(self.code(r2), (409, "deja_decidee"))
        self.assertEqual(len([e for e in self.courriel.envoyes if e["a"] == "koffi@exemple.bj"]), 1)

    def test_smtp_en_panne_pendant_l_approbation(self):  # point de vigilance 4
        ident = self.deposer_demande()
        self.courriel.en_panne = True
        statut, _, corps = self.post(f"/api/admin/demandes/{ident}/approuver", {"projet": "alpha"})
        self.assertEqual((statut, json.loads(corps)), (200, {"ok": True, "courriel_envoye": False}))
        self.assertEqual(self.projet("alpha")["etat"], "lien_en_attente")
        self.courriel.en_panne = False
        self.assertEqual(self.post("/api/admin/projets/alpha/nouveau-lien")[0], 200)
        jeton = self.jeton_du_dernier_courriel()
        self.assertEqual(appeler(self.app, "POST", f"/api/acces/{jeton}", {}, ORIGINE)[0], 200)

    def test_approuver_nom_pris_ou_invalide(self):
        self.cles.creer("alpha")
        ident = self.deposer_demande()
        self.assertEqual(self.code(self.post(f"/api/admin/demandes/{ident}/approuver", {"projet": "alpha"})),
                         (409, "projet_pris"))
        self.assertEqual(self.code(self.post(f"/api/admin/demandes/{ident}/approuver", {"projet": "Alpha UAC"})),
                         (400, "valeur_invalide"))
        self.assertEqual(self.code(self.post(f"/api/admin/demandes/{ident}/approuver", {"projet": "alpha\n"})),
                         (400, "valeur_invalide"))
        self.assertEqual(self.code(self.post(f"/api/admin/demandes/{ident}/approuver", {"limite": 0})),
                         (400, "valeur_invalide"))
        self.assertEqual(self.demandes.obtenir(ident)["etat"], "en_attente")

    def test_approbation_concurrente_annule_le_projet_en_trop(self):
        """Un autre onglet (ou processus) approuve la même demande entre la création du projet et la décision."""
        ident = self.deposer_demande()
        original = Demandes.marquer_approuvee

        def deja_traitee(demandes, ident_, projet, maintenant):
            original(demandes, ident_, "premier", maintenant)  # l'autre onglet passe juste avant
            original(demandes, ident_, projet, maintenant)  # lève ValueError("demande déjà traitée")

        with mock.patch.object(Demandes, "marquer_approuvee", deja_traitee):
            r = self.post(f"/api/admin/demandes/{ident}/approuver", {"projet": "en-trop"})
        self.assertEqual(self.code(r), (409, "deja_decidee"))
        self.assertEqual(self.cles.lister(), [])
        self.assertEqual([e for e in self.courriel.envoyes if e["a"] == "koffi@exemple.bj"], [])

    def test_demande_inconnue_404(self):
        self.assertEqual(self.code(self.post(f"/api/admin/demandes/{'0' * 16}/refuser")), (404, "demande_inconnue"))

    def test_refuser_avec_motif(self):
        ident = self.deposer_demande()
        self.assertEqual(self.code(self.post(f"/api/admin/demandes/{ident}/refuser", {"motif": "x" * 501})),
                         (400, "valeur_invalide"))
        self.assertEqual(self.demandes.obtenir(ident)["etat"], "en_attente")
        r = self.post(f"/api/admin/demandes/{ident}/refuser", {"motif": "Projet commercial."})
        self.assertEqual(self.lire(r), (200, {"ok": True, "courriel_envoye": True}))
        self.assertEqual(self.courriel.envoyes[-1]["a"], "koffi@exemple.bj")
        self.assertIn("Projet commercial.", self.courriel.envoyes[-1]["texte"])
        self.assertEqual(self.demandes.obtenir(ident)["etat"], "refusee")

    # Projets
    def test_limite_jusqu_a_un_million(self):
        self.cles.creer("demo")
        self.assertEqual(self.post("/api/admin/projets/demo/limite", {"limite": 1_000_000})[0], 200)
        self.assertEqual(self.projet("demo")["limite"], 1_000_000)
        for mauvaise in (0, "abc", None):
            self.assertEqual(self.code(self.post("/api/admin/projets/demo/limite", {"limite": mauvaise})),
                             (400, "valeur_invalide"))

    def test_depassement_du_plafond_signale(self):
        self.cles.creer("demo")
        self.post("/api/admin/projets/demo/limite", {"limite": 500})
        statut, donnees = self.lire(self.get("/api/admin/projets"))
        self.assertEqual((donnees["plafond"], donnees["projets"][0]["depasse_plafond"]), (300, True))

    def test_compte_du_jour(self):
        cle = self.cles.creer("demo")
        appeler(self.app, "POST", "/v1/synthese", {"texte": "mi"}, {"Authorization": f"Bearer {cle}"})
        statut, donnees = self.lire(self.get("/api/admin/projets"))
        self.assertEqual((donnees["total_jour"], donnees["projets"][0]["aujourd_hui"]), (1, 1))
        self.assertEqual(donnees["projets"][0]["depasse_plafond"], False)

    def test_projet_ssh_recoit_une_adresse_puis_un_lien(self):
        ancienne = self.cles.creer("projet-collegue")
        self.assertEqual(self.code(self.post("/api/admin/projets/projet-collegue/nouvelle-cle")),
                         (400, "courriel_absent"))
        self.assertEqual(self.code(self.post("/api/admin/projets/projet-collegue/courriel",
                                             {"courriel": "pas-une-adresse"})), (400, "valeur_invalide"))
        self.assertEqual(self.post("/api/admin/projets/projet-collegue/courriel",
                                   {"courriel": "collegue@exemple.bj"})[0], 200)
        r = self.post("/api/admin/projets/projet-collegue/nouvelle-cle")
        self.assertEqual(self.lire(r), (200, {"ok": True, "courriel_envoye": True}))
        self.assertEqual(self.courriel.envoyes[-1]["a"], "collegue@exemple.bj")
        self.assertTrue(self.courriel.envoyes[-1]["texte"].startswith("Bonjour,"))
        self.assertIsNone(self.cles.verifier(ancienne))

    def test_nouveau_lien_refuse_pour_un_projet_actif(self):
        self.cles.creer("demo")
        self.cles.changer_courriel("demo", "demo@exemple.bj")
        self.assertEqual(self.code(self.post("/api/admin/projets/demo/nouveau-lien")), (409, "etat_incompatible"))

    def test_revoquer_puis_supprimer_efface_la_demande(self):
        ident = self.deposer_demande()
        self.post(f"/api/admin/demandes/{ident}/approuver", {"projet": "alpha"})
        self.assertEqual(self.code(self.post("/api/admin/projets/alpha/supprimer")), (409, "etat_incompatible"))
        self.assertEqual(self.post("/api/admin/projets/alpha/revoquer")[0], 200)
        self.assertEqual(self.projet("alpha")["etat"], "revoquee")
        self.assertEqual(self.post("/api/admin/projets/alpha/supprimer")[0], 200)
        self.assertIsNone(self.demandes.obtenir(ident))
        self.assertEqual(self.cles.lister(), [])

    def test_projet_inconnu_404(self):
        self.assertEqual(self.code(self.post("/api/admin/projets/inconnu/revoquer")), (404, "projet_inconnu"))

    # Appels
    def test_appels_filtres_et_pagines(self):
        cle = self.cles.creer("demo")
        appeler(self.app, "POST", "/v1/synthese", {"texte": "mi"}, {"Authorization": f"Bearer {cle}"})
        appeler(self.app, "POST", "/v1/synthese", {"texte": "mi"}, {"Authorization": "Bearer pas-la-bonne"})
        statut, donnees = self.lire(self.get("/api/admin/appels", "jour=2026-11-09&projet=demo&page=1"))
        self.assertEqual((statut, donnees["total"], donnees["lignes"][0]["projet"]), (200, 1, "demo"))
        self.assertEqual(donnees["resume"], {"demandes": 2, "erreurs": 1, "temps_moyen_ms": donnees["resume"]["temps_moyen_ms"]})
        self.assertEqual((donnees["jour"], donnees["jours"], donnees["projet"]), ("2026-11-09", ["2026-11-09"], "demo"))
        statut, tout = self.lire(self.get("/api/admin/appels"))
        self.assertEqual((tout["jour"], tout["total"], tout["projet"]), ("2026-11-09", 2, None))
        for requete in ("jour=2026-13-01", "jour=2026-08-09", "jour=2026-11-10", "page=0", "page=abc"):
            self.assertEqual(self.code(self.get("/api/admin/appels", requete)), (400, "valeur_invalide"), requete)

    # Réglages
    def test_reglages_lus_et_modifies(self):
        self.assertEqual(self.lire(self.get("/api/admin/reglages")),
                         (200, {"adresse": "eliseeatonde@gmail.com", "plafond": 300, "smtp": {"configure": True},
                                "voix": {"pret": True, "version": "factice00001"}}))
        self.assertEqual(self.post("/api/admin/reglages", {"plafond": 500, "adresse": "elisee@exemple.bj"})[0], 200)
        donnees = self.lire(self.get("/api/admin/reglages"))[1]
        self.assertEqual((donnees["adresse"], donnees["plafond"]), ("elisee@exemple.bj", 500))
        for corps in ({"plafond": 0}, {"adresse": "pas-une-adresse"}):
            self.assertEqual(self.code(self.post("/api/admin/reglages", corps)), (400, "valeur_invalide"))

    def test_essai_d_envoi(self):
        self.assertEqual(self.lire(self.post("/api/admin/reglages/essai")), (200, {"ok": True, "courriel_envoye": True}))
        self.assertEqual(self.courriel.envoyes[-1]["a"], "eliseeatonde@gmail.com")
        self.courriel.configure_ = False
        self.assertEqual(self.code(self.post("/api/admin/reglages/essai")), (503, "smtp_absent"))

    # Mot de passe oublié
    def test_mot_de_passe_oublie_de_bout_en_bout(self):
        r = appeler(self.app, "POST", "/api/admin/oubli", {}, ORIGINE)
        self.assertEqual(r[0], 200)
        self.assertEqual(self.courriel.envoyes[-1]["a"], "eliseeatonde@gmail.com")
        code = re.search(r"\b(\d{8})\b", self.courriel.envoyes[-1]["texte"]).group(1)
        r = appeler(self.app, "POST", "/api/admin/oubli/changer", {"code": "00000000" if code != "00000000" else "1",
                                                                  "mot_de_passe": "nouveau-mot-de-passe"}, ORIGINE)
        self.assertEqual(self.code(r), (400, "code_faux"))
        r = appeler(self.app, "POST", "/api/admin/oubli/changer", {"code": code, "mot_de_passe": "court"}, ORIGINE)
        self.assertEqual(self.code(r), (400, "mdp_court"))
        r = appeler(self.app, "POST", "/api/admin/oubli/changer", {"code": code, "mot_de_passe": "nouveau-mot-de-passe"},
                    ORIGINE)
        self.assertEqual(r[0], 200)
        self.assertIn("Mot de passe", self.courriel.envoyes[-1]["sujet"])
        self.assertEqual(self.code(self.get("/api/admin/demandes")), (401, "non_connecte"))
        self.assertIsNone(self.connecter(MDP))
        self.assertIsNotNone(self.connecter("nouveau-mot-de-passe"))

    def test_deuxieme_code_trop_tot_429(self):
        appeler(self.app, "POST", "/api/admin/oubli", {}, ORIGINE)
        statut, entetes, corps = appeler(self.app, "POST", "/api/admin/oubli", {}, ORIGINE)
        self.assertEqual((statut, json.loads(corps)["code"], entetes["Retry-After"]), (429, "trop_de_codes", "600"))

    def test_oubli_sans_envoi_configure(self):
        self.courriel.configure_ = False
        self.assertEqual(self.code(appeler(self.app, "POST", "/api/admin/oubli", {}, ORIGINE)), (503, "smtp_absent"))


if __name__ == "__main__":
    unittest.main()
