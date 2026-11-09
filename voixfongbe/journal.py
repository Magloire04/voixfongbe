"""Journal des demandes : une ligne JSON par demande, un fichier par jour de Porto-Novo, effacé
après 90 jours. Jamais le texte demandé : il peut contenir des données personnelles."""

import json
import os
from datetime import date, datetime
from pathlib import Path

from .quotas import FUSEAU
from .stockage import verrou


class Journal:
    def __init__(self, dossier: Path, jours: int = 90):
        self.dossier = Path(dossier)
        self.jours = jours
        self._purge_faite_le = None

    def noter(self, *, projet: str | None, caracteres: int, format: str | None, duree_ms: int,
              cache: bool, code: int, maintenant: datetime) -> None:
        local = maintenant.astimezone(FUSEAU)
        ligne = json.dumps({"date": local.isoformat(timespec="seconds"), "projet": projet,
                            "caracteres": caracteres, "format": format, "duree_ms": duree_ms,
                            "cache": cache, "code": code}, ensure_ascii=False)
        self.dossier.mkdir(parents=True, exist_ok=True)
        chemin = self.dossier / f"journal-{local.date().isoformat()}.jsonl"
        with verrou(self.dossier / "journal"):
            nouveau = not chemin.exists()
            with open(chemin, "a", encoding="utf-8") as f:
                f.write(ligne + "\n")
            if nouveau and os.name != "nt":
                os.chmod(chemin, 0o600)
        if self._purge_faite_le != local.date():
            self._purge_faite_le = local.date()
            self._purger(local.date())

    def _purger(self, aujourd_hui: date) -> None:
        for f in self.dossier.glob("journal-*.jsonl"):
            try:
                jour = date.fromisoformat(f.name[len("journal-"):-len(".jsonl")])
            except ValueError:
                continue
            if (aujourd_hui - jour).days > self.jours:
                f.unlink(missing_ok=True)
