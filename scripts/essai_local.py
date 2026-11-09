"""Essai des pages sur le PC : http://localhost:8765/demande, /admin et les liens d'accès.

    .venv/Scripts/python scripts/essai_local.py              sert l'application, stockage dans tmp/essai-local/
    .venv/Scripts/python scripts/essai_local.py --exemples   remplit d'abord des données fictives

Les e-mails ne partent pas : ils s'affichent dans cette console (liens d'accès et codes compris).
Avec --exemples, un mot de passe d'essai, propre à ce PC, est tiré au hasard et affiché ici. Ce n'est
jamais celui du serveur.
"""

import argparse
import secrets
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from voixfongbe.app import creer_application  # noqa: E402
from voixfongbe.cles import Cles  # noqa: E402
from voixfongbe.config import Config  # noqa: E402
from voixfongbe.connexion import Connexion  # noqa: E402
from voixfongbe.demandes import Demandes, valider  # noqa: E402
from voixfongbe.journal import Journal  # noqa: E402
from voixfongbe.quotas import Quotas  # noqa: E402

PORT = 8765
HOTE = f"localhost:{PORT}"


class CourrielConsole:
    """Affiche les e-mails au lieu de les envoyer."""

    def configure(self) -> bool:
        return True

    def envoyer(self, destinataire: str, sujet: str, texte: str) -> bool:
        print(f"\n----- e-mail pour {destinataire} : {sujet}\n{texte}-----\n", flush=True)
        return True


class Silencieux(WSGIRequestHandler):
    def log_message(self, format, *args):  # une ligne par requête suffit
        sys.stderr.write(f"{self.command} {self.path} {args[1] if len(args) > 1 else ''}\n")


def remplir(stockage: Path) -> None:
    maintenant = datetime.now(timezone.utc)
    demandes = Demandes(stockage / "demandes.json", par_ip=1000)
    exemples = [
        {"nom": "Koffi Adjovi", "courriel": "koffi@exemple.bj", "organisation": "Université d'Abomey-Calavi",
         "description": "Application d'alphabétisation en fon pour des adultes.\nLes leçons sont lues à voix haute."},
        {"nom": "<img src=x onerror=alert(1)>", "courriel": "piege@exemple.bj", "organisation": "",
         "description": "Nom piégé : il doit s'afficher en texte, jamais comme une image."},
        {"nom": "Ɖokpɔ́ Sɛ́", "courriel": "dokpo@exemple.bj", "organisation": "",
         "description": "Lecture de contes en fon pour une bibliothèque de quartier."},
        {"nom": "Awa Hounkpè", "courriel": "awa@exemple.bj", "organisation": "Radio communautaire",
         "description": "Annonces de service public lues en fon."},
    ]
    # Une adresse fictive : 127.0.0.1, celle du navigateur d'essai, garde ses 3 demandes du jour.
    ids = [demandes.deposer(valider({**e, "accord": True}), ip="192.0.2.1", maintenant=maintenant, pris=set())["id"]
           for e in exemples]
    demandes.marquer_refusee(ids[3], "Projet commercial.", maintenant)

    cles = Cles(stockage / "cles.json")
    cles.creer("projet-collegue")
    cles.preparer("alpha-uac", courriel="alpha@exemple.bj", limite=200, nom="Alpha", organisation="UAC",
                  maintenant=maintenant)
    cles.preparer("lien-expire", courriel="lent@exemple.bj", nom="Lent", maintenant=maintenant - timedelta(days=8))
    cles.creer("ancien-projet")
    cles.revoquer("ancien-projet")
    cles.changer_limite("projet-collegue", 500)

    quotas = Quotas(stockage / "quotas.json")
    journal = Journal(stockage / "journal")
    for i in range(64):
        code = 200 if i % 9 else (429 if i % 2 else 401)
        projet = None if code == 401 else ("projet-collegue" if i % 3 else "alpha-uac")
        if code == 200:
            quotas.consommer(projet, maintenant, limite=1000, plafond=1000)
        journal.noter(projet=projet, caracteres=40 + i * 7, format="mp3" if i % 4 else "wav",
                      duree_ms=1700 + 13 * i if i % 5 else 9, cache=not i % 5, code=code,
                      maintenant=maintenant - timedelta(minutes=64 - i))

    mdp = secrets.token_urlsafe(12)
    Connexion(stockage / "admin.json").definir_mdp(mdp, maintenant)
    print(f"Mot de passe d'essai de l'espace admin (ce PC seulement) : {mdp}", flush=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--exemples", action="store_true", help="repart d'un stockage vide rempli de données fictives")
    args = p.parse_args()
    stockage = RACINE / "tmp" / "essai-local"
    if args.exemples:
        shutil.rmtree(stockage, ignore_errors=True)
        remplir(stockage)
    config = Config(racine=RACINE, dossier_modele=RACINE / "modele", dossier_stockage=stockage, hote=HOTE)
    application = creer_application(config, courriel=CourrielConsole())
    print(f"Pages : http://{HOTE}/demande et http://{HOTE}/admin (Ctrl+C pour arrêter)", flush=True)
    with make_server("127.0.0.1", PORT, application, handler_class=Silencieux) as serveur:
        try:
            serveur.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
