"""Point d'entrée de Passenger (Setup Python App de cPanel)."""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
# Le chargeur de Passenger n'ajoute pas toujours le dossier de l'application aux chemins d'import.
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from voixfongbe.app import creer_application  # noqa: E402
from voixfongbe.config import Config  # noqa: E402

application = creer_application(Config.depuis_env(RACINE))
