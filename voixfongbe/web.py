"""Socle commun des pages et de l'API d'administration : contexte partagé, adresse du client,
contrôle de la même origine, cookie, corps JSON, en-têtes des pages et fichiers statiques.

Les pages, feuilles de style, scripts et polices sont dans voixfongbe/web/ et passent toujours par
l'application : jamais par un dossier public/, que le serveur servirait sans contrôle.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .reponses import ErreurApi

DOSSIER_WEB = Path(__file__).resolve().parent / "web"
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; "
       "connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
ENTETES_PAGE = [("Content-Type", "text/html; charset=utf-8"), ("Cache-Control", "no-store"),
                ("X-Frame-Options", "DENY"), ("Content-Security-Policy", CSP)]
TYPES_STATIQUES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                   ".woff2": "font/woff2", ".svg": "image/svg+xml"}
# Liste figée au chargement : seul un fichier présent dans voixfongbe/web/ peut être servi.
STATIQUES = {f.name: f for f in DOSSIER_WEB.glob("*") if f.suffix in TYPES_STATIQUES} if DOSSIER_WEB.is_dir() else {}


@dataclass
class Contexte:
    config: object
    moteur: object
    horloge: Callable[[], datetime]
    cles: object
    quotas: object
    reglages: object
    demandes: object
    connexion: object
    courriel: object  # Courriel, ou tout objet qui a configure() et envoyer()
    journal: object


def ip_client(environ) -> str:
    """Dernière entrée de X-Forwarded-For : celle qu'ajoute le serveur frontal, pas le client."""
    entrees = [x.strip() for x in environ.get("HTTP_X_FORWARDED_FOR", "").split(",") if x.strip()]
    return entrees[-1] if entrees else environ.get("REMOTE_ADDR") or "inconnue"


def meme_origine(environ, hote: str) -> bool:
    origine = environ.get("HTTP_ORIGIN")
    if origine:
        return urlsplit(origine).netloc == hote
    referer = environ.get("HTTP_REFERER")
    if referer:
        return urlsplit(referer).netloc == hote
    return False


def lire_cookie(environ, nom: str) -> str | None:
    for morceau in environ.get("HTTP_COOKIE", "").split(";"):
        cle, _, valeur = morceau.strip().partition("=")
        if cle == nom and valeur:
            return valeur
    return None


def lire_corps(environ, max_corps: int) -> dict:
    """Corps JSON : un objet, 8 Ko au plus. Un fichier écrit par Bloc-notes commence par un BOM."""
    try:
        longueur = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        longueur = 0
    if longueur > max_corps:
        raise ErreurApi("corps_trop_grand")
    brut = environ["wsgi.input"].read(longueur) if longueur > 0 else b""
    try:
        donnees = json.loads(brut.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise ErreurApi("json_invalide") from None
    if not isinstance(donnees, dict):
        raise ErreurApi("json_invalide")
    return donnees


def _type_json(environ) -> bool:
    return environ.get("CONTENT_TYPE", "").split(";")[0].strip().lower() == "application/json"


def lire_corps_json(environ, max_corps: int) -> dict:
    if not _type_json(environ):
        raise ErreurApi("type_contenu")
    return lire_corps(environ, max_corps)


def controler_post(environ, ctx: Contexte) -> None:
    """Toute action qui modifie : une page de ce site (contre les pages tierces), et du JSON (qu'un
    formulaire d'un autre site ne peut pas envoyer sans le consentement du navigateur)."""
    if not meme_origine(environ, ctx.config.hote):
        raise ErreurApi("origine")
    if not _type_json(environ):
        raise ErreurApi("type_contenu")


def page(nom: str):
    return 200, list(ENTETES_PAGE), (DOSSIER_WEB / nom).read_bytes()


def statique(nom: str):
    chemin = STATIQUES.get(nom)
    if chemin is None:
        return None
    # Les polices ne changent jamais ; un script ou un style est revalidé à chaque page, pour qu'un
    # ancien fichier en cache ne tourne pas avec une page mise à jour.
    duree = "public, max-age=31536000, immutable" if chemin.suffix == ".woff2" else "no-cache"
    return 200, [("Content-Type", TYPES_STATIQUES[chemin.suffix]), ("Cache-Control", duree)], chemin.read_bytes()
