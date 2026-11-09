"""Petits fichiers JSON du service : écriture atomique, droits 600, verrou entre processus.

Passenger peut lancer plusieurs processus de l'application en même temps : toute lecture suivie
d'une écriture (quotas, clés) se fait sous verrou() pour qu'aucun décompte ne se perde.
"""

import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

ATTENTE_MAX_S = 30


def lire_json(chemin: Path, defaut):
    try:
        return json.loads(Path(chemin).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return defaut


def ecrire_json(chemin: Path, donnees) -> None:
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, prefix=f".{chemin.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False)
        if os.name != "nt":
            os.chmod(tmp, 0o600)
        os.replace(tmp, chemin)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@contextmanager
def verrou(chemin: Path):
    """Verrou exclusif sur <chemin>.verrou, partagé par tous les processus de l'application."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(f"{chemin}.verrou", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.name == "nt":
            import msvcrt

            limite = time.monotonic() + ATTENTE_MAX_S
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() > limite:
                        raise
                    time.sleep(0.01)
            try:
                yield
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
