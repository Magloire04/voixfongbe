"""Espace d'administration : page /admin et API /api/admin/…, réservées à Elisée.

Toute donnée exige une session valide (cookie __Host-, HttpOnly, Secure, SameSite=Strict), sauf
l'état, la connexion et le mot de passe oublié. Toute action qui modifie exige en plus une page de ce
site (Origin ou Referer) et un corps JSON. Un e-mail qui ne part pas n'annule jamais une décision :
la réponse le dit (courriel_envoye) et « Nouveau lien » permet de renvoyer.
"""

import re
from datetime import date, timedelta
from urllib.parse import parse_qs

from . import messages
from .cles import LIMITE_PAR_DEFAUT, NOM_PROJET
from .connexion import Bloque, PasConfigure, TropDeCodes
from .formats import valider_courriel, valider_limite
from .quotas import FUSEAU
from .reponses import ErreurApi, reponse_json
from .web import Contexte, controler_post, ip_client, lire_cookie, lire_corps_json, page

COOKIE = "__Host-voix-admin"
JOURS_APPELS = 90
MOTIF_MAX = 500


def _ok(**autres):
    return reponse_json(200, {"ok": True, **autres})


def _corps(ctx: Contexte, environ) -> dict:
    controler_post(environ, ctx)
    return lire_corps_json(environ, ctx.config.max_corps)


def _exiger_session(ctx: Contexte, environ) -> None:
    if not ctx.connexion.valide(lire_cookie(environ, COOKIE), ctx.horloge()):
        raise ErreurApi("non_connecte")


def protege(fonction):
    """Session exigée ; pour un POST, l'origine et le type du corps sont contrôlés avant."""
    def gestionnaire(ctx: Contexte, environ, m):
        if environ["REQUEST_METHOD"] == "POST":
            controler_post(environ, ctx)
        _exiger_session(ctx, environ)
        return fonction(ctx, environ, m)
    return gestionnaire


def _envoyer(ctx: Contexte, destinataire: str, sujet_texte: tuple[str, str]) -> bool:
    return ctx.courriel.envoyer(destinataire, *sujet_texte)


def _exiger_envoi(ctx: Contexte) -> None:
    """Avant une action dont l'e-mail est le seul moyen de prévenir la personne : sans boîte d'envoi
    configurée, rien ne change (une « Nouvelle clé » couperait sinon la clé en service sans rien envoyer).
    Un envoi qui échoue une fois configuré, lui, n'annule pas la décision."""
    if not ctx.courriel.configure():
        raise ErreurApi("smtp_absent")


def _lien(ctx: Contexte, jeton: str) -> str:
    return f"https://{ctx.config.hote}/acces/{jeton}"


# Page, état, connexion
def page_admin(ctx: Contexte, environ, m):
    return page("admin.html")


def etat(ctx: Contexte, environ, m):
    return reponse_json(200, {"configure": ctx.connexion.configure(),
                              "connecte": ctx.connexion.valide(lire_cookie(environ, COOKIE), ctx.horloge())})


def connexion(ctx: Contexte, environ, m):
    donnees = _corps(ctx, environ)
    if not ctx.connexion.configure():
        raise ErreurApi("pas_configure")
    mdp = donnees.get("mot_de_passe")
    try:
        jeton = ctx.connexion.ouvrir(mdp if isinstance(mdp, str) else "", ip_client(environ), ctx.horloge())
    except Bloque as e:
        raise ErreurApi("bloque", [("Retry-After", str(e.attente_s))]) from None
    if jeton is None:
        raise ErreurApi("mdp_faux")
    return reponse_json(200, {"ok": True},
                        [("Set-Cookie", f"{COOKIE}={jeton}; Path=/; HttpOnly; Secure; SameSite=Strict")])


def _effacer_cookie():
    return [("Set-Cookie", f"{COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0")]


