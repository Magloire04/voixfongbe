"""Quotas par jour de Porto-Novo (UTC+1) : par clé, et pour tout le service."""

import math
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from .stockage import ecrire_json, lire_json, verrou

FUSEAU = timezone(timedelta(hours=1))


class Quotas:
    def __init__(self, chemin: Path, par_cle: int = 100, total: int = 300):
        self.chemin = Path(chemin)
        self.par_cle = par_cle
        self.total = total

    def consommer(self, projet: str, maintenant: datetime, limite: int | None = None,
                  plafond: int | None = None) -> int | None:
        """None si la demande passe (et elle est comptée) ; sinon les secondes jusqu'à minuit.
        limite : celle du projet ; plafond : celui de tous les projets ; à défaut, ceux du constructeur."""
        limite = self.par_cle if limite is None else limite
        plafond = self.total if plafond is None else plafond
        local = maintenant.astimezone(FUSEAU)
        jour = local.date().isoformat()
        with verrou(self.chemin):
            donnees = lire_json(self.chemin, {})
            if donnees.get("jour") != jour:
                donnees = {"jour": jour, "total": 0, "projets": {}}
            deja = donnees["projets"].get(projet, 0)
            if deja >= limite or donnees["total"] >= plafond:
                minuit = datetime.combine(local.date() + timedelta(days=1), time(0), FUSEAU)
                return max(1, math.ceil((minuit - local).total_seconds()))
            donnees["projets"][projet] = deja + 1
            donnees["total"] += 1
            ecrire_json(self.chemin, donnees)
        return None

    def du_jour(self, maintenant: datetime) -> dict:
        """Décompte du jour de Porto-Novo : {"total", "projets": {projet: demandes}}."""
        donnees = lire_json(self.chemin, {})
        if donnees.get("jour") != maintenant.astimezone(FUSEAU).date().isoformat():
            return {"total": 0, "projets": {}}
        return {"total": donnees["total"], "projets": dict(donnees["projets"])}

    def rendre(self, projet: str, maintenant: datetime) -> None:
        """Annule une demande comptée qui n'a pas pu aboutir (voix indisponible, occupée, trop lente)."""
        jour = maintenant.astimezone(FUSEAU).date().isoformat()
        with verrou(self.chemin):
            donnees = lire_json(self.chemin, {})
            if donnees.get("jour") != jour or donnees["projets"].get(projet, 0) <= 0:
                return
            donnees["projets"][projet] -= 1
            donnees["total"] = max(0, donnees["total"] - 1)
            ecrire_json(self.chemin, donnees)
