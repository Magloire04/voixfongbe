"""Demandes d'accès déposées sur la page publique, en attendant la décision d'Elisée.

Données personnelles (nom, adresse, organisation, description) : gardées pour traiter la demande ;
une demande refusée est effacée 90 jours après la décision, une demande approuvée disparaît avec
son projet. L'adresse IP ne sert qu'à limiter les dépôts : seule son empreinte du jour est gardée.
"""

import hashlib
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .cles import NOM_PROJET
from .formats import valider_courriel
from .quotas import FUSEAU
from .stockage import ecrire_json, lire_json, verrou

LONGUEURS = {"nom": (2, 100), "organisation": (0, 120), "description": (20, 1000)}
SEPARATEURS = {" ", " ", "\x85"}
TRANSLITTERATION = str.maketrans({"ɖ": "d", "ɔ": "o", "ɛ": "e", "ŋ": "n", "ƒ": "f", "ʋ": "v", "ɣ": "g", "đ": "d"})


class ChampInvalide(ValueError):
    def __init__(self, champ: str, message: str):
        super().__init__(f"{champ} : {message}")
        self.champ = champ
        self.message = message


class DemandesFermees(Exception):
    pass


class TropDeDemandes(Exception):
    pass


def _controle(c: str) -> bool:
    return c in SEPARATEURS or unicodedata.category(c) == "Cc"


def _texte(donnees: dict, champ: str, libelle: str, une_ligne: bool) -> str:
    valeur = donnees.get(champ, "" if champ == "organisation" else None)
    if valeur is None and champ == "organisation":
        valeur = ""
    if not isinstance(valeur, str):
        raise ChampInvalide(champ, f"{libelle} : ce champ est obligatoire.")
    if une_ligne:
        if any(_controle(c) for c in valeur):
            raise ChampInvalide(champ, f"{libelle} : une seule ligne, sans caractère spécial.")
    else:
        valeur = valeur.replace("\r\n", "\n").replace("\r", "\n")
        valeur = "".join(c for c in valeur if c == "\n" or not _controle(c))
    valeur = valeur.strip()
    mini, maxi = LONGUEURS[champ]
    if not mini <= len(valeur) <= maxi:
        if mini:
            raise ChampInvalide(champ, f"{libelle} : de {mini} à {maxi:,} caractères.".replace(",", " "))
        raise ChampInvalide(champ, f"{libelle} : {maxi} caractères au plus.")
    return valeur


def valider(donnees: dict) -> dict:
    """Les champs du formulaire, contrôlés ; ChampInvalide sinon. Les balises restent du texte :
    l'espace admin les affiche telles quelles, sans jamais les interpréter."""
    nom = _texte(donnees, "nom", "Nom et prénom", une_ligne=True)
    courriel = donnees.get("courriel")
    try:
        courriel = valider_courriel(courriel)
    except ValueError:
        raise ChampInvalide("courriel", "Adresse e-mail : vérifiez-la, par exemple nom@exemple.bj.") from None
    organisation = _texte(donnees, "organisation", "Organisation", une_ligne=True)
    description = _texte(donnees, "description", "Votre projet", une_ligne=False)
    if donnees.get("accord") is not True:
        raise ChampInvalide("accord", "Cochez la case : la voix est réservée aux projets non commerciaux.")
    return {"nom": nom, "courriel": courriel, "organisation": organisation, "description": description}


def proposer_nom(nom: str, organisation: str, pris: set[str]) -> str:
    """Nom de projet au format des clés (a-z, 0-9, tiret ; 2 à 40 caractères), libre dans `pris`."""
    texte = unicodedata.normalize("NFD", (organisation or nom).lower().translate(TRANSLITTERATION))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    base = re.sub(r"[^a-z0-9]+", "-", texte).strip("-")[:40].strip("-")
    if len(base) < 2:
        base = "projet"
    candidat, n = base, 2
    while candidat in pris:
        suffixe = f"-{n}"
        candidat = base[:40 - len(suffixe)].rstrip("-") + suffixe
        n += 1
    assert NOM_PROJET.match(candidat)
    return candidat


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


