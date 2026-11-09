"""Point d'entrée de Passenger (Setup Python App de cPanel)."""

from pathlib import Path

from voixfongbe.app import creer_application
from voixfongbe.config import Config

application = creer_application(Config.depuis_env(Path(__file__).resolve().parent))
