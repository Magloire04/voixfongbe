"""Réponses JSON et erreurs de l'API : un code stable, un statut HTTP, un message en français."""

import json

MESSAGES = {
    # API de la voix
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
    # Pages, demandes d'accès et espace admin
    "origine": (403, "Demande refusée : elle doit venir d'une page de voix.bytechnum.com."),
    "type_contenu": (415, "Le corps doit être envoyé en JSON (Content-Type: application/json)."),
    "champ_invalide": (400, "Un champ du formulaire est mal rempli."),
    "trop_de_demandes": (429, "Trois demandes au plus par jour depuis la même connexion. Réessayez demain."),
    "demandes_fermees": (503, "Les demandes sont momentanément fermées. Réessayez dans quelques jours."),
    "lien_invalide": (410, "Ce lien a expiré ou a déjà servi. Pour en recevoir un nouveau, écrivez à "
                           "technum.services@bytechnum.com."),
    "non_connecte": (401, "Session terminée : reconnectez-vous."),
    "mdp_faux": (401, "Mot de passe incorrect."),
    "bloque": (429, "Trop d'essais. Réessayez dans 10 minutes."),
    "pas_configure": (503, "Le mot de passe de l'espace admin n'est pas encore défini (voir EXPLOITATION.md)."),
    "trop_de_codes": (429, "Un code a déjà été envoyé il y a peu. Réessayez plus tard."),
    "code_faux": (400, "Code incorrect ou expiré."),
    "mdp_court": (400, "Le mot de passe doit faire au moins 12 caractères."),
    "valeur_invalide": (400, "Valeur invalide."),
    "projet_pris": (409, "Ce nom de projet est déjà pris : choisissez-en un autre."),
    "projet_inconnu": (404, "Projet inconnu."),
    "demande_inconnue": (404, "Demande inconnue."),
    "deja_decidee": (409, "Cette demande a déjà été traitée."),
    "etat_incompatible": (409, "Action impossible dans l'état actuel du projet."),
    "courriel_absent": (400, "Ce projet n'a pas d'adresse e-mail : saisissez-la d'abord."),
    "smtp_absent": (503, "L'envoi d'e-mails n'est pas configuré (voir EXPLOITATION.md)."),
}


class ErreurApi(Exception):
    def __init__(self, code: str, entetes: list[tuple[str, str]] | None = None, *, message: str | None = None,
                 donnees: dict | None = None):
        super().__init__(code)
        self.code = code
        self.statut = MESSAGES[code][0]
        self.entetes = entetes or []
        self.message = message or MESSAGES[code][1]
        self.donnees = donnees or {}


def reponse_json(statut: int, donnees, entetes=None):
    corps = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
    return statut, [("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store"),
                    *(entetes or [])], corps


def reponse_erreur(e: ErreurApi):
    return reponse_json(e.statut, {"erreur": e.message, "code": e.code, **e.donnees}, e.entetes)
