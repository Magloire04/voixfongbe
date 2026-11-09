"""Espace d'administration de la voix fon : les réglages qui se font une fois, en SSH, sur le serveur.

    python scripts/admin.py mot-de-passe   définit ou change le mot de passe de l'espace admin
    python scripts/admin.py smtp           enregistre les identifiants de la boîte d'envoi
    python scripts/admin.py essai-smtp     envoie un e-mail d'essai à l'adresse des annonces

Les mots de passe se tapent sans s'afficher et ne passent jamais en argument : ils n'apparaissent ni
à l'écran, ni dans l'historique du terminal. Le serveur ne garde que l'empreinte du mot de passe
de l'espace admin ; celui de la boîte d'envoi est dans stockage/smtp.json, en droits 600.
"""

import argparse
import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from voixfongbe import messages  # noqa: E402
from voixfongbe.config import Config  # noqa: E402
from voixfongbe.connexion import Connexion  # noqa: E402
from voixfongbe.courriel import Courriel, ecrire_reglages  # noqa: E402
from voixfongbe.formats import valider_courriel  # noqa: E402
from voixfongbe.reglages import Reglages  # noqa: E402

HOTE_SMTP = "mail.spacemail.com"
PORT_SMTP = 465


def _stockage(config: Config) -> Path:
    stockage = config.dossier_stockage
    stockage.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(stockage, 0o700)
    return stockage


def mot_de_passe(config: Config, stockage: Path) -> int:
    mdp = getpass.getpass("Nouveau mot de passe de l'espace admin (12 caractères au moins) : ")
    if getpass.getpass("Le même, une seconde fois : ") != mdp:
        print("Erreur : les deux saisies diffèrent. Rien n'a changé.", file=sys.stderr)
        return 1
    maintenant = datetime.now(timezone.utc)
    try:
        Connexion(stockage / "admin.json").definir_mdp(mdp, maintenant)
    except ValueError as e:
        print(f"Erreur : {e}. Rien n'a changé.", file=sys.stderr)
        return 1
    print("Mot de passe enregistré. Toutes les sessions sont fermées.")
    courriel = Courriel(stockage / "smtp.json")
    if courriel.configure():
        adresse = Reglages(stockage / "reglages.json", config.adresse_annonces, config.total_jour).lire()["adresse"]
        if courriel.envoyer(adresse, *messages.alerte_mdp(maintenant)):
            print(f"E-mail d'alerte envoyé à {adresse}.")
    return 0


def smtp(config: Config, stockage: Path) -> int:
    hote = input(f"Serveur SMTP [{HOTE_SMTP}] : ").strip() or HOTE_SMTP
    port_texte = input(f"Port [{PORT_SMTP}] : ").strip() or str(PORT_SMTP)
    utilisateur = input("Adresse de la boîte d'envoi (identifiant) : ").strip()
    expediteur = input(f"Adresse d'expéditeur [{utilisateur}] : ").strip() or utilisateur
    mot_de_passe = getpass.getpass("Mot de passe de la boîte d'envoi : ")
    try:
        port = int(port_texte)
        valider_courriel(utilisateur)
        valider_courriel(expediteur)
    except ValueError:
        print("Erreur : port ou adresse invalide. Rien n'a été enregistré.", file=sys.stderr)
        return 1
    if not mot_de_passe:
        print("Erreur : mot de passe vide. Rien n'a été enregistré.", file=sys.stderr)
        return 1
    ecrire_reglages(stockage / "smtp.json", hote=hote, port=port, utilisateur=utilisateur,
                    mot_de_passe=mot_de_passe, expediteur=expediteur)
    print("Boîte d'envoi enregistrée (stockage/smtp.json, droits 600).")
    print("Essai : python scripts/admin.py essai-smtp")
    return 0


def essai_smtp(config: Config, stockage: Path) -> int:
    courriel = Courriel(stockage / "smtp.json")
    if not courriel.configure():
        print("La boîte d'envoi n'est pas configurée : python scripts/admin.py smtp", file=sys.stderr)
        return 1
    adresse = Reglages(stockage / "reglages.json", config.adresse_annonces, config.total_jour).lire()["adresse"]
    if not courriel.envoyer(adresse, *messages.essai()):
        print("Échec de l'envoi : vérifier les identifiants (le type d'erreur est affiché ci-dessus).",
              file=sys.stderr)
        return 1
    print(f"E-mail d'essai envoyé à {adresse}.")
    return 0


ACTIONS = {"mot-de-passe": mot_de_passe, "smtp": smtp, "essai-smtp": essai_smtp}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=sorted(ACTIONS))
    args = p.parse_args(argv)
    config = Config.depuis_env(RACINE)
    return ACTIONS[args.action](config, _stockage(config))


if __name__ == "__main__":
    sys.exit(main())
