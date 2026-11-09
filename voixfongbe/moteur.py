"""La voix elle-même : le modèle ONNX de facebook/mms-tts-fon, lu avec onnxruntime.

Le dossier du modèle contient model.onnx, vocab.json et empreinte.txt (SHA-256 de model.onnx,
écrite par outils/convertir.py). Tant que l'empreinte ne correspond pas, la voix est indisponible :
un fichier tronqué pendant l'envoi ne produit jamais de son faux.
"""

import hashlib
import json
import threading
import time
from pathlib import Path

import numpy

TAUX = 16000
REVERIFIER_S = 60  # un modèle absent ou faux est revérifié au plus une fois par minute


class ModeleIndisponible(Exception):
    pass


def _empreinte(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


class Moteur:
    def __init__(self, dossier_modele: Path, fils: int = 2):
        self.dossier = Path(dossier_modele)
        self.fils = fils
        self._pret = False
        self._verifie_le = None
        self._version = None
        self._vocabulaire = {}
        self._session = None
        self._verrou = threading.Lock()

    def pret(self) -> bool:
        with self._verrou:
            if self._pret:
                return True
            if self._verifie_le is not None and time.monotonic() - self._verifie_le < REVERIFIER_S:
                return False
            self._verifie_le = time.monotonic()
            try:
                attendue = (self.dossier / "empreinte.txt").read_text(encoding="ascii").strip()
                vocabulaire = json.loads((self.dossier / "vocab.json").read_text(encoding="utf-8"))
                reelle = _empreinte(self.dossier / "model.onnx")
            except (OSError, ValueError):
                return False
            if reelle != attendue:
                return False
            self._pret, self._version, self._vocabulaire = True, reelle[:12], vocabulaire
            return True

    @property
    def version(self) -> str | None:
        return self._version if self.pret() else None

    @property
    def vocabulaire(self) -> dict[str, int]:
        return self._vocabulaire if self.pret() else {}

    def _ouvrir(self):
        import onnxruntime  # chargé seulement quand la voix sert : démarrage plus rapide

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = self.fils
        options.inter_op_num_threads = 1
        return onnxruntime.InferenceSession(str(self.dossier / "model.onnx"), options,
                                            providers=["CPUExecutionProvider"])

    def synthetiser(self, ids: list[int]) -> numpy.ndarray:
        if not self.pret():
            raise ModeleIndisponible("modèle absent ou empreinte fausse")
        with self._verrou:
            if self._session is None:
                try:
                    self._session = self._ouvrir()
                except Exception as e:
                    # Empreinte juste mais fichier illisible (version d'onnxruntime, export abîmé) :
                    # la voix est indisponible, /v1/etat le dira.
                    self._pret, self._verifie_le, self._version = False, time.monotonic(), None
                    raise ModeleIndisponible(f"modèle illisible : {e}") from e
            session = self._session
        entree = numpy.array([ids], dtype=numpy.int64)
        donnees = {"input_ids": entree}
        if any(e.name == "attention_mask" for e in session.get_inputs()):
            donnees["attention_mask"] = numpy.ones_like(entree)
        son = session.run(["waveform"], donnees)[0][0]
        return son.astype(numpy.float32, copy=False)
