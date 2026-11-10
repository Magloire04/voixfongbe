"""Réglages modifiables depuis l'espace admin : l'adresse qui reçoit les annonces et les codes, le
plafond commun de demandes par jour, tous projets confondus, et l'interrupteur qui coupe l'API."""

from pathlib import Path

from .formats import valider_courriel, valider_limite
from .stockage import ecrire_json, lire_json, verrou


class Reglages:
    def __init__(self, chemin: Path, adresse_defaut: str, plafond_defaut: int):
        self.chemin = Path(chemin)
        self.defauts = {"adresse": adresse_defaut, "plafond": plafond_defaut, "api_coupee": False}

    def lire(self) -> dict:
        return {**self.defauts, **lire_json(self.chemin, {})}

    def modifier(self, *, adresse: str | None = None, plafond: int | None = None,
                 api_coupee: bool | None = None) -> None:
        valeurs = {}
        if api_coupee is not None:
            if not isinstance(api_coupee, bool):
                raise ValueError("api_coupee doit valoir true ou false")
            valeurs["api_coupee"] = api_coupee
        if adresse is not None:
            valeurs["adresse"] = valider_courriel(adresse)
        if plafond is not None:
            valeurs["plafond"] = valider_limite(plafond)
        with verrou(self.chemin):
            ecrire_json(self.chemin, {**lire_json(self.chemin, {}), **valeurs})
