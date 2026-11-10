import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from tests.aides import ORIGINE, CourrielFactice, MoteurFactice, appeler
from voixfongbe.app import creer_application
from voixfongbe.cles import Cles
from voixfongbe.config import Config
from voixfongbe.demandes import Demandes, valider
from voixfongbe.quotas import FUSEAU

T = datetime(2026, 11, 9, 22, 30, tzinfo=FUSEAU)
DEMANDE = {"nom": "Koffi A.", "courriel": "koffi@exemple.bj", "organisation": "UAC",
           "description": "Application d'alphabétisation en fon pour des adultes.", "accord": True, "site_web": ""}


class TestPubliques(unittest.TestCase):
    def setUp(self):
        self.racine = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.racine)
        self.config = Config(racine=self.racine, dossier_modele=self.racine / "modele",
                             dossier_stockage=self.racine / "stockage")
        self.maintenant = T
        self.courriel = CourrielFactice()
        self.app = creer_application(self.config, MoteurFactice(), horloge=lambda: self.maintenant,
                                     courriel=self.courriel)
        self.cles = Cles(self.config.dossier_stockage / "cles.json")
        self.demandes = Demandes(self.config.dossier_stockage / "demandes.json")

    def code(self, reponse):
        statut, _, corps = reponse
        return statut, json.loads(corps)["code"]

    def deposer(self, entetes=ORIGINE, **autres):
        return appeler(self.app, "POST", "/api/demande", {**DEMANDE, **autres}, entetes)

    # Page et demande
    def test_page_demande_protegee(self):
        statut, entetes, corps = appeler(self.app, "GET", "/demande")
        self.assertEqual(statut, 200)
        self.assertEqual(entetes["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("frame-ancestors 'none'", entetes["Content-Security-Policy"])
        self.assertIn("script-src 'self'", entetes["Content-Security-Policy"])
        self.assertEqual(entetes["X-Frame-Options"], "DENY")
        self.assertEqual(entetes["X-Robots-Tag"], "noindex, nofollow")
        self.assertIn(b"<html", corps)

    def test_demande_enregistree_et_annoncee(self):
        statut, _, corps = self.deposer()
        self.assertEqual((statut, json.loads(corps)), (200, {"ok": True}))
        self.assertEqual(len(self.demandes.en_attente()), 1)
        self.assertEqual([e["a"] for e in self.courriel.envoyes], ["eliseeatonde@gmail.com"])
        self.assertIn("Koffi A.", self.courriel.envoyes[0]["texte"])

    def test_demande_sans_origine_ou_d_ailleurs_403(self):
        self.assertEqual(self.code(self.deposer(entetes={})), (403, "origine"))
        self.assertEqual(self.code(self.deposer(entetes={"Origin": "https://ailleurs.example"})), (403, "origine"))
        self.assertEqual(self.code(self.deposer(entetes={"Origin": "null"})), (403, "origine"))
        self.assertEqual(self.demandes.en_attente(), [])

    def test_referer_de_la_page_accepte(self):
        self.assertEqual(self.deposer(entetes={"Referer": "https://voix.bytechnum.com/demande"})[0], 200)

    def test_champ_piege_ignore_en_silence(self):
        statut, _, corps = self.deposer(site_web="https://spam.example")
        self.assertEqual((statut, json.loads(corps)), (200, {"ok": True}))
        self.assertEqual((self.demandes.en_attente(), self.courriel.envoyes), ([], []))

    def test_champ_invalide_donne_le_champ(self):
        statut, _, corps = self.deposer(description="trop court")
        reponse = json.loads(corps)
        self.assertEqual((statut, reponse["code"], reponse["champ"]), (400, "champ_invalide", "description"))
        self.assertTrue(reponse["erreur"])

    def test_quatrieme_demande_de_la_meme_ip_429(self):
        for _ in range(3):
            self.assertEqual(self.deposer({**ORIGINE, "X-Forwarded-For": "10.0.0.1, 203.0.113.7"})[0], 200)
        r = self.deposer({**ORIGINE, "X-Forwarded-For": "10.9.9.9, 203.0.113.7"})
        self.assertEqual(self.code(r), (429, "trop_de_demandes"))
        self.assertEqual(self.deposer({**ORIGINE, "X-Forwarded-For": "203.0.113.7, 198.51.100.4"})[0], 200)

    def test_en_tete_invente_ne_contourne_pas_la_limite(self):
        # Client vu en direct (pas de relais local) : un X-Forwarded-For différent à chaque essai ne change rien.
        for i in range(3):
            r = self.deposer({**ORIGINE, "Remote-Addr": "41.138.89.7", "X-Forwarded-For": f"203.0.113.{i}"})
            self.assertEqual(r[0], 200)
        r = self.deposer({**ORIGINE, "Remote-Addr": "41.138.89.7", "X-Forwarded-For": "203.0.113.99"})
        self.assertEqual(self.code(r), (429, "trop_de_demandes"))

    def test_demandes_fermees(self):
        remplies = Demandes(self.config.dossier_stockage / "demandes.json", par_ip=1000)
        for _ in range(50):
            remplies.deposer(valider(DEMANDE), ip="10.0.0.1", maintenant=T, pris=set())
        self.assertEqual(json.loads(appeler(self.app, "GET", "/api/demande")[2]), {"ouvertes": False})
        self.assertEqual(self.code(self.deposer()), (503, "demandes_fermees"))

    def test_demandes_ouvertes(self):
        self.assertEqual(json.loads(appeler(self.app, "GET", "/api/demande")[2]), {"ouvertes": True})

    def test_annonce_en_panne_n_empeche_pas_la_demande(self):
        self.courriel.en_panne = True
        self.assertEqual(self.deposer()[0], 200)
        self.assertEqual(len(self.demandes.en_attente()), 1)

    def test_post_sans_json_415(self):
        r = self.deposer(entetes={**ORIGINE, "Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(self.code(r), (415, "type_contenu"))

    # Lien d'accès
    def test_lien_ouvert_par_un_antivirus_reste_utilisable(self):  # point de vigilance 1
        jeton = self.cles.preparer("alpha", courriel="koffi@exemple.bj", maintenant=T)
        for _ in range(2):
            self.assertEqual(appeler(self.app, "GET", f"/acces/{jeton}")[0], 200)
            self.assertEqual(json.loads(appeler(self.app, "GET", f"/api/acces/{jeton}")[2]), {"valide": True})
        statut, entetes, corps = appeler(self.app, "POST", f"/api/acces/{jeton}", {}, ORIGINE)
        self.assertEqual((statut, entetes["Cache-Control"]), (200, "no-store"))
        reponse = json.loads(corps)
        self.assertEqual(self.cles.verifier(reponse["cle"]), "alpha")
        self.assertEqual((reponse["projet"], reponse["limite"]), ("alpha", 100))
        self.assertEqual(reponse["guide"], "https://github.com/Magloire04/voixfongbe#readme")
        self.assertEqual(self.code(appeler(self.app, "POST", f"/api/acces/{jeton}", {}, ORIGINE)),
                         (410, "lien_invalide"))
        self.assertEqual(json.loads(appeler(self.app, "GET", f"/api/acces/{jeton}")[2]), {"valide": False})

    def test_page_acces_protegee(self):
        jeton = self.cles.preparer("alpha", courriel="koffi@exemple.bj", maintenant=T)
        _, entetes, _ = appeler(self.app, "GET", f"/acces/{jeton}")
        self.assertIn("frame-ancestors 'none'", entetes["Content-Security-Policy"])
        self.assertEqual(entetes["Cache-Control"], "no-store")

    def test_post_acces_sans_origine_403(self):
        jeton = self.cles.preparer("alpha", courriel="koffi@exemple.bj", maintenant=T)
        self.assertEqual(self.code(appeler(self.app, "POST", f"/api/acces/{jeton}", {})), (403, "origine"))
        self.assertEqual(self.cles.lien_valide(jeton, T), "alpha")

    def test_lien_expire_410(self):
        jeton = self.cles.preparer("alpha", courriel="koffi@exemple.bj", maintenant=T)
        self.maintenant = T + timedelta(days=8)
        r = appeler(self.app, "POST", f"/api/acces/{jeton}", {}, ORIGINE)
        self.assertEqual(self.code(r), (410, "lien_invalide"))
        self.assertIn("technum.services@bytechnum.com", json.loads(r[2])["erreur"])

    def test_jeton_mal_forme_404(self):
        self.assertEqual(appeler(self.app, "GET", "/acces/court")[0], 404)

    # Fichiers, méthodes, HTTPS
    def test_statique_et_traversee(self):
        statut, entetes, _ = appeler(self.app, "GET", "/static/style.css")
        self.assertEqual((statut, entetes["Content-Type"]), (200, "text/css; charset=utf-8"))
        for chemin in ("/static/../app.py", "/static/inconnu.js", "/static/app.py", "/static/demande.html"):
            self.assertEqual(appeler(self.app, "GET", chemin)[0], 404, chemin)

    def test_scripts_et_styles_revalides_polices_gardees(self):
        # Après une mise à jour, un ancien script en cache ne doit pas tourner avec la nouvelle page.
        for chemin in ("/static/style.css", "/static/admin.js"):
            self.assertEqual(appeler(self.app, "GET", chemin)[1]["Cache-Control"], "no-cache", chemin)
        self.assertIn("immutable", appeler(self.app, "GET", "/static/montserrat-latin-400.woff2")[1]["Cache-Control"])

    def test_redirection_https_des_nouvelles_routes(self):
        statut, entetes, _ = appeler(self.app, "GET", "/demande", entetes={"X-Forwarded-Proto": "http"})
        self.assertEqual((statut, entetes["Location"]), (301, "https://voix.bytechnum.com/demande"))

    def test_methode_405_avec_allow(self):
        statut, entetes, _ = appeler(self.app, "DELETE", "/api/demande")
        self.assertEqual((statut, entetes["Allow"]), (405, "GET, POST"))


if __name__ == "__main__":
    unittest.main()
