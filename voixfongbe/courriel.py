"""Envoi des e-mails du service : SMTP sur TLS (port 465), avec la boîte d'envoi @bytechnum.com.

Les identifiants sont saisis en SSH (scripts/admin.py smtp) dans smtp.json, en droits 600, et ne
sont jamais affichés. Un envoi qui échoue rend False : la décision qui l'a demandé reste valable.

L'envoi se fait pendant la requête, sans file d'attente : une boîte lente fait attendre la page (20 s
au plus par étape réseau) et occupe un processus pendant ce temps. Au volume prévu (quelques demandes
par jour), c'est plus sûr qu'un envoi en arrière-plan qu'un redémarrage de Passenger pourrait perdre.
"""

import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from .formats import valider_courriel
from .stockage import ecrire_json, lire_json

CLES_SMTP = ("hote", "port", "utilisateur", "mot_de_passe", "expediteur")
NOM_AFFICHE = "Voix fon"


def ecrire_reglages(chemin: Path, *, hote: str, port: int, utilisateur: str, mot_de_passe: str,
                    expediteur: str) -> None:
    ecrire_json(chemin, {"hote": hote, "port": int(port), "utilisateur": utilisateur,
                         "mot_de_passe": mot_de_passe, "expediteur": expediteur})


def _smtp_ssl(message: EmailMessage, reglages: dict) -> None:
    with smtplib.SMTP_SSL(reglages["hote"], int(reglages["port"]), context=ssl.create_default_context(),
                          timeout=20) as smtp:
        smtp.login(reglages["utilisateur"], reglages["mot_de_passe"])
        smtp.send_message(message)


class Courriel:
    def __init__(self, chemin: Path, transport=None):
        self.chemin = Path(chemin)
        self.transport = transport or _smtp_ssl

    def _reglages(self) -> dict | None:
        reglages = lire_json(self.chemin, {})
        return reglages if all(reglages.get(c) for c in CLES_SMTP) else None

    def configure(self) -> bool:
        return self._reglages() is not None

    def envoyer(self, destinataire: str, sujet: str, texte: str) -> bool:
        reglages = self._reglages()
        if reglages is None:
            return False
        try:
            message = EmailMessage()
            message["From"] = formataddr((NOM_AFFICHE, reglages["expediteur"]))
            message["To"] = valider_courriel(destinataire)
            message["Subject"] = sujet  # un retour à la ligne y lève ValueError
            message["Date"] = formatdate(localtime=True)
            message["Message-ID"] = make_msgid(domain="bytechnum.com")
            message.set_content(texte)
        except (ValueError, TypeError) as e:
            print(f"e-mail non construit : {type(e).__name__}", file=sys.stderr)
            return False
        try:
            self.transport(message, reglages)
        except Exception as e:  # noqa: BLE001 : quoi qu'il arrive, l'appelant doit pouvoir dire « non parti »
            # Seul le type de l'erreur : le message du serveur pourrait citer un identifiant.
            print(f"envoi d'e-mail impossible : {type(e).__name__}", file=sys.stderr)
            return False
        return True
