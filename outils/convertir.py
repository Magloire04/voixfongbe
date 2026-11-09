"""Convertit la voix fon de Meta (facebook/mms-tts-fon, licence CC BY-NC 4.0) au format ONNX.

À lancer sur le PC, dans l'environnement des outils (outils/requirements.txt) :

    python outils/convertir.py               -> modele/ : model.onnx, vocab.json, empreinte.txt
    python outils/convertir.py --bruit-nul   -> modele-test/ : même voix, hasard de la synthèse coupé,
                                                pour comparer exactement avec PyTorch (outils/fidelite.py)

Le dossier modele/ est ensuite copié tel quel sur le serveur. empreinte.txt contient l'empreinte
SHA-256 de model.onnx : le service refuse de démarrer la voix si le fichier ne correspond pas.
"""

import argparse
import hashlib
import shutil
import tempfile
from pathlib import Path

import onnxruntime
from huggingface_hub import hf_hub_download
from optimum.exporters.onnx import main_export
from transformers import AutoTokenizer, VitsModel

MODELE = "facebook/mms-tts-fon"
RACINE = Path(__file__).resolve().parent.parent


def empreinte(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def exporter(source: str, sortie: Path, valider: bool) -> None:
    """valider : contrôle de Hugging Face (mêmes sorties que PyTorch). Impossible avec le hasard de la
    synthèse (la durée des sons change d'un essai à l'autre) : seulement pour la copie sans hasard."""
    sortie.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        main_export(model_name_or_path=source, output=tmp, task="text-to-audio", do_validation=valider)
        shutil.copy2(Path(tmp) / "model.onnx", sortie / "model.onnx")
    shutil.copy2(hf_hub_download(MODELE, "vocab.json"), sortie / "vocab.json")
    (sortie / "empreinte.txt").write_text(empreinte(sortie / "model.onnx") + "\n", encoding="ascii")


def decrire(sortie: Path) -> None:
    session = onnxruntime.InferenceSession(str(sortie / "model.onnx"), providers=["CPUExecutionProvider"])
    print(f"{sortie / 'model.onnx'} ({(sortie / 'model.onnx').stat().st_size / 1e6:.1f} Mo)")
    for e in session.get_inputs():
        print(f"  entrée {e.name} {e.type} {e.shape}")
    for s in session.get_outputs():
        print(f"  sortie {s.name} {s.type} {s.shape}")
    print(f"  empreinte {(sortie / 'empreinte.txt').read_text().strip()}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bruit-nul", action="store_true", help="exporter une copie sans hasard, pour les comparaisons")
    args = p.parse_args()

    if not args.bruit_nul:
        sortie = RACINE / "modele"
        exporter(MODELE, sortie, valider=False)
    else:
        sortie = RACINE / "modele-test"
        with tempfile.TemporaryDirectory() as tmp:
            modele = VitsModel.from_pretrained(MODELE)
            modele.config.noise_scale = 0.0
            modele.config.noise_scale_duration = 0.0
            modele.save_pretrained(tmp)
            AutoTokenizer.from_pretrained(MODELE).save_pretrained(tmp)
            exporter(tmp, sortie, valider=True)
    decrire(sortie)


if __name__ == "__main__":
    main()
