"""Sons déjà fabriqués, gardés sur disque sous l'empreinte de (version du modèle, format, texte
préparé). Au-delà du plafond, les moins récemment servis sont effacés d'abord."""

import hashlib
import os
import re
import tempfile
from pathlib import Path

NOM = re.compile(r"^[0-9a-f]{64}$")


class Cache:
    def __init__(self, dossier: Path, plafond: int = 200 * 1024 * 1024):
        self.dossier = Path(dossier)
        self.plafond = plafond

    @staticmethod
    def cle(version: str, format: str, texte_prepare: str) -> str:
        return hashlib.sha256(f"{version}\n{format}\n{texte_prepare}".encode("utf-8")).hexdigest()

    def _chemin(self, cle: str) -> Path:
        if not NOM.match(cle):
            raise ValueError("clé de cache invalide")
        return self.dossier / cle

    def lire(self, cle: str) -> bytes | None:
        chemin = self._chemin(cle)
        try:
            donnees = chemin.read_bytes()
            os.utime(chemin)  # servi à l'instant : il passe en dernier pour la purge
            return donnees
        except FileNotFoundError:
            return None

    def ecrire(self, cle: str, donnees: bytes) -> None:
        chemin = self._chemin(cle)
        self.dossier.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.dossier, prefix=".", suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(donnees)
        os.replace(tmp, chemin)
        self._purger(garder=cle)

    def _purger(self, garder: str) -> None:
        fichiers = []
        for f in self.dossier.iterdir():
            if NOM.match(f.name):
                try:
                    st = f.stat()
                except FileNotFoundError:
                    continue
                fichiers.append((st.st_mtime, st.st_size, f))
        total = sum(taille for _, taille, _ in fichiers)
        for _, taille, f in sorted(x for x in fichiers if x[2].name != garder):
            if total <= self.plafond:
                break
            f.unlink(missing_ok=True)
            total -= taille