@protege
def deconnexion(ctx: Contexte, environ, m):
    ctx.connexion.fermer(lire_cookie(environ, COOKIE))
    return reponse_json(200, {"ok": True}, _effacer_cookie())


def oubli(ctx: Contexte, environ, m):
    _corps(ctx, environ)
    if not ctx.courriel.configure():
        raise ErreurApi("smtp_absent")
    try:
        code = ctx.connexion.demander_code(ctx.horloge())
    except PasConfigure:
        raise ErreurApi("pas_configure") from None
    except TropDeCodes as e:
        raise ErreurApi("trop_de_codes", [("Retry-After", str(e.attente_s))]) from None
    envoye = _envoyer(ctx, ctx.reglages.lire()["adresse"], messages.code_oubli(code))
    return _ok(courriel_envoye=envoye)


def oubli_changer(ctx: Contexte, environ, m):
    donnees = _corps(ctx, environ)
    maintenant = ctx.horloge()
    try:
        change = ctx.connexion.changer_avec_code(str(donnees.get("code", "")).strip(), donnees.get("mot_de_passe"),
                                                 maintenant)
    except ValueError:
        raise ErreurApi("mdp_court") from None
    if not change:
        raise ErreurApi("code_faux")
    _envoyer(ctx, ctx.reglages.lire()["adresse"], messages.alerte_mdp(maintenant))
    return reponse_json(200, {"ok": True}, _effacer_cookie())


# Demandes
@protege
def liste_demandes(ctx: Contexte, environ, m):
    return reponse_json(200, {"en_attente": ctx.demandes.en_attente(),
                              "historique": ctx.demandes.historique(ctx.horloge())})


@protege
def decider(ctx: Contexte, environ, m):
    donnees = lire_corps_json(environ, ctx.config.max_corps)
    maintenant = ctx.horloge()
    demande = ctx.demandes.obtenir(m["id"])
    if demande is None:
        raise ErreurApi("demande_inconnue")
    if demande["etat"] != "en_attente":
        raise ErreurApi("deja_decidee")
    _exiger_envoi(ctx)
    if m["action"] == "refuser":
        motif = donnees.get("motif")
        if motif is not None and (not isinstance(motif, str) or len(motif.strip()) > MOTIF_MAX):
            raise ErreurApi("valeur_invalide", message=f"Motif : {MOTIF_MAX} caractères au plus.")
        motif = motif.strip() if motif else None
        try:
            ctx.demandes.marquer_refusee(demande["id"], motif, maintenant)
        except ValueError:
            raise ErreurApi("deja_decidee") from None
        return _ok(courriel_envoye=_envoyer(ctx, demande["courriel"], messages.refus(demande["nom"], motif)))

    projet = donnees.get("projet") or demande["projet_propose"]
    if not isinstance(projet, str) or not NOM_PROJET.fullmatch(projet):
        raise ErreurApi("valeur_invalide", message="Nom de projet : 2 à 40 caractères parmi a-z, 0-9 et le tiret.")
    try:
        limite = valider_limite(donnees.get("limite", LIMITE_PAR_DEFAUT))
    except ValueError as e:
        raise ErreurApi("valeur_invalide", message=f"Limite : {e}.") from None
    try:
        jeton = ctx.cles.preparer(projet, courriel=demande["courriel"], limite=limite, nom=demande["nom"],
                                  organisation=demande["organisation"] or None, maintenant=maintenant)
    except ValueError:
        # Nom pris : peut-être par une approbation de la même demande, faite dans un autre onglet.
        if (ctx.demandes.obtenir(demande["id"]) or {}).get("etat") != "en_attente":
            raise ErreurApi("deja_decidee") from None
        raise ErreurApi("projet_pris") from None
    try:
        ctx.demandes.marquer_approuvee(demande["id"], projet, maintenant)
    except ValueError:
        # Approuvée entre-temps ailleurs (autre onglet, autre processus) : le projet créé ici est en trop.
        ctx.cles.revoquer(projet, maintenant)
        ctx.cles.supprimer(projet)
        raise ErreurApi("deja_decidee") from None
    envoye = _envoyer(ctx, demande["courriel"],
                      messages.acces_accorde(demande["nom"], _lien(ctx, jeton), limite, ctx.config.guide))
    return _ok(courriel_envoye=envoye)


