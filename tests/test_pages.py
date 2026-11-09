"""Contrôles des pages : elles doivent marcher sous la CSP stricte, sans rien injecter ni charger d'ailleurs."""

import shutil
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from tests.aides import MoteurFactice, appeler
from voixfongbe.app import creer_application
from voixfongbe.config import Config

WEB = Path(__file__).resolve().parent.parent / "voixfongbe" / "web"
PAGES = ("demande.html", "acces.html", "admin.html")
MENTION = "Voix : MMS-TTS de Meta (CC BY-NC 4.0)"


class Releve(HTMLParser):
    def __init__(self):
        super().__init__()
        self.balises = []  # (balise, attributs)

    def handle_starttag(self, tag, attrs):
        self.balises.append((tag, dict(attrs)))


def relever(nom: str) -> list[tuple[str, dict]]:
    r = Releve()
    r.feed((WEB / nom).read_text(encoding="utf-8"))
    return r.balises


class TestPages(unittest.TestCase):
    def test_ni_script_ni_style_en_ligne(self):
        for nom in PAGES:
            for balise, attributs in relever(nom):
                if balise == "script":
                    self.assertTrue(attributs.get("src"), f"{nom} : script en ligne")
                self.assertNotEqual(balise, "style", nom)
                self.assertNotIn("style", attributs, f"{nom} : attribut style sur <{balise}>")
                self.assertFalse([a for a in attributs if a.startswith("on")], f"{nom} : gestionnaire en ligne")

    def test_scripts_sans_injection_html(self):  # point de vigilance 5
        scripts = sorted(WEB.glob("*.js"))
        self.assertEqual([s.name for s in scripts], ["acces.js", "admin.js", "demande.js"])
        for script in scripts:
            texte = script.read_text(encoding="utf-8")
            for interdit in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(",
                             "new Function"):
                self.assertNotIn(interdit, texte, f"{script.name} : {interdit}")

    def test_ressources_locales(self):
        for nom in PAGES:
            balises = relever(nom)
            for balise, attributs in balises:
                if "src" in attributs:
                    self.assertTrue(attributs["src"].startswith("/static/"), f"{nom} : {attributs['src']}")
                if balise == "link":
                    self.assertTrue(attributs["href"].startswith("/static/"), f"{nom} : {attributs['href']}")
            self.assertIn(("script", {"src": f"/static/{nom.replace('.html', '.js')}"}),
                          [(b, {"src": a["src"]}) for b, a in balises if b == "script"])

    def test_polices_servies(self):
        racine = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, racine)
        app = creer_application(Config(racine=racine, dossier_modele=racine / "modele",
                                       dossier_stockage=racine / "stockage"), MoteurFactice())
        for poids in ("400", "600", "700"):
            for jeu in ("latin", "latin-ext"):
                statut, entetes, corps = appeler(app, "GET", f"/static/montserrat-{jeu}-{poids}.woff2")
                self.assertEqual((statut, entetes["Content-Type"]), (200, "font/woff2"), (jeu, poids))
                self.assertTrue(corps.startswith(b"wOF2"))
        self.assertTrue((WEB / "OFL.txt").exists())

    def test_icone_d_onglet(self):
        racine = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, racine)
        app = creer_application(Config(racine=racine, dossier_modele=racine / "modele",
                                       dossier_stockage=racine / "stockage"), MoteurFactice())
        statut, entetes, corps = appeler(app, "GET", "/static/icone.svg")
        self.assertEqual((statut, entetes["Content-Type"]), (200, "image/svg+xml"))
        self.assertNotIn(b"<script", corps)
        for nom in PAGES:
            self.assertIn(("link", {"rel": "icon", "href": "/static/icone.svg", "type": "image/svg+xml"}),
                          relever(nom), nom)

    def test_contact_public(self):
        texte = (WEB / "demande.html").read_text(encoding="utf-8")
        self.assertIn("technum.services@bytechnum.com", texte)
        self.assertNotIn("eliseeatonde@gmail.com", texte)

    def test_mention_exacte(self):
        for nom in ("demande.html", "acces.html"):
            self.assertIn(MENTION, (WEB / nom).read_text(encoding="utf-8"), nom)

    def test_champ_piege_hors_d_atteinte(self):
        piege = [a for b, a in relever("demande.html") if a.get("name") == "site_web"]
        self.assertEqual(len(piege), 1)
        self.assertEqual((piege[0].get("tabindex"), piege[0].get("autocomplete")), ("-1", "off"))

    def test_pas_de_tiret_cadratin(self):
        for fichier in WEB.glob("*.*"):
            if fichier.suffix in (".html", ".js", ".css"):
                self.assertNotIn("—", fichier.read_text(encoding="utf-8"), fichier.name)


if __name__ == "__main__":
    unittest.main()
