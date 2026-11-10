"""Sujets et textes des e-mails du service, en français et en texte simple.

Jamais de clé dans un e-mail : la personne reçoit un lien qui l'affiche une seule fois.
"""

from datetime import datetime

from .quotas import FUSEAU

CONTACT = "technum.services@bytechnum.com"
MENTION = "« Voix : MMS-TTS de Meta (CC BY-NC 4.0) »"
SIGNATURE = "Voix fon\nTECHNUM, bytechnum.com"
MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre")


def _nombre(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _date(moment: datetime) -> str:
    local = moment.astimezone(FUSEAU)
    return f"{local.day} {MOIS[local.month - 1]} {local.year} à {local.hour} h {local.minute:02d}"


def _bonjour(nom: str | None) -> str:
    """Un projet créé en SSH n'a pas de nom de personne : « Bonjour, » plutôt que « Bonjour , »."""
    return f"Bonjour {nom},\n" if nom else "Bonjour,\n"


def _consignes(lien: str, limite: int, guide: str) -> str:
    return (f"Ouvrez ce lien pour afficher votre clé d'accès :\n{lien}\n\n"
            "Le lien est valable 7 jours. La clé ne s'affiche qu'une seule fois : copiez-la dès qu'elle "
            "apparaît. Rangez-la dans une variable d'environnement de votre serveur, jamais dans le code "
            "d'une page web ou d'une application mobile.\n\n"
            f"Votre limite : {_nombre(limite)} demandes par jour.\n"
            f"Guide de configuration : {guide}\n\n"
            "La voix est le modèle MMS-TTS de Meta, sous licence CC BY-NC 4.0 : usage non commercial "
            f"uniquement. Votre application doit afficher la mention {MENTION}.\n\n"
            f"Une question : {CONTACT}\n\n{SIGNATURE}\n")


def annonce_demande(demande: dict, lien_admin: str) -> tuple[str, str]:
    organisation = demande.get("organisation") or "(non précisée)"
    return (f"Nouvelle demande d'accès : {demande['nom']}",
            f"Nom : {demande['nom']}\nAdresse : {demande['courriel']}\nOrganisation : {organisation}\n"
            f"Projet proposé : {demande.get('projet_propose', '')}\n\nDescription :\n{demande['description']}\n\n"
            f"À examiner dans l'espace admin : {lien_admin}\n")


def acces_accorde(nom: str, lien: str, limite: int, guide: str) -> tuple[str, str]:
    return ("Votre accès à la voix fon",
            _bonjour(nom) + "\nVotre demande d'accès à la voix fon est acceptée.\n\n"
            + _consignes(lien, limite, guide))


def nouveau_lien(nom: str, lien: str, limite: int, guide: str) -> tuple[str, str]:
    return ("Votre nouveau lien d'accès à la voix fon",
            _bonjour(nom) + "\nVoici un nouveau lien d'accès à la voix fon. Si vous aviez déjà une clé, "
            "elle ne fonctionne plus : remplacez-la par la nouvelle.\n\n" + _consignes(lien, limite, guide))


def refus(nom: str, motif: str | None) -> tuple[str, str]:
    texte = _bonjour(nom) + "\nVotre demande d'accès à la voix fon n'a pas été retenue.\n"
    if motif:
        texte += f"\nMotif : {motif}\n"
    texte += f"\nPour en parler, écrivez à {CONTACT}.\n\n{SIGNATURE}\n"
    return "Votre demande d'accès à la voix fon", texte


def code_oubli(code: str) -> tuple[str, str]:
    return ("Code pour changer le mot de passe de l'espace admin",
            f"Votre code : {code}\n\nIl est valable 10 minutes. Si vous n'avez rien demandé, ignorez ce "
            "message : le mot de passe ne change pas sans ce code.\n")


def alerte_mdp(quand: datetime) -> tuple[str, str]:
    return ("Mot de passe de l'espace admin changé",
            f"Le mot de passe de l'espace admin de la voix fon a été changé le {_date(quand)} (heure de "
            "Porto-Novo). Toutes les sessions ouvertes ont été fermées.\n\nSi ce n'est pas vous, définissez "
            "tout de suite un nouveau mot de passe en SSH : scripts/admin.py mot-de-passe.\n")


def alerte_adresse(nouvelle: str, quand: datetime) -> tuple[str, str]:
    """Envoyée à l'ancienne adresse : c'est elle qui recevait les codes de mot de passe oublié."""
    return ("Adresse de l'espace admin changée",
            f"L'adresse qui reçoit les annonces et les codes de l'espace admin de la voix fon a été remplacée "
            f"par {nouvelle}, le {_date(quand)} (heure de Porto-Novo). Ce message est envoyé à l'ancienne "
            "adresse.\n\nSi ce n'est pas vous, définissez tout de suite un nouveau mot de passe en SSH "
            "(scripts/admin.py mot-de-passe), puis remettez votre adresse dans l'onglet Réglages.\n")


def alerte_echecs(nombre: int, quand: datetime) -> tuple[str, str]:
    return ("Essais de connexion à l'espace admin",
            f"{nombre} mots de passe faux ont été saisis sur l'espace admin de la voix fon dans l'heure "
            f"précédant le {_date(quand)} (heure de Porto-Novo), toutes adresses confondues.\n\nSi ce n'est pas "
            "vous, rien n'est à faire tant que votre mot de passe est long et unique. En cas de doute, "
            "changez-le en SSH : scripts/admin.py mot-de-passe.\n")


def essai() -> tuple[str, str]:
    return ("Essai d'envoi de la voix fon",
            "Ce message confirme que l'espace admin de la voix fon peut envoyer des e-mails.\n")