# Projets et limites
@protege
def liste_projets(ctx: Contexte, environ, m):
    maintenant = ctx.horloge()
    plafond = ctx.reglages.lire()["plafond"]
    jour = ctx.quotas.du_jour(maintenant)
    projets = [{**p, "aujourd_hui": jour["projets"].get(p["projet"], 0), "depasse_plafond": p["limite"] > plafond}
               for p in ctx.cles.lister(maintenant)]
    return reponse_json(200, {"plafond": plafond, "total_jour": jour["total"], "projets": projets})


@protege
def agir_projet(ctx: Contexte, environ, m):
    donnees = lire_corps_json(environ, ctx.config.max_corps)
    maintenant = ctx.horloge()
    projet, action = m["projet"], m["action"]
    fiche = next((p for p in ctx.cles.lister(maintenant) if p["projet"] == projet), None)
    if fiche is None:
        raise ErreurApi("projet_inconnu")
    try:
        return _agir(ctx, projet, action, fiche, donnees, maintenant)
    except KeyError:
        # Supprimé entre la lecture et l'action (autre onglet, autre processus).
        raise ErreurApi("projet_inconnu") from None


def _agir(ctx: Contexte, projet: str, action: str, fiche: dict, donnees: dict, maintenant):
    try:
        if action == "limite":
            ctx.cles.changer_limite(projet, donnees.get("limite"))
            return _ok()
        if action == "courriel":
            ctx.cles.changer_courriel(projet, donnees.get("courriel"))
            return _ok()
    except ValueError as e:
        raise ErreurApi("valeur_invalide", message=f"{str(e)[:1].upper()}{str(e)[1:]}.") from None
    if action == "revoquer":
        ctx.cles.revoquer(projet, maintenant)
        return _ok()
    if action == "supprimer":
        if fiche["etat"] != "revoquee":
            raise ErreurApi("etat_incompatible", message="Révoquez le projet avant de le supprimer.")
        try:
            ctx.cles.supprimer(projet)
        except ValueError:  # un nouveau lien ou une clé est arrivé entre-temps
            raise ErreurApi("etat_incompatible", message="Révoquez le projet avant de le supprimer.") from None
        ctx.demandes.effacer_projet(projet)
        return _ok()
    # nouvelle-cle (projet actif ou révoqué) et nouveau-lien (lien en attente ou expiré)
    permis = ("active", "revoquee") if action == "nouvelle-cle" else ("lien_en_attente", "lien_expire")
    if fiche["etat"] not in permis:
        raise ErreurApi("etat_incompatible")
    if not fiche["courriel"]:
        raise ErreurApi("courriel_absent")
    _exiger_envoi(ctx)
    try:
        jeton = ctx.cles.nouveau_lien(projet, maintenant)
    except ValueError:
        raise ErreurApi("courriel_absent") from None
    envoye = _envoyer(ctx, fiche["courriel"],
                      messages.nouveau_lien(fiche["nom"], _lien(ctx, jeton), fiche["limite"], ctx.config.guide))
    return _ok(courriel_envoye=envoye)


# Appels
@protege
def appels(ctx: Contexte, environ, m):
    requete = parse_qs(environ.get("QUERY_STRING", ""))
    aujourd_hui = ctx.horloge().astimezone(FUSEAU).date()
    try:
        jour = date.fromisoformat(requete.get("jour", [aujourd_hui.isoformat()])[0])
        page_ = int(requete.get("page", ["1"])[0])
    except ValueError:
        raise ErreurApi("valeur_invalide", message="Jour ou page invalide.") from None
    if not aujourd_hui - timedelta(days=JOURS_APPELS) <= jour <= aujourd_hui or page_ < 1:
        raise ErreurApi("valeur_invalide", message=f"Jour des {JOURS_APPELS} derniers jours, page à partir de 1.")
    projet = requete.get("projet", [""])[0] or None
    lu = ctx.journal.lire(jour, projet=projet, page=page_)
    return reponse_json(200, {"jour": jour.isoformat(), "jours": ctx.journal.jours_disponibles(aujourd_hui), "projet": projet,
                              "resume": ctx.journal.resume(jour), **lu})


