"""Essai réel de la voix, sans passer par l'API : utilisé par scripts/deployer.sh.

    python scripts/essayer_voix.py      -> code 0 et durée du son si la voix parle, 1 sinon
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from voixfongbe.config import Config  # noqa: E402
from voixfongbe.moteur import ModeleIndisponible, Moteur  # noqa: E402
from voixfongbe.texte import identifiants, preparer  # noqa: E402


def main() -> int:
    config = Config.depuis_env(RACINE)
    moteur = Moteur(config.dossier_modele, config.fils)
    if not moteur.pret():
        print("Voix indisponible : modèle absent ou empreinte fausse.")
        return 1
    try:
        son = moteur.synthetiser(identifiants(preparer("Mi kú abɔ.", moteur.vocabulaire), moteur.vocabulaire))
    except ModeleIndisponible as e:
        print(f"Voix indisponible : {e}")
        return 1
    print(f"Voix essayée : {len(son) / 16000:.1f} s de son.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
