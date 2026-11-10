"""API de la voix fon (WSGI, sans framework).

    GET  /v1/etat       état du service, sans clé
    POST /v1/synthese   {"texte": "...", "format": "mp3" | "wav"} avec « Authorization: Bearer <clé> »
    GET  /robots.txt    refuse tous les robots

Plus les pages publiques (demande d'accès, lien d'accès, fichiers statiques : publiques.py) et
l'espace d'administration (/admin et /api/admin/… : admin.py).

Pas de CORS : le service s'appelle depuis le serveur d'un projet, où la clé reste cachée.
"""

import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as DelaiDepasse
from datetime import datetime, timezone
from http import HTTPStatus

import numpy

from . import admin, publiques
from .audio import TAUX, en_mp3, en_wav
from .cache import Cache
from .cles import Cles
from .config import Config
from .connexion import Connexion
from .courriel import Courriel
from .demandes import Demandes
from .journal import Journal
from .moteur import ModeleIndisponible, Moteur
from .quotas import Quotas
from .reglages import Reglages
from .reponses import ErreurApi, reponse_erreur, reponse_json
from .texte import borner, caracteres_ignores, decouper, identifiants, preparer
from .web import Contexte, lire_corps

PAUSE_S = 0.15  # entre deux morceaux d'un long texte

