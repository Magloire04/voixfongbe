import hashlib
import json
import threading
import time
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tests.aides import MoteurFactice, appeler
from voixfongbe.app import creer_application
from voixfongbe.cles import Cles
from voixfongbe.config import Config
from voixfongbe.quotas import FUSEAU
from voixfongbe.reglages import Reglages

T = datetime(2026, 11, 9, 22, 30, tzinfo=FUSEAU)
SECURITE = {"Strict-Transport-Security": "max-age=31536000", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex, nofollow"}


class TestApp(unittest.TestCase):
    def setUp(self):
        self.racine = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.racine)
        self.config = Config(racine=self.racine, dossier_modele=self.racine / "modele",
                             dossier_stockage=self.racine / "stockage")
        self.cle = Cles(self.config.dossier_stockage / "cles.json").creer("demo")
        self.auth = {"Authorization": f"Bearer {self.cle}"}

    def app(self, moteur=None, par_cle=None, **reglages):
        """par_cle : limite quotidienne du projet « demo » (elle vit dans le fichier des clés)."""
        if par_cle is not None:
            Cles(self.config.dossier_stockage / "cles.json").changer_limite("demo", par_cle)
        config = Config(**{**self.config.__dict__, **reglages})
        return creer_application(config, moteur or MoteurFactice(), horloge=lambda: T)

    def synthese(self, app, corps, entetes=None):
        return appeler(app, "POST", "/v1/synthese", corps, self.auth if entetes is None else entetes)

    def code(self, reponse):
        statut, _, corps = reponse
        return statut, json.loads(corps)["code"]

    # 1. Routes et méthodes
    def test_route_inconnue_404(self):
        self.assertEqual(self.code(appeler(self.app(), "GET", "/ailleurs")), (404, "introuvable"))

    def test_mauvaise_methode_405_avec_allow(self):
        statut, entetes, _ = appeler(self.app(), "GET", "/v1/synthese")
        self.assertEqual((statut, entetes["Allow"]), (405, "POST"))

    # 2. HTTPS
    def test_http_redirige_vers_https(self):
        statut, entetes, _ = appeler(self.app(), "GET", "/v1/etat", entetes={"X-Forwarded-Proto": "http"})
        self.assertEqual((statut, entetes["Location"]), (301, "https://voix.bytechnum.com/v1/etat"))

    # 3. Clé
    def test_sans_cle_401_cle_absente(self):
        self.assertEqual(self.code(self.synthese(self.app(), {"texte": "mi"}, {})), (401, "cle_absente"))

    def test_cle_inconnue_401(self):
        r = self.synthese(self.app(), {"texte": "mi"}, {"Authorization": "Bearer pas-la-bonne"})
        self.assertEqual(self.code(r), (401, "cle_invalide"))

    def test_schema_bearer_sans_tenir_compte_de_la_casse(self):
        statut, _, _ = self.synthese(self.app(), {"texte": "mi"}, {"Authorization": f"bearer {self.cle}"})
        self.assertEqual(statut, 200)

    # 4. Taille
    def test_corps_trop_grand_413(self):
        r = self.synthese(self.app(), b"{" + b" " * 9000 + b"}")
        self.assertEqual(self.code(r), (413, "corps_trop_grand"))

    # 5. Contenu
    def test_json_illisible_400(self):
        self.assertEqual(self.code(self.synthese(self.app(), b"pas du json")), (400, "json_invalide"))

    def test_texte_absent_ou_pas_une_chaine_400(self):
        for corps in ({}, {"texte": 5}, {"texte": None}):
            self.assertEqual(self.code(self.synthese(self.app(), corps)), (400, "texte_absent"), corps)

    def test_texte_trop_long_400(self):
        r = self.synthese(self.app(), {"texte": "a" * 1001})
        self.assertEqual(self.code(r), (400, "texte_trop_long"))

    def test_mille_caracteres_acceptes(self):
        self.assertEqual(self.synthese(self.app(), {"texte": "a" * 1000})[0], 200)

    def test_format_inconnu_400(self):
        self.assertEqual(self.code(self.synthese(self.app(), {"texte": "mi", "format": "ogg"})), (400, "format_inconnu"))

    # 6. Quota
    def test_quota_429_avec_retry_after(self):
        app = self.app(par_cle=1)
        self.synthese(app, {"texte": "mi"})
        statut, entetes, corps = self.synthese(app, {"texte": "kú"})
        self.assertEqual((statut, json.loads(corps)["code"], entetes["Retry-After"]), (429, "quota_jour", "5400"))

    def test_limite_du_projet_appliquee(self):
        Cles(self.config.dossier_stockage / "cles.json").changer_limite("demo", 1)
        app = self.app()
        self.assertEqual(self.synthese(app, {"texte": "mi"})[0], 200)
        self.assertEqual(self.code(self.synthese(app, {"texte": "kú"})), (429, "quota_jour"))

    def test_plafond_commun_des_reglages(self):
        stockage = self.config.dossier_stockage
        Reglages(stockage / "reglages.json", "eliseeatonde@gmail.com", 300).modifier(plafond=1)
        autre = Cles(stockage / "cles.json").creer("autre")
        app = self.app()
        self.assertEqual(self.synthese(app, {"texte": "mi"})[0], 200)
        r = self.synthese(app, {"texte": "kú"}, {"Authorization": f"Bearer {autre}"})
        self.assertEqual(self.code(r), (429, "quota_jour"))

    def test_limite_baissee_sous_le_compte_du_jour(self):
        app = self.app()
        for texte in ("mi", "kú"):
            self.assertEqual(self.synthese(app, {"texte": texte})[0], 200)
        Cles(self.config.dossier_stockage / "cles.json").changer_limite("demo", 1)
        self.assertEqual(self.code(self.synthese(app, {"texte": "abɔ"})), (429, "quota_jour"))

    def test_cle_a_l_ancien_format_marche(self):  # point de vigilance 2
        chemin = self.config.dossier_stockage / "cles.json"
        chemin.write_text(json.dumps({"projets": {"projet-collegue": {
            "empreinte": hashlib.sha256(b"cle-ancienne").hexdigest(), "cree_le": "2026-11-09T12:00:00+00:00"}}}))
        r = self.synthese(self.app(), {"texte": "mi"}, {"Authorization": "Bearer cle-ancienne"})
        self.assertEqual(r[0], 200)

    # 7. Modèle
    def test_modele_absent_503(self):
        r = self.synthese(self.app(MoteurFactice(pret=False)), {"texte": "mi"})
        self.assertEqual(self.code(r), (503, "modele_indisponible"))

    # 8. Texte vide
    def test_texte_vide_apres_preparation_400(self):
        self.assertEqual(self.code(self.synthese(self.app(), {"texte": "300 ? 🙂"})), (400, "texte_vide"))

    # 9. Cache et délai
    def test_meme_texte_deux_fois_vient_du_cache(self):
        moteur = MoteurFactice()
        app = self.app(moteur)
        _, e1, c1 = self.synthese(app, {"texte": "Mi kú abɔ."})
        _, e2, c2 = self.synthese(app, {"texte": "MI KÚ ABƆ !"})
        self.assertEqual((e1["X-Voix-Cache"], e2["X-Voix-Cache"]), ("non", "oui"))
        self.assertEqual(c1, c2)
        self.assertEqual(moteur.appels, 1)

    def test_synthese_trop_longue_rend_503(self):
        app = self.app(MoteurFactice(delai_s=0.5), delai_s=0.1)
        self.assertEqual(self.code(self.synthese(app, {"texte": "Mi kú."})), (503, "delai_depasse"))

    # 10. Réponse
    def test_reponse_mp3_avec_entetes(self):
        statut, e, corps = self.synthese(self.app(), {"texte": "Mi kú abɔ."})
        self.assertEqual((statut, e["Content-Type"], e["Content-Length"]), (200, "audio/mpeg", str(len(corps))))
        self.assertEqual((e["X-Voix-Licence"], e["X-Voix-Cache"], e["X-Voix-Caracteres-Ignores"]),
                         ("MMS-TTS de Meta, CC BY-NC 4.0", "non", "0"))

    def test_format_wav(self):
        statut, e, corps = self.synthese(self.app(), {"texte": "Mi kú.", "format": "wav"})
        self.assertEqual((statut, e["Content-Type"], corps[:4]), (200, "audio/wav", b"RIFF"))

    def test_chiffres_signales_dans_l_entete(self):
        _, e, _ = self.synthese(self.app(), {"texte": "È nɔ sa 300 F"})
        self.assertEqual(e["X-Voix-Caracteres-Ignores"], "3")

    # 11. Erreur imprévue et journal
    def test_erreur_imprevue_500_sans_detail(self):
        r = self.synthese(self.app(MoteurFactice(erreur=RuntimeError("détail secret"))), {"texte": "mi"})
        self.assertEqual(self.code(r), (500, "erreur_interne"))
        self.assertNotIn("secret", r[2].decode("utf-8"))

    def test_journal_note_chaque_demande_sans_texte(self):
        app = self.app()
        self.synthese(app, {"texte": "Mi kú abɔ."})
        self.synthese(app, {"texte": "a" * 1001})
        lignes = (self.config.dossier_stockage / "journal" / "journal-2026-11-09.jsonl").read_text(encoding="utf-8")
        self.assertEqual([json.loads(l)["code"] for l in lignes.splitlines()], [200, 400])
        self.assertNotIn("abɔ", lignes)

    # En-têtes, état, robots, CORS
    def test_entetes_de_securite_partout(self):
        app = self.app()
        for statut, entetes, _ in (appeler(app, "GET", "/v1/etat"), appeler(app, "GET", "/ailleurs"),
                                   self.synthese(app, {"texte": "mi"})):
            for nom, valeur in SECURITE.items():
                self.assertEqual(entetes.get(nom), valeur, (statut, nom))

    def test_erreurs_non_mises_en_cache(self):
        _, e, _ = appeler(self.app(), "GET", "/ailleurs")
        self.assertEqual(e["Cache-Control"], "no-store")

    def test_etat_pret(self):
        statut, _, corps = appeler(self.app(), "GET", "/v1/etat")
        self.assertEqual(statut, 200)
        self.assertEqual(json.loads(corps), {"service": "voix fon", "version": "factice00001",
                                             "modele": "facebook/mms-tts-fon", "licence": "CC BY-NC 4.0",
                                             "pret": True, "ouvert": True})

    def couper(self, coupee=True):
        Reglages(self.config.dossier_stockage / "reglages.json", "eliseeatonde@gmail.com", 300).modifier(
            api_coupee=coupee)

    def test_api_coupee_503_sans_compter_le_quota(self):
        app = self.app(par_cle=1)
        self.couper()
        statut, entetes, corps = self.synthese(app, {"texte": "mi"})
        self.assertEqual((statut, json.loads(corps)["code"]), (503, "api_coupee"))
        self.assertNotIn("Retry-After", entetes)
        etat = json.loads(appeler(app, "GET", "/v1/etat")[2])
        self.assertEqual((etat["pret"], etat["ouvert"]), (False, False))
        self.couper(False)
        self.assertEqual(self.synthese(app, {"texte": "mi"})[0], 200)  # la demande refusée n'a rien coûté

    def test_api_coupee_meme_sans_cle(self):
        self.couper()
        self.assertEqual(self.code(self.synthese(self.app(), {"texte": "mi"}, {})), (503, "api_coupee"))

    def test_etat_quand_modele_absent(self):
        corps = json.loads(appeler(self.app(MoteurFactice(pret=False)), "GET", "/v1/etat")[2])
        self.assertEqual((corps["pret"], corps["version"]), (False, None))

    def test_robots_txt(self):
        statut, _, corps = appeler(self.app(), "GET", "/robots.txt")
        self.assertEqual((statut, corps), (200, b"User-agent: *\nDisallow: /\n"))

    # Relecture finale
    def test_lettre_accentuee_inconnue_ne_plante_pas(self):
        self.assertEqual(self.synthese(self.app(), {"texte": "Mi ń yì."})[0], 200)

    def test_texte_sans_lettre_400(self):
        self.assertEqual(self.code(self.synthese(self.app(), {"texte": "300 - 400"})), (400, "texte_vide"))

    def test_quota_non_consomme_si_modele_absent(self):
        app = self.app(MoteurFactice(pret=False), par_cle=1)
        for _ in range(2):
            self.assertEqual(self.code(self.synthese(app, {"texte": "mi"})), (503, "modele_indisponible"))

    def test_quota_non_consomme_si_texte_vide(self):
        app = self.app(par_cle=1)
        self.synthese(app, {"texte": "300"})
        self.assertEqual(self.synthese(app, {"texte": "mi"})[0], 200)

    def test_erreur_imprevue_rend_le_quota(self):
        app = self.app(MoteurFactice(erreur=RuntimeError("panne")), par_cle=1)
        for _ in range(2):
            self.assertEqual(self.code(self.synthese(app, {"texte": "mi"})), (500, "erreur_interne"))

    def test_delai_depasse_compte_dans_le_quota(self):
        """Le calcul a eu lieu : sinon une clé pourrait occuper le processeur sans fin, sans rien payer."""
        app = self.app(MoteurFactice(delai_s=0.3), delai_s=0.05, par_cle=1)
        self.assertEqual(self.code(self.synthese(app, {"texte": "Mi kú."})), (503, "delai_depasse"))
        time.sleep(0.5)
        self.assertEqual(self.code(self.synthese(app, {"texte": "abɔ"})), (429, "quota_jour"))

    def test_resultat_tardif_mis_en_cache(self):
        moteur = MoteurFactice(delai_s=0.3)
        app = self.app(moteur, delai_s=0.05, par_cle=2)
        self.assertEqual(self.code(self.synthese(app, {"texte": "Mi kú."})), (503, "delai_depasse"))
        time.sleep(0.6)
        statut, entetes, _ = self.synthese(app, {"texte": "Mi kú."})
        self.assertEqual((statut, entetes["X-Voix-Cache"], moteur.appels), (200, "oui", 1))

    def test_voix_occupee_rend_503_tout_de_suite(self):
        app = self.app(MoteurFactice(delai_s=0.5), par_cle=2)
        premiere = threading.Thread(target=self.synthese, args=(app, {"texte": "Mi kú."}))
        premiere.start()
        time.sleep(0.1)
        debut = time.monotonic()
        statut, entetes, corps = self.synthese(app, {"texte": "abɔ"})
        self.assertLess(time.monotonic() - debut, 0.3)
        self.assertEqual((statut, json.loads(corps)["code"], entetes["Retry-After"]), (503, "voix_occupee", "5"))
        premiere.join()
        self.assertEqual(self.synthese(app, {"texte": "abɔ"})[0], 200)  # quota rendu

    def test_redirection_seulement_pour_les_routes_connues(self):
        statut, entetes, _ = appeler(self.app(), "GET", "/x\r\nSet-Cookie: a=b",
                                     entetes={"X-Forwarded-Proto": "http"})
        self.assertEqual(statut, 404)
        self.assertNotIn("Location", entetes)

    def test_redirection_sans_hote_douteux(self):
        statut, entetes, _ = appeler(self.app(), "GET", "/v1/etat",
                                     entetes={"X-Forwarded-Proto": "http", "Host": "a.example\r\nX-Y: z"})
        self.assertEqual((statut, entetes["Location"]), (301, "https://voix.bytechnum.com/v1/etat"))

    def test_corps_avec_bom_accepte(self):
        corps = b"\xef\xbb\xbf" + json.dumps({"texte": "Mi kú."}).encode("utf-8")
        self.assertEqual(self.synthese(self.app(), corps)[0], 200)

    # Mémoire bornée : un long texte est dit par morceaux
    def test_long_texte_dit_par_morceaux_de_120_caracteres(self):
        moteur = MoteurFactice()
        texte = " ".join(["Mi zìn fí élɔ bo kàn nǔ ɖevo byɔ."] * 20)  # environ 680 caractères
        self.assertEqual(self.synthese(self.app(moteur), {"texte": texte})[0], 200)
        self.assertGreater(moteur.appels, 1)
        self.assertTrue(all(n <= 2 * 120 + 1 for n in moteur.longueurs), moteur.longueurs)

    def test_aucun_morceau_trop_long_meme_sans_espace_ni_avec_accents_decomposes(self):
        for texte in ("a" * 1000, "ń" * 500):
            moteur = MoteurFactice()
            self.assertEqual(self.synthese(self.app(moteur), {"texte": texte})[0], 200)
            self.assertTrue(all(n <= 2 * 120 + 1 for n in moteur.longueurs), (texte[:3], moteur.longueurs))

    def test_morceaux_recolles_avec_une_pause(self):
        moteur = MoteurFactice()
        app = self.app(moteur, max_morceau=20)
        statut, _, wav = self.synthese(app, {"texte": "Mi kú abɔ ɖo gle. Un na xlɛ́ mi lee.", "format": "wav"})
        self.assertEqual(statut, 200)
        self.assertEqual(moteur.appels, 2)
        attendu = sum(160 * n for n in moteur.longueurs) + int(0.15 * 16000)
        self.assertEqual((len(wav) - 44) // 2, attendu)

    def test_aucune_reponse_cors(self):
        app = self.app()
        origine = {"Origin": "https://ailleurs.example", **self.auth}
        for statut, entetes, _ in (appeler(app, "OPTIONS", "/v1/synthese", entetes=origine),
                                   self.synthese(app, {"texte": "mi"}, origine)):
            self.assertNotIn("Access-Control-Allow-Origin", entetes, statut)


if __name__ == "__main__":
    unittest.main()
