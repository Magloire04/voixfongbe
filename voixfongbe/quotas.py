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

    def consommer(self, projet: str, maintenant: datetime) -> int | None:
        """None si la demande passe (et elle est comptée) ; sinon les secondes jusqu'à minuit."""
        local = maintenant.astimezone(FUSEAU)
        jour = local.date().isoformat()
        with verrou(self.chemin):
            donnees = lire_json(self.chemin, {})
            if donnees.get("jour") != jour:
                donnees = {"jour": jour, "total": 0, "projets": {}}
            deja = donnees["projets"].get(projet, 0)
            if deja >= self.par_cle or donnees["total"] >= self.total:
                minuit = datetime.combine(local.date() + timedelta(days=1), time(0), FUSEAU)
                return max(1, math.ceil((minuit - local).total_seconds()))
            donnees["projets"][projet] = deja + 1
            donnees["total"] += 1
            ecrire_json(self.chemin, donnees)
        return None

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
