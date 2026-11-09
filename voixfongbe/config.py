"""Réglages du service. Les limites viennent de la conception ; seuls les dossiers et le nombre de
fils d'exécution se changent par variables d'environnement."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    racine: Path
    dossier_modele: Path
    dossier_stockage: Path
    fils: int = 2
    max_caracteres: int = 1000
    max_morceau: int = 120  # dit d'un coup au plus : environ 400 Mo de mémoire sur le serveur
    total_jour: int = 300  # plafond commun tant qu'il n'a pas été changé dans l'espace admin
    delai_s: float = 30.0
    plafond_cache: int = 200 * 1024 * 1024
    max_corps: int = 8192
    hote: str = "voix.bytechnum.com"
    adresse_annonces: str = "eliseeatonde@gmail.com"  # par défaut ; se change dans l'espace admin
    guide: str = "https://github.com/Magloire04/voixfongbe#readme"

    @classmethod
    def depuis_env(cls, racine: Path) -> "Config":
        racine = Path(racine)
        return cls(
            racine=racine,
            dossier_modele=Path(os.environ.get("VOIX_MODELE_DIR", racine / "modele")),
            dossier_stockage=Path(os.environ.get("VOIX_STOCKAGE_DIR", racine / "stockage")),
            fils=int(os.environ.get("VOIX_FILS", "2")),
            hote=os.environ.get("VOIX_HOTE", "voix.bytechnum.com"),
        )
