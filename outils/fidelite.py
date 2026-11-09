"""Vérifie que la voix convertie en ONNX dit la même chose que la voix d'origine (PyTorch).

À lancer sur le PC, après outils/convertir.py et outils/convertir.py --bruit-nul :

    python outils/fidelite.py

1. Hasard coupé des deux côtés (modele-test/) : pour 10 phrases de tests/donnees/phrases.txt,
   même nombre d'échantillons et écart absolu maximal inférieur à 1e-3, sinon échec.
2. Réglages normaux (modele/) : une paire de WAV par phrase dans fidelite/, pour l'écoute
   (pytorch-NN.wav et onnx-NN.wav). Le hasard rend chaque version un peu différente.
"""

import sys
from pathlib import Path

import numpy
import onnxruntime
import scipy.io.wavfile
import torch
from transformers import AutoTokenizer, VitsModel

MODELE = "facebook/mms-tts-fon"
RACINE = Path(__file__).resolve().parent.parent
SEUIL = 1e-3
NOMBRE = 10


def phrases() -> list[str]:
    lignes = (RACINE / "tests" / "donnees" / "phrases.txt").read_text(encoding="utf-8").splitlines()
    return [l for l in lignes if l.strip()]


def session(dossier: Path) -> onnxruntime.InferenceSession:
    return onnxruntime.InferenceSession(str(dossier / "model.onnx"), providers=["CPUExecutionProvider"])


def onnx_son(s: onnxruntime.InferenceSession, ids: numpy.ndarray) -> numpy.ndarray:
    return s.run(["waveform"], {"input_ids": ids, "attention_mask": numpy.ones_like(ids)})[0][0]


def main() -> int:
    tokenizer = AutoTokenizer.from_pretrained(MODELE)
    modele = VitsModel.from_pretrained(MODELE).eval()
    taux = modele.config.sampling_rate
    retenues = []
    for texte in phrases():
        ids = tokenizer(texte, return_tensors="pt").input_ids
        if ids.shape[1] > 2:  # au moins un vrai symbole entre les blancs
            retenues.append((texte, ids))
        if len(retenues) == NOMBRE:
            break

    print("1. Hasard coupé")
    # VitsModel recopie ces réglages à sa création (modeling_vits.py) : changer config ne suffit pas.
    modele.noise_scale = 0.0
    modele.noise_scale_duration = 0.0
    test = session(RACINE / "modele-test")
    echecs = 0
    for i, (texte, ids) in enumerate(retenues, 1):
        with torch.no_grad():
            ref = modele(ids).waveform[0].numpy()
        son = onnx_son(test, ids.numpy())
        ecart = float(numpy.abs(ref - son).max()) if len(ref) == len(son) else float("inf")
        ok = len(ref) == len(son) and ecart < SEUIL
        echecs += not ok
        print(f"  {i:2d} {'conforme' if ok else 'ÉCART  '} {len(ref):6d} / {len(son):6d} échantillons, "
              f"écart max {ecart:.2e}  {texte[:50]}")

    print("2. Réglages normaux : paires à écouter dans fidelite/")
    modele.noise_scale = modele.config.noise_scale
    modele.noise_scale_duration = modele.config.noise_scale_duration
    normal = session(RACINE / "modele")
    dossier = RACINE / "fidelite"
    dossier.mkdir(exist_ok=True)
    for i, (texte, ids) in enumerate(retenues, 1):
        torch.manual_seed(i)
        with torch.no_grad():
            ref = modele(ids).waveform[0].numpy()
        son = onnx_son(normal, ids.numpy())
        scipy.io.wavfile.write(dossier / f"pytorch-{i:02d}.wav", taux, ref)
        scipy.io.wavfile.write(dossier / f"onnx-{i:02d}.wav", taux, son)
        print(f"  {i:2d} pytorch {len(ref) / taux:4.1f} s | onnx {len(son) / taux:4.1f} s  {texte[:50]}")

    print(f"\n{len(retenues) - echecs} phrase(s) conforme(s) sur {len(retenues)}.")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
