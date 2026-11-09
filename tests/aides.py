"""Aides des tests : une fausse voix (pas besoin du modèle) et un appel WSGI direct."""

import io
import json
import time
from pathlib import Path

import numpy

from voixfongbe.moteur import ModeleIndisponible
from voixfongbe.texte import charger_vocabulaire

VOCAB = charger_vocabulaire(Path(__file__).resolve().parent / "donnees" / "vocab.json")


class MoteurFactice:
    def __init__(self, pret: bool = True, delai_s: float = 0.0, erreur: Exception | None = None):
        self._pret = pret
        self.delai_s = delai_s
        self.erreur = erreur
        self.appels = 0
        self.longueurs = []  # longueur des identifiants reçus, par appel

    def pret(self) -> bool:
        return self._pret

    @property
    def version(self) -> str | None:
        return "factice00001" if self._pret else None

    @property
    def vocabulaire(self) -> dict[str, int]:
        return VOCAB if self._pret else {}

    def synthetiser(self, ids: list[int]) -> numpy.ndarray:
        if not self._pret:
            raise ModeleIndisponible("factice")
        self.appels += 1
        self.longueurs.append(len(ids))
        if self.erreur:
            raise self.erreur
        time.sleep(self.delai_s)
        return (0.3 * numpy.sin(numpy.arange(160 * len(ids)) / 8)).astype(numpy.float32)


class CourrielFactice:
    """Remplace l'envoi SMTP : note les e-mails au lieu de les envoyer."""

    def __init__(self):
        self.envoyes = []  # {"a", "sujet", "texte"}
        self.en_panne = False
        self.configure_ = True

    def configure(self) -> bool:
        return self.configure_

    def envoyer(self, destinataire: str, sujet: str, texte: str) -> bool:
        if self.en_panne or not self.configure_:
            return False
        self.envoyes.append({"a": destinataire, "sujet": sujet, "texte": texte})
        return True


def appeler(app, methode: str, chemin: str, corps=None, entetes: dict | None = None):
    """Rend (statut, entêtes, corps). corps : dict (envoyé en JSON), bytes ou None."""
    if isinstance(corps, (dict, list)):
        donnees = json.dumps(corps).encode("utf-8")
    else:
        donnees = corps or b""
    environ = {
        "REQUEST_METHOD": methode, "PATH_INFO": chemin, "QUERY_STRING": "", "SERVER_NAME": "voix.bytechnum.com",
        "SERVER_PORT": "443", "HTTP_HOST": "voix.bytechnum.com", "wsgi.url_scheme": "https",
        "wsgi.input": io.BytesIO(donnees), "wsgi.errors": io.StringIO(), "CONTENT_LENGTH": str(len(donnees)),
        "CONTENT_TYPE": "application/json",
    }
    for nom, valeur in (entetes or {}).items():
        environ["HTTP_" + nom.upper().replace("-", "_")] = valeur
    recu = {}

    def start_response(statut, liste, exc_info=None):
        recu["statut"] = int(statut.split()[0])
        recu["entetes"] = dict(liste)

    corps_rendu = b"".join(app(environ, start_response))
    return recu["statut"], recu["entetes"], corps_rendu
