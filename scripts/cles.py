"""Clés d'accès au service de voix, une par projet. À lancer sur le serveur, en SSH :

    python scripts/cles.py creer <projet>          crée une clé et l'affiche UNE seule fois
    python scripts/cles.py creer <projet> --brut   n'affiche que la clé (pour une variable de shell)
    python scripts/cles.py lister                  projets qui ont une clé
    python scripts/cles.py revoquer <projet>       la clé du projet ne marche plus

Le nom du projet : 2 à 40 caractères parmi a-z, 0-9 et le tiret. Le serveur ne garde que
l'empreinte de la clé : une clé perdue ne se retrouve pas, on la révoque et on en crée une autre.
"""

import argparse
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from voixfongbe.cles import Cles  # noqa: E402
from voixfongbe.config import Config  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sous = p.add_subparsers(dest="action", required=True)
    c = sous.add_parser("creer")
    c.add_argument("projet")
    c.add_argument("--brut", action="store_true")
    sous.add_parser("lister")
    r = sous.add_parser("revoquer")
    r.add_argument("projet")
    args = p.parse_args()

    stockage = Config.depuis_env(RACINE).dossier_stockage
    stockage.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(stockage, 0o700)
    cles = Cles(stockage / "cles.json")
    try:
        if args.action == "creer":
            cle = cles.creer(args.projet)
            if args.brut:
                print(cle)
            else:
                print(f"Clé du projet « {args.projet} » (elle ne sera plus jamais affichée) :\n\n  {cle}\n")
                print("Transmettez-la de façon privée, avec le lien du README. Elle se place dans une")
                print("variable d'environnement du serveur du projet, jamais dans le code d'une page web.")
        elif args.action == "lister":
            for x in cles.lister():
                print(f"{x['projet']:40s} créée le {x['cree_le']}")
        elif args.action == "revoquer":
            print("Clé révoquée." if cles.revoquer(args.projet) else "Aucune clé pour ce projet.")
    except ValueError as e:
        print(f"Erreur : {e}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