# Réglages
@protege
def reglages(ctx: Contexte, environ, m):
    if environ["REQUEST_METHOD"] == "POST":
        donnees = lire_corps_json(environ, ctx.config.max_corps)
        maintenant = ctx.horloge()
        ancienne = ctx.reglages.lire()["adresse"]
        adresse = donnees.get("adresse")
        try:
            adresse = valider_courriel(adresse) if adresse is not None else None
            plafond = donnees.get("plafond")
            if plafond is not None:
                valider_limite(plafond)
        except ValueError as e:
            raise ErreurApi("valeur_invalide", message=f"{str(e)[:1].upper()}{str(e)[1:]}.") from None
        change_adresse = adresse is not None and adresse != ancienne
        if change_adresse:
            # Cette adresse reçoit les codes de mot de passe oublié : une session volée ne doit pas pouvoir
            # la détourner sans le mot de passe.
            mdp = donnees.get("mot_de_passe")
            try:
                confirme = ctx.connexion.confirmer(mdp if isinstance(mdp, str) else "", ip_client(environ),
                                                   maintenant)
            except Bloque as e:
                raise ErreurApi("bloque", [("Retry-After", str(e.attente_s))]) from None
            if not confirme:
                raise ErreurApi("mdp_faux", message="Mot de passe incorrect : il est demandé pour changer "
                                                    "l'adresse des annonces.")
        ctx.reglages.modifier(adresse=adresse, plafond=plafond)
        if change_adresse:
            _envoyer(ctx, ancienne, messages.alerte_adresse(adresse, maintenant))
        return _ok()
    r = ctx.reglages.lire()
    return reponse_json(200, {"adresse": r["adresse"], "plafond": r["plafond"],
                              "smtp": {"configure": ctx.courriel.configure()},
                              "voix": {"pret": ctx.moteur.pret(), "version": ctx.moteur.version}})


@protege
def essai(ctx: Contexte, environ, m):
    if not ctx.courriel.configure():
        raise ErreurApi("smtp_absent")
    return _ok(courriel_envoye=_envoyer(ctx, ctx.reglages.lire()["adresse"], messages.essai()))


GET, POST = frozenset({"GET"}), frozenset({"POST"})
ROUTES = [
    (re.compile(r"/admin"), GET, page_admin),
    (re.compile(r"/api/admin/etat"), GET, etat),
    (re.compile(r"/api/admin/connexion"), POST, connexion),
    (re.compile(r"/api/admin/deconnexion"), POST, deconnexion),
    (re.compile(r"/api/admin/oubli"), POST, oubli),
    (re.compile(r"/api/admin/oubli/changer"), POST, oubli_changer),
    (re.compile(r"/api/admin/demandes"), GET, liste_demandes),
    (re.compile(r"/api/admin/demandes/(?P<id>[0-9a-f]{16})/(?P<action>approuver|refuser)"), POST, decider),
    (re.compile(r"/api/admin/projets"), GET, liste_projets),
    (re.compile(r"/api/admin/projets/(?P<projet>[a-z0-9-]{2,40})/"
                r"(?P<action>limite|courriel|revoquer|nouvelle-cle|nouveau-lien|supprimer)"), POST, agir_projet),
    (re.compile(r"/api/admin/appels"), GET, appels),
    (re.compile(r"/api/admin/reglages"), frozenset({"GET", "POST"}), reglages),
    (re.compile(r"/api/admin/reglages/essai"), POST, essai),
]
