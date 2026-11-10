"""Routes publiques : demande d'accès, lien d'accès à usage unique, fichiers statiques.

Un GET ne consomme jamais rien : les antivirus de messagerie ouvrent les liens avant la personne.
Seul le POST envoyé par le bouton « Afficher ma clé » crée la clé.
"""

import re

from . import messages
from .demandes import ChampInvalide, DemandesFermees, TropDeDemandes, valider
from .reponses import ErreurApi, reponse_json
from .web import Contexte, controler_post, ip_client, lire_corps_json, page, statique


def page_demande(ctx: Contexte, environ, m):
    return page("demande.html")


def api_demande(ctx: Contexte, environ, m):
    if environ["REQUEST_METHOD"] == "GET":
        return reponse_json(200, {"ouvertes": not ctx.demandes.fermees()})
    controler_post(environ, ctx)
    donnees = lire_corps_json(environ, ctx.config.max_corps)
    if str(donnees.get("site_web") or "").strip():
        return reponse_json(200, {"ok": True})  # champ piège rempli : un robot, ignoré sans le lui dire
    try:
        fiche = valider(donnees)
    except ChampInvalide as e:
        raise ErreurApi("champ_invalide", message=e.message, donnees={"champ": e.champ}) from None
    maintenant = ctx.horloge()
    pris = {p["projet"] for p in ctx.cles.lister(maintenant)}
    try:
        demande = ctx.demandes.deposer(fiche, ip=ip_client(environ), maintenant=maintenant, pris=pris)
    except DemandesFermees:
        raise ErreurApi("demandes_fermees") from None
    except TropDeDemandes:
        raise ErreurApi("trop_de_demandes") from None
    # Seul Elisée est prévenu : aucun e-mail ne part vers l'adresse saisie avant sa décision. L'envoi se
    # fait pendant la requête (voir courriel.py) ; son échec n'empêche pas la réponse.
    sujet, texte = messages.annonce_demande(demande, f"https://{ctx.config.hote}/admin")
    ctx.courriel.envoyer(ctx.reglages.lire()["adresse"], sujet, texte)
    return reponse_json(200, {"ok": True})


def page_acces(ctx: Contexte, environ, m):
    return page("acces.html")


def api_acces(ctx: Contexte, environ, m):
    jeton, maintenant = m["jeton"], ctx.horloge()
    if environ["REQUEST_METHOD"] == "GET":
        return reponse_json(200, {"valide": ctx.cles.lien_valide(jeton, maintenant) is not None})
    controler_post(environ, ctx)
    resultat = ctx.cles.utiliser_lien(jeton, maintenant)
    if resultat is None:
        raise ErreurApi("lien_invalide")
    projet, cle = resultat
    return reponse_json(200, {"projet": projet, "cle": cle, "limite": ctx.cles.limite(projet),
                              "guide": ctx.config.guide})


def fichier_statique(ctx: Contexte, environ, m):
    reponse = statique(m["nom"])
    if reponse is None:
        raise ErreurApi("introuvable")
    return reponse


JETON = r"(?P<jeton>[A-Za-z0-9_-]{43})"
ROUTES = [
    (re.compile(r"/demande"), frozenset({"GET"}), page_demande),
    (re.compile(r"/api/demande"), frozenset({"GET", "POST"}), api_demande),
    (re.compile(rf"/acces/{JETON}"), frozenset({"GET"}), page_acces),
    (re.compile(rf"/api/acces/{JETON}"), frozenset({"GET", "POST"}), api_acces),
    (re.compile(r"/static/(?P<nom>[a-z0-9-]+\.(?:css|js|woff2|svg))"), frozenset({"GET"}), fichier_statique),
]
