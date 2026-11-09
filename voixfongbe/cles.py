"""Clés d'accès, une par projet. Le fichier ne garde que l'empreinte SHA-256 de chaque clé :
même lu par quelqu'un d'autre, il ne permet pas d'utiliser le service."""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from .stockage import ecrire_json, lire_json, verrou

NOM_PROJET = re.compile(r"^[a-z0-9-]{2,40}$")


def _empreinte(cle: str) -> str:
    return hashlib.sha256(cle.encode("utf-8")).hexdigest()


class Cles:
    def __init__(self, chemin: Path):
        self.chemin = Path(chemin)

    def _lire(self) -> dict:
        return lire_json(self.chemin, {"projets": {}})

    def creer(self, projet: str) -> str:
        if not NOM_PROJET.match(projet):
            raise ValueError("nom de projet invalide : 2 à 40 caractères parmi a-z, 0-9 et le tiret")
        with verrou(self.chemin):
            donnees = self._lire()
            if projet in donnees["projets"]:
                raise ValueError(f"le projet « {projet} » a déjà une clé : la révoquer d'abord")
            cle = secrets.token_urlsafe(32)
            donnees["projets"][projet] = {
                "empreinte": _empreinte(cle),
                "cree_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            ecrire_json(self.chemin, donnees)
        return cle

    def verifier(self, cle: str) -> str | None:
        if not cle:
            return None
        empreinte = _empreinte(cle)
        trouve = None
        for projet, fiche in self._lire()["projets"].items():  # tout parcourir : durée constante
            if hmac.compare_digest(fiche["empreinte"], empreinte):
                trouve = projet
        return trouve

    def revoquer(self, projet: str) -> bool:
        with verrou(self.chemin):
            donnees = self._lire()
            if projet not in donnees["projets"]:
                return False
            del donnees["projets"][projet]
            ecrire_json(self.chemin, donnees)
        return True

    def lister(self) -> list[dict]:
        return [{"projet": p, "cree_le": f["cree_le"]} for p, f in sorted(self._lire()["projets"].items())]
