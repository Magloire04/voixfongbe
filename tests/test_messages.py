import unittest
from datetime import datetime

from voixfongbe import messages
from voixfongbe.quotas import FUSEAU

GUIDE = "https://github.com/Magloire04/voixfongbe#readme"
LIEN = "https://voix.bytechnum.com/acces/" + "a" * 43
MENTION = "Voix : MMS-TTS de Meta (CC BY-NC 4.0)"


class TestMessages(unittest.TestCase):
    def test_acces_accorde(self):
        sujet, texte = messages.acces_accorde("Koffi A.", LIEN, 100, GUIDE)
        self.assertTrue(sujet)
        for attendu in ("Koffi A.", LIEN, GUIDE, "100 demandes par jour", MENTION, "7 jours", "une seule fois"):
            self.assertIn(attendu, texte)

    def test_grande_limite_lisible(self):
        _, texte = messages.acces_accorde("Koffi A.", LIEN, 1_000_000, GUIDE)
        self.assertIn("1 000 000 demandes par jour", texte)

    def test_nouveau_lien(self):
        _, texte = messages.nouveau_lien("Koffi A.", LIEN, 200, GUIDE)
        for attendu in (LIEN, GUIDE, "200 demandes par jour", MENTION, "ne fonctionne plus"):
            self.assertIn(attendu, texte)

    def test_sans_nom_de_personne(self):
        for fonction in (messages.acces_accorde, messages.nouveau_lien):
            self.assertTrue(fonction("", LIEN, 100, GUIDE)[1].startswith("Bonjour,\n"))
        self.assertTrue(messages.refus(None, None)[1].startswith("Bonjour,\n"))

    def test_refus_avec_et_sans_motif(self):
        _, avec = messages.refus("Koffi A.", "Projet commercial.")
        _, sans = messages.refus("Koffi A.", None)
        self.assertIn("Projet commercial.", avec)
        self.assertNotIn("Motif", sans)
        self.assertIn("technum.services@bytechnum.com", sans)

    def test_annonce_sans_lien_d_acces(self):
        demande = {"nom": "Koffi A.", "courriel": "koffi@exemple.bj", "organisation": "UAC",
                   "description": "Alphabétisation en fon.", "projet_propose": "uac"}
        sujet, texte = messages.annonce_demande(demande, "https://voix.bytechnum.com/admin")
        self.assertIn("Koffi A.", sujet)
        for attendu in ("koffi@exemple.bj", "UAC", "Alphabétisation en fon.", "https://voix.bytechnum.com/admin"):
            self.assertIn(attendu, texte)
        self.assertNotIn("/acces/", texte)

    def test_code_oubli(self):
        _, texte = messages.code_oubli("04821937")
        self.assertIn("04821937", texte)
        self.assertIn("10 minutes", texte)

    def test_alerte_mdp(self):
        _, texte = messages.alerte_mdp(datetime(2026, 11, 9, 21, 30, tzinfo=FUSEAU))
        self.assertIn("9 novembre 2026 à 21 h 30", texte)

    def test_essai(self):
        sujet, texte = messages.essai()
        self.assertTrue(sujet and texte)


if __name__ == "__main__":
    unittest.main()
