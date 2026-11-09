import contextlib
import io
import os
import shutil
import smtplib
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from voixfongbe.courriel import Courriel, ecrire_reglages

REGLAGES = {"hote": "mail.spacemail.com", "port": 465, "utilisateur": "envoi@bytechnum.com",
            "mot_de_passe": "mdp-tres-secret-42", "expediteur": "envoi@bytechnum.com"}


class TestCourriel(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dossier)
        self.chemin = self.dossier / "smtp.json"
        self.recus = []

    def transport(self, message, reglages):
        self.recus.append((message, reglages))

    def configure(self):
        ecrire_reglages(self.chemin, **REGLAGES)
        return Courriel(self.chemin, transport=self.transport)

    def test_non_configure_n_envoie_rien(self):
        c = Courriel(self.chemin, transport=self.transport)
        self.assertFalse(c.configure())
        self.assertFalse(c.envoyer("koffi@exemple.bj", "Sujet", "Texte"))
        self.assertEqual(self.recus, [])

    def test_message_construit(self):
        c = self.configure()
        self.assertTrue(c.configure())
        self.assertTrue(c.envoyer("koffi@exemple.bj", "Votre accès", "Mi kú abɔ."))
        message, reglages = self.recus[0]
        self.assertEqual(message["From"], "Voix fon <envoi@bytechnum.com>")
        self.assertEqual(message["To"], "koffi@exemple.bj")
        self.assertEqual(message["Subject"], "Votre accès")
        self.assertIn("@bytechnum.com>", message["Message-ID"])
        self.assertIsNotNone(message["Date"])
        self.assertEqual(message.get_content_type(), "text/plain")
        self.assertEqual(message.get_content().strip(), "Mi kú abɔ.")
        self.assertEqual(reglages["hote"], "mail.spacemail.com")

    def test_echec_rend_false_sans_secret(self):
        def panne(message, reglages):
            raise smtplib.SMTPAuthenticationError(535, b"refus pour mdp-tres-secret-42")

        ecrire_reglages(self.chemin, **REGLAGES)
        erreurs = io.StringIO()
        with contextlib.redirect_stderr(erreurs):
            self.assertFalse(Courriel(self.chemin, transport=panne).envoyer("koffi@exemple.bj", "S", "T"))
            self.assertFalse(Courriel(self.chemin, transport=lambda m, r: (_ for _ in ()).throw(OSError("x")))
                             .envoyer("koffi@exemple.bj", "S", "T"))
        self.assertIn("SMTPAuthenticationError", erreurs.getvalue())
        self.assertNotIn("mdp-tres-secret-42", erreurs.getvalue())

    def test_transport_par_defaut_en_tls_465(self):
        ecrire_reglages(self.chemin, **REGLAGES)
        with mock.patch("smtplib.SMTP_SSL") as smtp_ssl:
            self.assertTrue(Courriel(self.chemin).envoyer("koffi@exemple.bj", "S", "T"))
        args, kwargs = smtp_ssl.call_args
        self.assertEqual(args, ("mail.spacemail.com", 465))
        self.assertEqual(kwargs["timeout"], 20)
        contexte = kwargs["context"]
        self.assertTrue(contexte.check_hostname)
        self.assertEqual(contexte.verify_mode, ssl.CERT_REQUIRED)
        session = smtp_ssl.return_value.__enter__.return_value
        session.login.assert_called_once_with("envoi@bytechnum.com", "mdp-tres-secret-42")
        session.send_message.assert_called_once()

    def test_entete_avec_retour_a_la_ligne_refuse(self):  # point de vigilance 5
        c = self.configure()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(c.envoyer("a@b.bj\r\nBcc: x@y.bj", "S", "T"))
            self.assertFalse(c.envoyer("koffi@exemple.bj", "Sujet\r\nBcc: x@y.bj", "T"))
        self.assertEqual(self.recus, [])

    @unittest.skipIf(os.name == "nt", "droits Unix")
    def test_reglages_smtp_en_droits_600(self):
        ecrire_reglages(self.chemin, **REGLAGES)
        self.assertEqual(self.chemin.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