class Demandes:
    def __init__(self, chemin: Path, max_en_attente: int = 50, par_ip: int = 3, jours_refus: int = 90):
        self.chemin = Path(chemin)
        self.max_en_attente = max_en_attente
        self.par_ip = par_ip
        self.jours_refus = jours_refus

    def _lire(self) -> dict:
        donnees = lire_json(self.chemin, {})
        donnees.setdefault("demandes", {})
        donnees.setdefault("ip", {"jour": None, "n": {}})
        return donnees

    def _purger(self, donnees: dict, maintenant: datetime) -> bool:
        limite = maintenant - timedelta(days=self.jours_refus)
        anciennes = [i for i, d in donnees["demandes"].items()
                     if d["etat"] == "refusee" and datetime.fromisoformat(d["decidee_le"]) < limite]
        for i in anciennes:
            del donnees["demandes"][i]
        return bool(anciennes)

    @staticmethod
    def _en_attente(donnees: dict) -> list[dict]:
        return sorted((d for d in donnees["demandes"].values() if d["etat"] == "en_attente"),
                      key=lambda d: d["recue_le"])

    def deposer(self, fiche: dict, *, ip: str, maintenant: datetime, pris: set[str]) -> dict:
        jour = maintenant.astimezone(FUSEAU).date().isoformat()
        with verrou(self.chemin):
            donnees = self._lire()
            self._purger(donnees, maintenant)
            if len(self._en_attente(donnees)) >= self.max_en_attente:
                raise DemandesFermees()
            if donnees["ip"]["jour"] != jour:
                donnees["ip"] = {"jour": jour, "n": {}}
            empreinte = hashlib.sha256(f"{jour}|{ip}".encode("utf-8")).hexdigest()
            deja = donnees["ip"]["n"].get(empreinte, 0)
            if deja >= self.par_ip:
                raise TropDeDemandes()
            donnees["ip"]["n"][empreinte] = deja + 1
            ident = secrets.token_hex(8)
            demande = {"id": ident, "nom": fiche["nom"], "courriel": fiche["courriel"],
                       "organisation": fiche.get("organisation", ""), "description": fiche["description"],
                       "projet_propose": proposer_nom(fiche["nom"], fiche.get("organisation", ""), pris),
                       "recue_le": _iso(maintenant), "etat": "en_attente", "decidee_le": None, "motif": None,
                       "projet": None}
            donnees["demandes"][ident] = demande
            ecrire_json(self.chemin, donnees)
        return dict(demande)

    def fermees(self) -> bool:
        return len(self._en_attente(self._lire())) >= self.max_en_attente

    def obtenir(self, ident: str) -> dict | None:
        demande = self._lire()["demandes"].get(ident)
        return dict(demande) if demande else None

    def en_attente(self) -> list[dict]:
        return self._en_attente(self._lire())

    def historique(self, maintenant: datetime) -> list[dict]:
        with verrou(self.chemin):
            donnees = self._lire()
            if self._purger(donnees, maintenant):
                ecrire_json(self.chemin, donnees)
        return sorted((d for d in donnees["demandes"].values() if d["etat"] != "en_attente"),
                      key=lambda d: d["decidee_le"], reverse=True)

    def _decider(self, ident: str, maintenant: datetime, **valeurs) -> None:
        with verrou(self.chemin):
            donnees = self._lire()
            demande = donnees["demandes"][ident]  # KeyError si la demande est inconnue
            if demande["etat"] != "en_attente":
                raise ValueError("demande déjà traitée")
            demande.update(decidee_le=_iso(maintenant), **valeurs)
            ecrire_json(self.chemin, donnees)

    def marquer_approuvee(self, ident: str, projet: str, maintenant: datetime) -> None:
        self._decider(ident, maintenant, etat="approuvee", projet=projet)

    def marquer_refusee(self, ident: str, motif: str | None, maintenant: datetime) -> None:
        self._decider(ident, maintenant, etat="refusee", motif=motif or None)

    def purger(self, maintenant: datetime) -> None:
        with verrou(self.chemin):
            donnees = self._lire()
            if self._purger(donnees, maintenant):
                ecrire_json(self.chemin, donnees)

    def effacer_projet(self, projet: str) -> None:
        with verrou(self.chemin):
            donnees = self._lire()
            donnees["demandes"] = {i: d for i, d in donnees["demandes"].items()
                                   if not (d["etat"] == "approuvee" and d["projet"] == projet)}
            ecrire_json(self.chemin, donnees)
