"""Journal des demandes : une ligne JSON par demande, un fichier par jour de Porto-Novo, effacé
après 90 jours. Jamais le texte demandé : il peut contenir des données personnelles."""

import json
import math
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

    # Lecture, pour l'onglet Appels de l'espace admin
    def _lignes(self, jour: date) -> list[dict]:
        try:
            texte = (self.dossier / f"journal-{jour.isoformat()}.jsonl").read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        lignes = []
        for brut in texte.splitlines():
            try:
                ligne = json.loads(brut)
            except ValueError:
                continue
            if isinstance(ligne, dict):
                lignes.append(ligne)
        return lignes

    def lire(self, jour: date, *, projet: str | None = None, page: int = 1, par_page: int = 50) -> dict:
        """Les demandes d'un jour, plus récentes d'abord, par pages de `par_page`."""
        lignes = [x for x in reversed(self._lignes(jour)) if projet is None or x.get("projet") == projet]
        pages = max(1, math.ceil(len(lignes) / par_page))
        debut = (page - 1) * par_page
        return {"lignes": lignes[debut:debut + par_page] if page >= 1 else [], "total": len(lignes), "page": page,
                "pages": pages}

    def resume(self, jour: date) -> dict:
        """Demandes du jour, erreurs (codes 400 et plus), temps moyen d'une vraie synthèse (200 hors cache)."""
        lignes = self._lignes(jour)
        durees = [x.get("duree_ms", 0) for x in lignes if x.get("code") == 200 and not x.get("cache")]
        return {"demandes": len(lignes), "erreurs": sum(1 for x in lignes if (x.get("code") or 0) >= 400),
                "temps_moyen_ms": round(sum(durees) / len(durees)) if durees else None}

    def jours_disponibles(self, aujourd_hui: date | None = None) -> list[str]:
        """Jours qui ont un journal, plus récents d'abord. Avec aujourd_hui, les jours de plus de 90 jours
        sont d'abord effacés : la purge ne passe qu'à l'écriture, et un service sans appel en garderait."""
        if aujourd_hui is not None:
            self._purger(aujourd_hui)
        jours = []
        for f in self.dossier.glob("journal-*.jsonl"):
            try:
                jours.append(date.fromisoformat(f.name[len("journal-"):-len(".jsonl")]).isoformat())
            except ValueError:
                continue
        return sorted(jours, reverse=True)