LICENCE = "MMS-TTS de Meta, CC BY-NC 4.0"
SECURITE = [
    ("Strict-Transport-Security", "max-age=31536000"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Robots-Tag", "noindex, nofollow"),
]
TYPES = {"mp3": "audio/mpeg", "wav": "audio/wav"}
HOTE = re.compile(r"[A-Za-z0-9.-]+(:\d{1,5})?")
HOTE_PAR_DEFAUT = "voix.bytechnum.com"
# Erreurs après lesquelles la demande n'est pas comptée : aucun calcul n'a eu lieu. Un délai dépassé
# compte, car le calcul tourne jusqu'au bout : sinon une clé occuperait le processeur sans rien payer.
RENDRE_LE_QUOTA = {"voix_occupee", "modele_indisponible"}


def creer_application(config: Config, moteur=None, horloge=None, courriel=None):
    moteur = moteur if moteur is not None else Moteur(config.dossier_modele, config.fils)
    horloge = horloge or (lambda: datetime.now(timezone.utc))
    stockage = config.dossier_stockage
    cles = Cles(stockage / "cles.json")
    quotas = Quotas(stockage / "quotas.json", total=config.total_jour)
    reglages = Reglages(stockage / "reglages.json", config.adresse_annonces, config.total_jour)
    cache = Cache(stockage / "cache", config.plafond_cache)
    journal = Journal(stockage / "journal")
    ctx = Contexte(config=config, moteur=moteur, horloge=horloge, cles=cles, quotas=quotas, reglages=reglages,
                   demandes=Demandes(stockage / "demandes.json"), connexion=Connexion(stockage / "admin.json"),
                   courriel=courriel if courriel is not None else Courriel(stockage / "smtp.json"),
                   journal=journal)
    executeur = ThreadPoolExecutor(max_workers=1)
    # Une seule synthèse à la fois par processus : le compte n'a que 2 cœurs. Le verrou n'est libéré
    # qu'à la fin réelle du calcul, même si la demande a abandonné entre-temps.
    occupe = threading.Lock()

    def fabriquer(morceaux: list[list[int]], format_: str, cle_cache: str) -> bytes:
        try:
            pause = numpy.zeros(int(PAUSE_S * TAUX), dtype=numpy.float32)
            sons = []
            for i, ids in enumerate(morceaux):  # morceau par morceau : la mémoire reste bornée
                if i:
                    sons.append(pause)
                sons.append(moteur.synthetiser(ids))
            echantillons = numpy.concatenate(sons)
            son = en_mp3(echantillons) if format_ == "mp3" else en_wav(echantillons)
            cache.ecrire(cle_cache, son)  # même en retard : le prochain essai le trouvera tout de suite
            return son
        finally:
            occupe.release()

    def synthese(environ, suivi: dict):
        schema, _, cle = environ.get("HTTP_AUTHORIZATION", "").strip().partition(" ")
        if schema.lower() != "bearer" or not cle.strip():
            raise ErreurApi("cle_absente")
        projet = cles.verifier(cle.strip())
        if projet is None:
            raise ErreurApi("cle_invalide")
        suivi["projet"] = projet

        donnees = lire_corps(environ, config.max_corps)
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
        # decouper() borne le texte reçu, borner() le texte préparé : aucun morceau ne dépasse
        # max_morceau symboles, quelle que soit l'entrée (mot sans espace, accents décomposés).
        prepares = [b for m in decouper(texte, config.max_morceau)
                    for b in borner(preparer(m, vocabulaire), config.max_morceau)]
        if not prepares:
            raise ErreurApi("texte_vide")

        maintenant = horloge()
        attente = quotas.consommer(projet, maintenant, limite=cles.limite(projet),
                                   plafond=reglages.lire()["plafond"])
        if attente is not None:
            raise ErreurApi("quota_jour", [("Retry-After", str(attente))])
        try:
            cle_cache = Cache.cle(moteur.version, format_, "\n".join(prepares))
            son = cache.lire(cle_cache)
            suivi["cache"] = son is not None
            if son is None:
                if not occupe.acquire(blocking=False):
                    raise ErreurApi("voix_occupee", [("Retry-After", "5")])
                try:
                    tache = executeur.submit(fabriquer, [identifiants(p, vocabulaire) for p in prepares],
                                             format_, cle_cache)
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

    def route_synthese(environ, m, suivi):
        suivi["journal"] = True
        return synthese(environ, suivi)

    def route_etat(environ, m, suivi):
        return reponse_json(200, {"service": "voix fon", "version": moteur.version, "modele": "facebook/mms-tts-fon",
                                  "licence": "CC BY-NC 4.0", "pret": moteur.pret()})

    def route_robots(environ, m, suivi):
        return 200, [("Content-Type", "text/plain; charset=utf-8")], b"User-agent: *\nDisallow: /\n"

    def depuis(fonction):
        return lambda environ, m, suivi: fonction(ctx, environ, m)

    # (motif, méthodes acceptées, gestionnaire). Toute adresse absente de cette table donne 404.
    routes = [
        (re.compile(r"/v1/etat"), frozenset({"GET"}), route_etat),
        (re.compile(r"/v1/synthese"), frozenset({"POST"}), route_synthese),
        (re.compile(r"/robots\.txt"), frozenset({"GET"}), route_robots),
        *((motif, methodes, depuis(f)) for motif, methodes, f in publiques.ROUTES),
        *((motif, methodes, depuis(f)) for motif, methodes, f in admin.ROUTES),
    ]

    def traiter(environ, suivi: dict):
        methode = environ.get("REQUEST_METHOD", "GET")
        chemin = environ.get("PATH_INFO", "")
        for motif, methodes, gestionnaire in routes:
            m = motif.fullmatch(chemin)
            if m:
                break
        else:
            raise ErreurApi("introuvable")
        if methode not in methodes:
            raise ErreurApi("methode", [("Allow", ", ".join(sorted(methodes)))])
        if environ.get("HTTP_X_FORWARDED_PROTO", "").lower() == "http":
            # Seulement vers une route connue, avec un hôte vérifié : rien de ce que le client
            # envoie ne peut glisser un retour à la ligne dans l'en-tête Location.
            hote = next((h for h in (environ.get("HTTP_HOST", ""), environ.get("SERVER_NAME", ""))
                         if HOTE.fullmatch(h)), HOTE_PAR_DEFAUT)
            # 308 garde la méthode et le corps d'un POST ; 301 pour une simple lecture.
            return 301 if methode in ("GET", "HEAD") else 308, [("Location", f"https://{hote}{chemin}")], b""
        return gestionnaire(environ, m, suivi)

    def application(environ, start_response):
        debut = time.monotonic()
        suivi = {"journal": False, "projet": None, "caracteres": 0, "format": None, "cache": False}
        try:
            statut, entetes, corps = traiter(environ, suivi)
        except ErreurApi as e:
            statut, entetes, corps = reponse_erreur(e)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            statut, entetes, corps = reponse_erreur(ErreurApi("erreur_interne"))
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
