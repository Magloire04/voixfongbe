"""Réglages modifiables depuis l'espace admin : l'adresse qui reçoit les annonces et les codes, et le
plafond commun de demandes par jour, tous projets confondus."""

from pathlib import Path

from .formats import valider_courriel, valider_limite
from .stockage import ecrire_json, lire_json, verrou


class Reglages:
    def __init__(self, chemin: Path, adresse_defaut: str, plafond_defaut: int):
        self.chemin = Path(chemin)
        self.defauts = {"adresse": adresse_defaut, "plafond": plafond_defaut}

    def lire(self) -> dict:
        return {**self.defauts, **lire_json(self.chemin, {})}

    def modifier(self, *, adresse: str | None = None, plafond: int | None = None) -> None:
        valeurs = {}
        if adresse is not None:
            valeurs["adresse"] = valider_courriel(adresse)
        if plafond is not None:
            valeurs["plafond"] = valider_limite(plafond)
        with verrou(self.chemin):
            ecrire_json(self.chemin, {**lire_json(self.chemin, {}), **valeurs})
