"""API de la voix fon (WSGI, sans framework).

    GET  /v1/etat       état du service, sans clé
    POST /v1/synthese   {"texte": "...", "format": "mp3" | "wav"} avec « Authorization: Bearer <clé> »
    GET  /robots.txt    refuse tous les robots

Pas de CORS : le service s'appelle depuis le serveur d'un projet, où la clé reste cachée.
"""

import json
import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as DelaiDepasse
from datetime import datetime, timezone
from http import HTTPStatus

from .audio import en_mp3, en_wav
from .cache import Cache
from .cles import Cles
from .config import Config
from .journal import Journal
from .moteur import ModeleIndisponible, Moteur
from .quotas import Quotas
from .texte import caracteres_ignores, identifiants, preparer

LICENCE = "MMS-TTS de Meta, CC BY-NC 4.0"
SECURITE = [
    ("Strict-Transport-Security", "max-age=31536000"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Robots-Tag", "noindex, nofollow"),
]
TYPES = {"mp3": "audio/mpeg", "wav": "audio/wav"}
ROUTES = {"/v1/etat": "GET", "/v1/synthese": "POST", "/robots.txt": "GET"}
HOTE = re.compile(r"[A-Za-z0-9.-]+(:\d{1,5})?")
HOTE_PAR_DEFAUT = "voix.bytechnum.com"
# Erreurs après lesquelles la demande n'est pas comptée dans le quota (rien n'a été rendu).
RENDRE_LE_QUOTA = {"voix_occupee", "delai_depasse", "modele_indisponible"}

MESSAGES = {
    "introuvable": (404, "Adresse inconnue. Voir /v1/etat et le README."),
    "methode": (405, "Méthode non acceptée pour cette adresse."),
    "cle_absente": (401, "Clé d'accès absente : en-tête « Authorization: Bearer <clé> »."),
    "cle_invalide": (401, "Clé d'accès inconnue ou révoquée."),
    "corps_trop_grand": (413, "Demande trop grande : 8 Ko au plus."),
    "json_invalide": (400, "Le corps doit être un objet JSON, par exemple {\"texte\": \"Mi kú abɔ.\"}."),
    "texte_absent": (400, "Le champ « texte » est absent ou n'est pas une chaîne de caractères."),
    "texte_trop_long": (400, "Texte trop long : 1 000 caractères au plus par demande."),
    "format_inconnu": (400, "Format inconnu : « mp3 » ou « wav »."),
    "quota_jour": (429, "Quota du jour atteint. Réessayez après minuit, heure de Porto-Novo."),
    "modele_indisponible": (503, "La voix est momentanément indisponible."),
    "texte_vide": (400, "Aucun caractère fon reconnu dans le texte : chiffres, signes et émojis sont ignorés."),
    "delai_depasse": (503, "La voix a mis trop de temps à répondre. Réessayez avec un texte plus court."),
    "voix_occupee": (503, "La voix prépare déjà une autre phrase. Réessayez dans quelques secondes."),
    "erreur_interne": (500, "Erreur interne du service."),
}


class ErreurApi(Exception):
    def __init__(self, code: str, entetes: list[tuple[str, str]] | None = None):
        super().__init__(code)
        self.code = code
        self.statut = MESSAGES[code][0]
        self.entetes = entetes or []


def _json(statut: int, donnees, entetes=None):
    corps = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
    return statut, [("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store"),
                    *(entetes or [])], corps


def _erreur(e: ErreurApi):
    return _json(e.statut, {"erreur": MESSAGES[e.code][1], "code": e.code}, e.entetes)


def creer_application(config: Config, moteur=None, horloge=None):
    moteur = moteur if moteur is not None else Moteur(config.dossier_modele, config.fils)
    horloge = horloge or (lambda: datetime.now(timezone.utc))
    stockage = config.dossier_stockage
    cles = Cles(stockage / "cles.json")
    quotas = Quotas(stockage / "quotas.json", config.par_cle, config.total_jour)
    cache = Cache(stockage / "cache", config.plafond_cache)
    journal = Journal(stockage / "journal")
    executeur = ThreadPoolExecutor(max_workers=1)
    # Une seule synthèse à la fois par processus : le compte n'a que 2 cœurs. Le verrou n'est libéré
    # qu'à la fin réelle du calcul, même si la demande a abandonné entre-temps.
    occupe = threading.Lock()

    def fabriquer(ids: list[int], format_: str, cle_cache: str) -> bytes:
        try:
            echantillons = moteur.synthetiser(ids)
            son = en_mp3(echantillons) if format_ == "mp3" else en_wav(echantillons)
            cache.ecrire(cle_cache, son)  # même en retard : le prochain essai le trouvera tout de suite
            return son
        finally:
            occupe.release()

    def lire_corps(environ) -> dict:
        try:
            longueur = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            longueur = 0
        if longueur > config.max_corps:
            raise ErreurApi("corps_trop_grand")
        brut = environ["wsgi.input"].read(longueur) if longueur > 0 else b""
        try:
            donnees = json.loads(brut.decode("utf-8-sig"))  # un fichier écrit par Bloc-notes commence par un BOM
        except (UnicodeDecodeError, ValueError):
            raise ErreurApi("json_invalide") from None
        if not isinstance(donnees, dict):
            raise ErreurApi("json_invalide")
        return donnees

    def synthese(environ, suivi: dict):
        schema, _, cle = environ.get("HTTP_AUTHORIZATION", "").strip().partition(" ")
        if schema.lower() != "bearer" or not cle.strip():
            raise ErreurApi("cle_absente")
        projet = cles.verifier(cle.strip())
        if projet is None:
            raise ErreurApi("cle_invalide")
        suivi["projet"] = projet

        donnees = lire_corps(environ)
        texte = donnees.get("texte")
        if not isinstance(texte, str):
            raise ErreurApi("texte_absent")
        suivi["caracteres"] = len(texte)
        if len(texte) > config.max_caracteres:
            raise ErreurApi("texte_trop_long")
        format_ = donnees.get("format", "mp3")
        if format_ not in TYPES:
            raise ErreurApi("format_inconnu")
        suivi["format"] = format_

        # Tout ce qui peut échouer sans rien produire passe avant le quota.
        if not moteur.pret():
            raise ErreurApi("modele_indisponible")
        vocabulaire = moteur.vocabulaire
        prepare = preparer(texte, vocabulaire)
        if not prepare:
            raise ErreurApi("texte_vide")

        maintenant = horloge()
        attente = quotas.consommer(projet, maintenant)
        if attente is not None:
            raise ErreurApi("quota_jour", [("Retry-After", str(attente))])
        try:
            cle_cache = Cache.cle(moteur.version, format_, prepare)
            son = cache.lire(cle_cache)
            suivi["cache"] = son is not None
            if son is None:
                if not occupe.acquire(blocking=False):
                    raise ErreurApi("voix_occupee", [("Retry-After", "5")])
                try:
                    tache = executeur.submit(fabriquer, identifiants(prepare, vocabulaire), format_, cle_cache)
                except BaseException:
                    occupe.release()
                    raise
                try:
                    son = tache.result(timeout=config.delai_s)
                except DelaiDepasse:
                    raise ErreurApi("delai_depasse") from None
                except ModeleIndisponible:
                    raise ErreurApi("modele_indisponible") from None
        except ErreurApi as e:
            if e.code in RENDRE_LE_QUOTA:
                quotas.rendre(projet, maintenant)
            raise
        except Exception:
            quotas.rendre(projet, maintenant)
            raise
        return 200, [("Content-Type", TYPES[format_]), ("X-Voix-Licence", LICENCE),
                     ("X-Voix-Cache", "oui" if suivi["cache"] else "non"),
                     ("X-Voix-Caracteres-Ignores", str(caracteres_ignores(texte, vocabulaire)))], son

    def traiter(environ, suivi: dict):
        methode = environ.get("REQUEST_METHOD", "GET")
        chemin = environ.get("PATH_INFO", "")
        if chemin not in ROUTES:
            raise ErreurApi("introuvable")
        if methode != ROUTES[chemin]:
            raise ErreurApi("methode", [("Allow", ROUTES[chemin])])
        if environ.get("HTTP_X_FORWARDED_PROTO", "").lower() == "http":
            # Seulement vers une route connue, avec un hôte vérifié : rien de ce que le client
            # envoie ne peut glisser un retour à la ligne dans l'en-tête Location.
            hote = next((h for h in (environ.get("HTTP_HOST", ""), environ.get("SERVER_NAME", ""))
                         if HOTE.fullmatch(h)), HOTE_PAR_DEFAUT)
            # 308 garde la méthode et le corps d'un POST ; 301 pour une simple lecture.
            return 301 if methode in ("GET", "HEAD") else 308, [("Location", f"https://{hote}{chemin}")], b""
        if chemin == "/robots.txt":
            return 200, [("Content-Type", "text/plain; charset=utf-8")], b"User-agent: *\nDisallow: /\n"
        if chemin == "/v1/etat":
            return _json(200, {"service": "voix fon", "version": moteur.version, "modele": "facebook/mms-tts-fon",
                               "licence": "CC BY-NC 4.0", "pret": moteur.pret()})
        suivi["journal"] = True
        return synthese(environ, suivi)

    def application(environ, start_response):
        debut = time.monotonic()
        suivi = {"journal": False, "projet": None, "caracteres": 0, "format": None, "cache": False}
        try:
            statut, entetes, corps = traiter(environ, suivi)
        except ErreurApi as e:
            statut, entetes, corps = _erreur(e)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            statut, entetes, corps = _erreur(ErreurApi("erreur_interne"))
        if suivi["journal"]:
            try:
                journal.noter(projet=suivi["projet"], caracteres=suivi["caracteres"], format=suivi["format"],
                              duree_ms=round((time.monotonic() - debut) * 1000), cache=suivi["cache"],
                              code=statut, maintenant=horloge())
            except Exception:
                traceback.print_exc(file=sys.stderr)
        raison = HTTPStatus(statut).phrase
        start_response(f"{statut} {raison}", [*SECURITE, *entetes, ("Content-Length", str(len(corps)))])
        return [corps]

    return application
