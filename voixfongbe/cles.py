"""Projets et clés d'accès. Le fichier ne garde que l'empreinte SHA-256 de chaque clé et de chaque
lien d'accès : même lu par quelqu'un d'autre, il ne permet pas d'utiliser le service.

Fiche d'un projet : empreinte de la clé (absente tant que la personne n'a pas ouvert son lien, ou
après une révocation), date de création, limite quotidienne, coordonnées facultatives, date de
révocation, et lien d'accès en attente (empreinte du jeton, expiration). Une fiche à l'ancien
format, {"empreinte", "cree_le"}, prend les valeurs par défaut : elle continue de marcher.
"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .formats import valider_courriel, valider_limite
from .stockage import ecrire_json, lire_json, verrou

NOM_PROJET = re.compile(r"[a-z0-9-]{2,40}")  # toujours avec fullmatch : « $ » laisserait passer un retour à la ligne final
LIMITE_PAR_DEFAUT = 100
DUREE_LIEN = timedelta(days=7)
DEFAUTS = {"empreinte": None, "cree_le": None, "limite": LIMITE_PAR_DEFAUT, "courriel": None, "nom": None,
           "organisation": None, "revoquee_le": None, "lien": None}


def _empreinte(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _maintenant(maintenant: datetime | None) -> datetime:
    return (maintenant or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _verifier_nom(projet: str) -> None:
    if not isinstance(projet, str) or not NOM_PROJET.fullmatch(projet):
        raise ValueError("nom de projet invalide : 2 à 40 caractères parmi a-z, 0-9 et le tiret")


def _lien_ouvert(fiche: dict, maintenant: datetime) -> bool:
    lien = fiche["lien"]
    return bool(lien) and datetime.fromisoformat(lien["expire_le"]) > maintenant


def _etat(fiche: dict, maintenant: datetime) -> str:
    if fiche["empreinte"]:
        return "active"
    if fiche["lien"]:
        return "lien_en_attente" if _lien_ouvert(fiche, maintenant) else "lien_expire"
    return "revoquee"


class Cles:
    def __init__(self, chemin: Path):
        self.chemin = Path(chemin)

    def _lire(self) -> dict:
        donnees = lire_json(self.chemin, {"projets": {}})
        donnees["projets"] = {p: {**DEFAUTS, **f} for p, f in donnees.get("projets", {}).items()}
        return donnees

    def _nouveau_lien(self, fiche: dict, maintenant: datetime) -> str:
        jeton = secrets.token_urlsafe(32)
        fiche["lien"] = {"empreinte": _empreinte(jeton), "expire_le": _iso(maintenant + DUREE_LIEN)}
        return jeton

    def _par_lien(self, donnees: dict, jeton: str, maintenant: datetime) -> str | None:
        """Projet dont le lien ouvert correspond au jeton ; toutes les fiches sont comparées."""
        if not jeton:
            return None
        empreinte = _empreinte(jeton)
        trouve = None
        for projet, fiche in donnees["projets"].items():
            lien = fiche["lien"]
            if lien and hmac.compare_digest(lien["empreinte"], empreinte) and _lien_ouvert(fiche, maintenant):
                trouve = projet
        return trouve

    # Clé créée en SSH
    def creer(self, projet: str, maintenant: datetime | None = None) -> str:
        _verifier_nom(projet)
        moment = _maintenant(maintenant)
        with verrou(self.chemin):
            donnees = self._lire()
            fiche = donnees["projets"].get(projet)
            if fiche and fiche["empreinte"]:
                raise ValueError(f"le projet « {projet} » a déjà une clé : la révoquer d'abord")
            fiche = fiche or {**DEFAUTS, "cree_le": _iso(moment)}
            cle = secrets.token_urlsafe(32)
            fiche.update(empreinte=_empreinte(cle), lien=None, revoquee_le=None)
            donnees["projets"][projet] = fiche
            ecrire_json(self.chemin, donnees)
        return cle

    def verifier(self, cle: str) -> str | None:
        if not cle:
            return None
        empreinte = _empreinte(cle)
        trouve = None
        for projet, fiche in self._lire()["projets"].items():  # tout parcourir : durée constante
            if fiche["empreinte"] and hmac.compare_digest(fiche["empreinte"], empreinte):
                trouve = projet
        return trouve

    def revoquer(self, projet: str, maintenant: datetime | None = None) -> bool:
        with verrou(self.chemin):
            donnees = self._lire()
            fiche = donnees["projets"].get(projet)
            if fiche is None or (not fiche["empreinte"] and not fiche["lien"]):
                return False
            fiche.update(empreinte=None, lien=None, revoquee_le=_iso(_maintenant(maintenant)))
            ecrire_json(self.chemin, donnees)
        return True

    def lister(self, maintenant: datetime | None = None) -> list[dict]:
        moment = _maintenant(maintenant)
        return [{"projet": p, "cree_le": f["cree_le"], "limite": f["limite"], "courriel": f["courriel"],
                 "nom": f["nom"], "organisation": f["organisation"], "etat": _etat(f, moment),
                 "lien_expire_le": f["lien"]["expire_le"] if f["lien"] else None}
                for p, f in sorted(self._lire()["projets"].items())]

    # Accès par lien, sans terminal
    def preparer(self, projet: str, *, courriel: str, limite: int = LIMITE_PAR_DEFAUT, nom: str | None = None,
                 organisation: str | None = None, maintenant: datetime) -> str:
        """Crée un projet sans clé, avec un lien d'accès ; rend le jeton du lien (jamais gardé en clair)."""
        _verifier_nom(projet)
        courriel = valider_courriel(courriel)
        limite = valider_limite(limite)
        moment = _maintenant(maintenant)
        with verrou(self.chemin):
            donnees = self._lire()
            if projet in donnees["projets"]:
                raise ValueError(f"le nom de projet « {projet} » est déjà pris")
            fiche = {**DEFAUTS, "cree_le": _iso(moment), "limite": limite, "courriel": courriel, "nom": nom,
                     "organisation": organisation}
            jeton = self._nouveau_lien(fiche, moment)
            donnees["projets"][projet] = fiche
            ecrire_json(self.chemin, donnees)
        return jeton

    def nouveau_lien(self, projet: str, maintenant: datetime) -> str:
        """Révoque la clé actuelle s'il y en a une et rend le jeton d'un nouveau lien de 7 jours."""
        moment = _maintenant(maintenant)
        with verrou(self.chemin):
            donnees = self._lire()
            fiche = donnees["projets"][projet]
            if not fiche["courriel"]:
                raise ValueError("ce projet n'a pas d'adresse e-mail")
            fiche.update(empreinte=None, revoquee_le=None)
            jeton = self._nouveau_lien(fiche, moment)
            ecrire_json(self.chemin, donnees)
        return jeton

    def lien_valide(self, jeton: str, maintenant: datetime) -> str | None:
        return self._par_lien(self._lire(), jeton, _maintenant(maintenant))

    def utiliser_lien(self, jeton: str, maintenant: datetime) -> tuple[str, str] | None:
        """Crée la clé du projet et ferme le lien : la clé n'est rendue qu'une seule fois."""
        moment = _maintenant(maintenant)
        with verrou(self.chemin):
            donnees = self._lire()
            projet = self._par_lien(donnees, jeton, moment)
            if projet is None:
                return None
            cle = secrets.token_urlsafe(32)
            donnees["projets"][projet].update(empreinte=_empreinte(cle), lien=None, revoquee_le=None)
            ecrire_json(self.chemin, donnees)
        return projet, cle

    def supprimer(self, projet: str) -> bool:
        """Efface la fiche (et ses coordonnées) d'un projet déjà révoqué."""
        with verrou(self.chemin):
            donnees = self._lire()
            fiche = donnees["projets"].get(projet)
            if fiche is None:
                return False
            if fiche["empreinte"] or fiche["lien"]:
                raise ValueError("révoquer le projet avant de le supprimer")
            del donnees["projets"][projet]
            ecrire_json(self.chemin, donnees)
        return True

    def _modifier(self, projet: str, **valeurs) -> None:
        with verrou(self.chemin):
            donnees = self._lire()
            donnees["projets"][projet].update(valeurs)  # KeyError si le projet est inconnu
            ecrire_json(self.chemin, donnees)

    def changer_limite(self, projet: str, limite: int) -> None:
        self._modifier(projet, limite=valider_limite(limite))

    def changer_courriel(self, projet: str, courriel: str) -> None:
        self._modifier(projet, courriel=valider_courriel(courriel))

    def limite(self, projet: str) -> int:
        fiche = self._lire()["projets"].get(projet)
        return fiche["limite"] if fiche else LIMITE_PAR_DEFAUT
