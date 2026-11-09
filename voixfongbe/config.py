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
    par_cle: int = 100
    total_jour: int = 300
    delai_s: float = 30.0
    plafond_cache: int = 200 * 1024 * 1024
    max_corps: int = 8192

    @classmethod
    def depuis_env(cls, racine: Path) -> "Config":
        racine = Path(racine)
        return cls(
            racine=racine,
            dossier_modele=Path(os.environ.get("VOIX_MODELE_DIR", racine / "modele")),
            dossier_stockage=Path(os.environ.get("VOIX_STOCKAGE_DIR", racine / "stockage")),
            fils=int(os.environ.get("VOIX_FILS", "2")),
        )
