# Espace d'administration et demandes de clé : plan de réalisation

> **Pour l'exécutant :** suivre superpowers:executing-plans (ou superpowers:subagent-driven-development) tâche par tâche. Les étapes sont des cases à cocher.

**But :** ajouter au service de voix une page publique de demande d'accès, un lien à usage unique qui affiche la clé, et un espace `/admin` réservé à Elisée (demandes, projets et limites, appels, réglages), pour que l'usage courant ne demande plus de terminal.

**Architecture :** même application WSGI. De nouveaux modules à responsabilité unique (réglages, demandes, envoi d'e-mails, textes des e-mails, connexion) suivent le modèle des modules existants : fichiers JSON sous `verrou()`, heure fournie par `horloge`. Deux modules de routes (`publiques.py`, `admin.py`) reçoivent un `Contexte` commun ; `app.py` garde le contrôle des routes, des méthodes et de HTTPS. Les pages sont des fichiers HTML, CSS et JS statiques rangés dans `voixfongbe/web/`, servis par l'application, qui parlent à l'API en JSON.

**Outils :** Python 3.13 (serveur) et 3.14 (tests sur le PC, `.venv`) ; bibliothèque standard seulement (`smtplib`, `ssl`, `email`, `hashlib.scrypt`, `secrets`, `hmac`) ; tests `unittest` ; Playwright pour regarder les pages.

**Conception :** `docs/superpowers/specs/2026-11-09-espace-admin-design.md` (elle fait foi), qui s'appuie sur `docs/superpowers/specs/2026-11-09-voix-fon-design.md`.

## Contraintes globales

- Aucune nouvelle dépendance : `requirements.txt` ne change pas.
- Code compatible Python 3.13 et 3.14. Identifiants en français. Textes visibles en français, sans détail technique.
- Stockage : JSON écrits par `ecrire_json` (atomique, droits 600). Toute lecture suivie d'une écriture se fait sous `verrou()`, car plusieurs processus Passenger tournent en même temps.
- Aucun dossier `public/` : pages, feuilles de style, scripts et polices passent par des routes de l'application.
- Rien de secret en clair sur le disque ni dans un e-mail : ni clé d'API, ni jeton de lien, ni jeton de session, ni code de mot de passe oublié, ni mot de passe. Seules les empreintes sont gardées, comparées par `hmac.compare_digest`. L'adresse IP n'est gardée que sous forme d'empreinte.
- Valeurs de la conception :
  - demande : description de 20 à 1 000 caractères ; 3 demandes par jour et par IP (dernière entrée de `X-Forwarded-For`) ; 50 demandes en attente au plus ; refusées effacées après 90 jours ;
  - accès : jeton de 32 octets valable 7 jours ; limite par projet de 1 à 1 000 000, 100 par défaut ; plafond commun de 300 par défaut ;
  - connexion : mot de passe de 12 caractères au moins, scrypt ; session fermée après 10 minutes sans activité ; 3 mots de passe faux par IP donnent 10 minutes de blocage ; code de 8 chiffres valable 10 minutes, 5 essais, 1 envoi par 10 minutes et 3 par jour ;
  - appels : journal sur 90 jours, 50 lignes par page.
- Adresses : annonces et codes vers `eliseeatonde@gmail.com` par défaut (réglable) ; contact public `technum.services@bytechnum.com` ; guide `https://github.com/Magloire04/voixfongbe#readme` ; hôte `voix.bytechnum.com`.
- Mention de licence, mot pour mot : « Voix : MMS-TTS de Meta (CC BY-NC 4.0) ».
- La clé de `projet-collegue` (fichier des clés à l'ancien format) doit continuer de marcher.
- Git : branche `feature/espace-admin`. Messages au nom d'Elisée seul, sans aucune trace d'outil d'IA. Elisée fusionne. Rien n'est poussé ni déployé sans son accord explicite.
- Tests : `.venv/Scripts/python -m unittest discover -s tests -t .` (aujourd'hui : 99 réussis, 1 ignoré sous Windows). Une tâche n'est finie que si toute la suite passe.

## Points de vigilance de la relecture

Cas que la conception implique sans les nommer. Chacun a son test dans la tâche indiquée.

1. L'antivirus d'une messagerie ouvre le lien d'accès (GET de la page et de l'API) avant la personne : rien n'est consommé, et la clé s'affiche quand même au clic (tâche 7).
2. Après la mise à jour, `cles.json` est encore à l'ancien format (`{"empreinte", "cree_le"}`) : la clé de `projet-collegue` marche, avec une limite de 100 (tâches 1 et 2).
3. Elisée clique deux fois sur « Approuver », ou approuve dans deux onglets : un seul projet, un seul e-mail, et la seconde réponse dit que la demande est déjà traitée (tâches 3 et 8).
4. La boîte d'envoi est en panne au moment d'approuver : la décision reste, l'écran dit que l'e-mail n'est pas parti, « Nouveau lien » le renvoie, et l'ancien lien ne marche plus (tâche 8).
5. Un demandeur glisse des balises HTML ou des retours à la ligne dans ses champs : rien ne s'exécute dans l'espace admin (texte affiché tel quel) et rien ne s'ajoute aux en-têtes d'un e-mail (tâches 3, 4 et 9).

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `voixfongbe/formats.py` (nouveau) | contrôle d'une adresse e-mail et d'une limite |
| `voixfongbe/cles.py` | projets : clé, lien d'accès, limite, adresse, état |
| `voixfongbe/reglages.py` (nouveau) | adresse des annonces, plafond commun |
| `voixfongbe/quotas.py` | limite et plafond passés à chaque appel, décompte du jour |
| `voixfongbe/demandes.py` (nouveau) | demandes d'accès : contrôle, anti-abus, nom de projet, décisions, effacement |
| `voixfongbe/courriel.py` (nouveau) | envoi SMTP sur TLS (465) |
| `voixfongbe/messages.py` (nouveau) | sujets et textes des e-mails |
| `voixfongbe/connexion.py` (nouveau) | mot de passe, sessions, blocage, code de mot de passe oublié |
| `voixfongbe/journal.py` | lecture du journal pour l'onglet Appels |
| `voixfongbe/reponses.py` (nouveau) | `ErreurApi`, messages d'erreur, réponses JSON (sortis de `app.py`) |
| `voixfongbe/web.py` (nouveau) | `Contexte`, IP, même origine, cookie, en-têtes des pages, fichiers statiques |
| `voixfongbe/publiques.py` (nouveau) | `/demande`, `/api/demande`, `/acces/…`, `/api/acces/…`, `/static/…` |
| `voixfongbe/admin.py` (nouveau) | `/admin` et `/api/admin/…` |
| `voixfongbe/app.py`, `voixfongbe/config.py` | table des routes, contexte, nouveaux réglages |
| `voixfongbe/web/` (nouveau) | `demande.html`, `acces.html`, `admin.html`, `style.css`, `demande.js`, `acces.js`, `admin.js`, polices Montserrat `woff2`, `OFL.txt` |
| `scripts/admin.py` (nouveau), `scripts/cles.py`, `scripts/essai_local.py` (nouveau), `scripts/deployer.sh` | SSH : mot de passe et SMTP ; clés ; essai sur le PC ; contrôle après déploiement |
| `tests/aides.py` | `CourrielFactice`, `ORIGINE`, `appeler(..., requete=)` |
| `tests/test_*.py` | un fichier de tests par module |
| `README.md`, `EXPLOITATION.md`, `.gitattributes` | documents ; `*.woff2 binary` |

---

### Tâche 0 : branche et documents

- [ ] **Étape 1 :** dans `C:\wamp64\www\voixfongbe`, sur `main` à jour (`3a3f5a9`), créer la branche `feature/espace-admin`.
- [ ] **Étape 2 :** commit de la conception et de ce plan : `docs: add design and plan for the admin space`.

### Tâche 1 : projets, liens d'accès et limites dans le fichier des clés

**Fichiers :** créer `voixfongbe/formats.py`, `tests/test_formats.py` ; modifier `voixfongbe/cles.py`, `tests/test_cles.py`.

**Produit :**
- `formats.LIMITE_MAX = 1_000_000` ; `formats.valider_courriel(valeur) -> str` (retire les blancs aux bouts ; 254 caractères au plus ; motif `[A-Za-z0-9._%+-]{1,64}@(?:[A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,24}` en entier ; sinon `ValueError`) ; `formats.valider_limite(valeur) -> int` (un `int` qui n'est pas un `bool`, de 1 à `LIMITE_MAX`, sinon `ValueError`).
- `cles.LIMITE_PAR_DEFAUT = 100`, `cles.DUREE_LIEN = timedelta(days=7)`.
- Fiche d'un projet dans `cles.json` : `{"empreinte": str|None, "cree_le": iso, "limite": int, "courriel": str|None, "nom": str|None, "organisation": str|None, "revoquee_le": iso|None, "lien": {"empreinte": str, "expire_le": iso}|None}`. Une clé absente prend sa valeur par défaut : c'est la migration de l'ancien format.
- États (calculés, jamais stockés) : `"active"` (une empreinte de clé), `"lien_en_attente"`, `"lien_expire"`, `"revoquee"`.
- Méthodes de `Cles` (heures en UTC ; `maintenant` facultatif, l'heure actuelle par défaut) :
  - `creer(projet, maintenant=None) -> str` : SSH ; refuse un projet qui a déjà une clé active ; un projet révoqué ou en attente reçoit une clé, et son lien est annulé ;
  - `verifier(cle) -> str | None` : ignore les projets sans clé ;
  - `revoquer(projet, maintenant=None) -> bool` : garde la fiche, efface l'empreinte et le lien, note `revoquee_le` ; `False` si le projet est inconnu ou déjà révoqué ;
  - `preparer(projet, *, courriel, limite=100, nom=None, organisation=None, maintenant) -> str` : crée un projet sans clé, avec un lien ; rend le jeton (`secrets.token_urlsafe(32)`, 43 caractères) ; `ValueError` si le nom est invalide ou pris ;
  - `nouveau_lien(projet, maintenant) -> str` : efface la clé actuelle et `revoquee_le`, crée un nouveau jeton ; `ValueError` si le projet n'a pas d'adresse ;
  - `lien_valide(jeton, maintenant) -> str | None` : ne consomme rien ;
  - `utiliser_lien(jeton, maintenant) -> tuple[str, str] | None` : crée la clé, efface le lien, rend `(projet, clé)` une seule fois ;
  - `supprimer(projet) -> bool` : `ValueError` si le projet n'est pas révoqué ;
  - `changer_limite(projet, limite)`, `changer_courriel(projet, courriel)` : passent par `formats` ; `KeyError` si le projet est inconnu ;
  - `limite(projet) -> int` : `LIMITE_PAR_DEFAUT` si le projet a disparu entre-temps ;
  - `lister(maintenant=None) -> list[dict]` : clés `projet, cree_le, limite, courriel, nom, organisation, etat, lien_expire_le`, jamais une empreinte.
- `verifier`, `lien_valide` et `utiliser_lien` parcourent toutes les fiches et comparent par `hmac.compare_digest`, comme aujourd'hui.

- [ ] **Étape 1 :** écrire les tests. `T = datetime(2026, 11, 9, 22, 30, tzinfo=FUSEAU)`.

```python
def test_ancien_format_reste_valable(self):  # point de vigilance 2
    self.chemin.write_text(json.dumps({"projets": {"projet-collegue": {
        "empreinte": hashlib.sha256(b"cle-ancienne").hexdigest(), "cree_le": "2026-11-09T12:00:00+00:00"}}}))
    cles = Cles(self.chemin)
    self.assertEqual(cles.verifier("cle-ancienne"), "projet-collegue")
    self.assertEqual(cles.limite("projet-collegue"), 100)
    self.assertEqual(cles.lister(T)[0]["etat"], "active")

def test_lien_utilise_une_seule_fois(self):
    jeton = self.cles.preparer("alpha", courriel="koffi@exemple.bj", maintenant=T)
    self.assertEqual(len(jeton), 43)
    self.assertEqual(self.cles.lien_valide(jeton, T), "alpha")
    projet, cle = self.cles.utiliser_lien(jeton, T)
    self.assertEqual((projet, self.cles.verifier(cle)), ("alpha", "alpha"))
    self.assertIsNone(self.cles.utiliser_lien(jeton, T))
    contenu = self.chemin.read_text(encoding="utf-8")
    self.assertNotIn(jeton, contenu)
    self.assertNotIn(cle, contenu)
```

Autres tests, assertions à écrire :
- `test_lien_expire_apres_7_jours` : valide à `T + 7 j - 1 s` ; `lien_valide` et `utiliser_lien` rendent `None` à `T + 7 j + 1 s` ; état `"lien_expire"`.
- `test_nouveau_lien_revoque_la_cle_actuelle` : après `utiliser_lien` puis `nouveau_lien`, l'ancienne clé ne vérifie plus, l'ancien jeton non plus, le nouveau donne une clé.
- `test_nouveau_lien_sans_adresse_refuse` : projet créé par `creer` puis `nouveau_lien` : `ValueError`.
- `test_revoquer_annule_le_lien_en_attente` : `preparer`, `revoquer` : `lien_valide` rend `None`, état `"revoquee"`, la fiche reste dans `lister`.
- `test_supprimer_seulement_un_projet_revoque` : `supprimer` d'un projet actif lève `ValueError` ; après `revoquer`, il rend `True` et `lister()` est vide.
- `test_creer_en_ssh_reactive_un_projet_revoque` : `creer`, `revoquer`, `creer` : la nouvelle clé vérifie.
- `test_limite_bornee` : `changer_limite` à `0`, `1_000_001`, `True`, `"100"`, `2.5` lève `ValueError` ; `1_000_000` passe et `limite()` le rend.
- `test_preparer_nom_pris_refuse` : `ValueError` sur un projet existant.
- `tests/test_formats.py` : `test_courriel_valide` accepte `koffi@exemple.bj` ; refuse `a@b`, `<a@b.bj>`, `x@y.bj\r\nBcc: z@w.bj`, une adresse de 255 caractères.
- Modifier `test_lister_donne_projets_et_dates_sans_empreinte` : l'ensemble des clés devient celui de `lister` ci-dessus, toujours sans `"empreinte"`.
- [ ] **Étape 2 :** lancer `.venv/Scripts/python -m unittest tests.test_cles tests.test_formats -v`. Attendu : échecs (`preparer`, `formats` inconnus).
- [ ] **Étape 3 :** écrire `formats.py` et modifier `cles.py`.
- [ ] **Étape 4 :** relancer, puis toute la suite. Attendu : tout passe.
- [ ] **Étape 5 :** commit `feat(keys): track projects, access links and per-project limits`.

### Tâche 2 : plafond commun réglable et limite du projet appliquée par l'API

**Fichiers :** créer `voixfongbe/reglages.py`, `tests/test_reglages.py` ; modifier `voixfongbe/quotas.py`, `voixfongbe/config.py`, `voixfongbe/app.py`, `tests/test_quotas.py`, `tests/test_app.py`.

**Consomme :** `Cles.limite`, `Cles.changer_limite` (tâche 1).

**Produit :**
- `Reglages(chemin, adresse_defaut: str, plafond_defaut: int)` : `lire() -> {"adresse": str, "plafond": int}` (valeurs par défaut si le fichier manque) ; `modifier(*, adresse=None, plafond=None)` : contrôle par `formats`, `ValueError` sinon, écriture sous verrou.
- `Quotas.consommer(projet, maintenant, limite=None, plafond=None) -> int | None` : sans argument, les valeurs du constructeur (les tests actuels ne changent pas).
- `Quotas.du_jour(maintenant) -> {"total": int, "projets": dict[str, int]}` : zéros si le fichier est d'un autre jour.
- `Config` : nouveaux champs `hote: str = "voix.bytechnum.com"` (variable `VOIX_HOTE`), `adresse_annonces: str = "eliseeatonde@gmail.com"`, `guide: str = "https://github.com/Magloire04/voixfongbe#readme"`.
- `app.py` : `reglages = Reglages(stockage / "reglages.json", config.adresse_annonces, config.total_jour)` ; dans `synthese`, `quotas.consommer(projet, maintenant, limite=cles.limite(projet), plafond=reglages.lire()["plafond"])`.

- [ ] **Étape 1 :** écrire les tests :
  - `test_reglages_par_defaut` : `lire() == {"adresse": "eliseeatonde@gmail.com", "plafond": 300}`.
  - `test_reglages_modifies_et_controles` : `modifier(plafond=0)` et `modifier(adresse="pas-une-adresse")` lèvent `ValueError` ; `modifier(plafond=500)` est relu par une nouvelle instance.
  - `test_limite_passee_a_l_appel` : `consommer(..., limite=2)` : la troisième demande rend une attente.
  - `test_du_jour` : deux demandes de `a`, une de `b` donnent `{"total": 3, "projets": {"a": 2, "b": 1}}` ; le lendemain, `{"total": 0, "projets": {}}`.
  - Dans `test_app.py` :
    - `test_limite_du_projet_appliquee` : `changer_limite("demo", 1)` : premier appel 200, deuxième 429 `quota_jour` ;
    - `test_plafond_commun_des_reglages` : `Reglages.modifier(plafond=1)` : un deuxième projet reçoit 429 ;
    - `test_limite_baissee_sous_le_compte_du_jour` : deux appels, puis `changer_limite("demo", 1)` : le suivant reçoit 429 ;
    - `test_cle_a_l_ancien_format_marche` (point de vigilance 2) : `cles.json` écrit à l'ancien format, l'appel rend 200.
- [ ] **Étape 2 :** lancer `.venv/Scripts/python -m unittest tests.test_reglages tests.test_quotas tests.test_app -v`. Attendu : échecs.
- [ ] **Étape 3 :** écrire `reglages.py`, modifier `quotas.py`, `config.py` et `app.py`.
- [ ] **Étape 4 :** relancer, puis toute la suite. Attendu : tout passe.
- [ ] **Étape 5 :** commit `feat(quotas): apply each project's own limit and an adjustable shared ceiling`.

### Tâche 3 : demandes d'accès

**Fichiers :** créer `voixfongbe/demandes.py`, `tests/test_demandes.py`.

**Consomme :** `formats.valider_courriel`, `cles.NOM_PROJET`, `quotas.FUSEAU`.

**Produit :**
- `class ChampInvalide(ValueError)` avec `champ: str` et `message: str` (français, pour l'écran) ; `class DemandesFermees(Exception)` ; `class TropDeDemandes(Exception)`.
- `valider(donnees: dict) -> dict` : rend `{"nom", "courriel", "organisation", "description"}` sans blancs aux bouts. Règles :
  - `nom` de 2 à 100 caractères, `organisation` de 0 à 120, `description` de 20 à 1 000 ;
  - `nom`, `courriel` et `organisation` refusés s'ils contiennent un caractère de contrôle (dont CR et LF) ; `description` garde `\n` et retire les autres caractères de contrôle ;
  - `accord` doit valoir exactement `True`, sinon `ChampInvalide("accord", ...)` ;
  - chaque valeur doit être une chaîne (`organisation` peut manquer) ;
  - les balises restent telles quelles, car l'affichage les montre en texte.
- `proposer_nom(nom: str, organisation: str, pris: set[str]) -> str` : part de l'organisation si elle est remplie, sinon du nom ; minuscules ; lettres fon translittérées (`ɖ→d, ɔ→o, ɛ→e, ŋ→n, ƒ→f, ʋ→v, ɣ→g, đ→d`) ; accents retirés (NFD) ; tout autre caractère devient `-` ; tirets regroupés et retirés aux bouts ; 40 caractères au plus ; `"projet"` s'il reste moins de 2 caractères ; si le nom est pris, suffixe `-2`, `-3`… en raccourcissant la base pour rester sous 40. Le résultat respecte toujours `NOM_PROJET`.
- `Demandes(chemin, max_en_attente=50, par_ip=3, jours_refus=90)`, fichier `{"demandes": {id: fiche}, "ip": {"jour": iso, "n": {empreinte: int}}}`. Fiche : `id` (`secrets.token_hex(8)`), `nom`, `courriel`, `organisation`, `description`, `projet_propose`, `recue_le`, `etat` (`"en_attente" | "approuvee" | "refusee"`), `decidee_le`, `motif`, `projet`. Méthodes :
  - `deposer(fiche: dict, *, ip: str, maintenant, pris: set[str]) -> dict` : enregistre la fiche avec `projet_propose = proposer_nom(nom, organisation, pris)` et la rend ; lève `DemandesFermees` à 50 en attente, `TropDeDemandes` à la quatrième demande du jour (de Porto-Novo) pour la même IP ; l'IP n'est gardée que par l'empreinte SHA-256, remise à zéro chaque jour ; purge les refusées anciennes ;
  - `fermees() -> bool` ;
  - `obtenir(id) -> dict | None` ;
  - `en_attente() -> list[dict]` (plus anciennes d'abord) et `historique(maintenant) -> list[dict]` (décidées, plus récentes d'abord ; purge d'abord) ;
  - `marquer_approuvee(id, projet, maintenant)` et `marquer_refusee(id, motif: str | None, maintenant)` : `KeyError` si l'id est inconnu, `ValueError` si la demande est déjà décidée ;
  - `purger(maintenant)` : efface les refusées décidées il y a plus de 90 jours ;
  - `effacer_projet(projet)` : efface les demandes approuvées liées à ce projet.

- [ ] **Étape 1 :** écrire les tests :
  - `test_valider_retire_les_blancs` ;
  - `test_longueurs` : description de 19 et de 1 001 caractères, nom vide, organisation de 121 caractères : `ChampInvalide` avec le bon `champ` ;
  - `test_accord_obligatoire` : `False`, `"true"` ou absent donnent `ChampInvalide("accord")` ;
  - `test_retour_a_la_ligne_refuse_dans_les_champs_d_une_ligne` (point de vigilance 5) : nom `"Koffi\r\nBcc: x@y.bj"` et courriel `"k@exemple.bj\nBcc: x@y.bj"` sont refusés ; une description sur deux lignes passe ;
  - `test_balises_gardees_en_texte` : nom `"<img src=x onerror=alert(1)>"` est rendu à l'identique par `valider` ;
  - `test_proposer_nom` :

```python
self.assertEqual(proposer_nom("Koffi A.", "Université d'Abomey-Calavi", set()), "universite-d-abomey-calavi")
self.assertEqual(proposer_nom("Ɖokpɔ́ Sɛ́", "", set()), "dokpo-se")
self.assertEqual(proposer_nom("Alpha", "", {"alpha", "alpha-2"}), "alpha-3")
self.assertEqual(proposer_nom("李雷", "", {"projet"}), "projet-2")
long = proposer_nom("x", "Organisation " * 6, {proposer_nom("x", "Organisation " * 6, set())})
self.assertRegex(long, r"^[a-z0-9-]{2,40}$")
self.assertTrue(long.endswith("-2"))
```

  - `test_trois_demandes_par_ip_et_par_jour` : la quatrième de `203.0.113.7` lève `TropDeDemandes` ; une autre IP passe ; le lendemain, la même IP repasse ;
  - `test_ip_jamais_en_clair` : `"203.0.113.7"` n'est pas dans le fichier ;
  - `test_fermees_a_50_en_attente` : `fermees()` vaut `True` et `deposer` lève `DemandesFermees` ;
  - `test_decision_unique` (point de vigilance 3) : `marquer_approuvee` puis `marquer_approuvee` ou `marquer_refusee` lèvent `ValueError` ;
  - `test_refusees_effacees_apres_90_jours` : refusée à `T`, absente de `historique(T + 91 j)` ; une approuvée à `T` y reste ;
  - `test_effacer_projet` : une demande approuvée pour `alpha` disparaît.
- [ ] **Étape 2 :** lancer `.venv/Scripts/python -m unittest tests.test_demandes -v`. Attendu : échec à l'import.
- [ ] **Étape 3 :** écrire `demandes.py`.
- [ ] **Étape 4 :** relancer, puis toute la suite. Attendu : tout passe.
- [ ] **Étape 5 :** commit `feat(requests): store access requests with abuse limits and project names`.

### Tâche 4 : envoi des e-mails et textes des messages

**Fichiers :** créer `voixfongbe/courriel.py`, `voixfongbe/messages.py`, `tests/test_courriel.py`, `tests/test_messages.py` ; modifier `tests/aides.py`.

**Produit :**
- `courriel.ecrire_reglages(chemin, *, hote, port, utilisateur, mot_de_passe, expediteur)` : écrit `smtp.json` par `ecrire_json` (droits 600).
- `Courriel(chemin: Path, transport=None)` :
  - `configure() -> bool` : `smtp.json` existe et contient les cinq clés ;
  - `envoyer(destinataire, sujet, texte) -> bool` : construit un `EmailMessage` (`From: "Voix fon" <expediteur>` par `formataddr`, `To`, `Subject`, `Date`, `Message-ID` sur `bytechnum.com`, corps `text/plain` en UTF-8), l'envoie et rend `True` ;
  - rend `False` sans lever si l'envoi n'est pas configuré, si le message ne se construit pas (`ValueError` d'un en-tête avec retour à la ligne) ou si le transport échoue (`smtplib.SMTPException`, `OSError`). L'échec est écrit sur `stderr` par son seul type d'exception, sans identifiant ni mot de passe ;
  - le transport par défaut, `_smtp_ssl(message, reglages)`, ouvre `smtplib.SMTP_SSL(hote, port, context=ssl.create_default_context(), timeout=20)`, puis `login(utilisateur, mot_de_passe)` et `send_message(message)`.
- `messages.py`, fonctions qui rendent `(sujet, texte)` en français et en texte simple :
  - `annonce_demande(demande: dict, lien_admin: str)` : nom, adresse, organisation, description, lien de l'admin ;
  - `acces_accorde(nom, lien, limite, guide)` : lien d'accès, validité de 7 jours, affichage unique de la clé, guide, « {limite} demandes par jour », la mention de licence, la consigne de ranger la clé côté serveur ;
  - `refus(nom, motif: str | None)` : poli, avec le motif s'il y en a un ;
  - `nouveau_lien(nom, lien, limite, guide)` : comme `acces_accorde`, et dit que l'ancienne clé éventuelle ne marche plus ;
  - `code_oubli(code)` : le code et « 10 minutes » ;
  - `alerte_mdp(quand: datetime)` : date et heure de Porto-Novo ;
  - `essai()`.
- `tests/aides.py` : `CourrielFactice` avec `envoyes: list[dict]` (clés `a`, `sujet`, `texte`), `en_panne = False`, `configure_ = True`, `configure()`, et `envoyer()` qui note le message et rend `True`, ou rend `False` sans rien noter s'il est en panne.

- [ ] **Étape 1 :** écrire les tests :
  - `test_non_configure_n_envoie_rien` : pas de `smtp.json` : `configure()` vaut `False`, `envoyer` rend `False` et le transport n'est pas appelé ;
  - `test_message_construit` : le transport reçoit un message dont `From` vaut `Voix fon <envoi@bytechnum.com>`, avec le bon `To`, et un corps qui garde `ɔ` intact ;
  - `test_echec_rend_false_sans_secret` : le transport lève `smtplib.SMTPAuthenticationError` : `False`, et le `stderr` capturé ne contient pas le mot de passe ;
  - `test_transport_par_defaut_en_tls_465` : avec `smtplib.SMTP_SSL` remplacé par `unittest.mock`, l'appel se fait avec `("mail.spacemail.com", 465)`, `timeout=20` et un contexte qui a `check_hostname` à `True` et `verify_mode == ssl.CERT_REQUIRED` ; `login` reçoit l'utilisateur et le mot de passe ;
  - `test_entete_avec_retour_a_la_ligne_refuse` (point de vigilance 5) : `envoyer("a@b.bj\r\nBcc: x@y.bj", ...)` rend `False` et le transport n'est pas appelé ;
  - `test_reglages_smtp_en_droits_600` : ignoré sous Windows ;
  - `test_acces_accorde` : contient le lien, le guide, `"100 demandes par jour"`, `"Voix : MMS-TTS de Meta (CC BY-NC 4.0)"`, `"7 jours"` ;
  - `test_refus_avec_et_sans_motif` ;
  - `test_annonce_sans_lien_d_acces` : contient `https://voix.bytechnum.com/admin` et pas `/acces/` ;
  - `test_code_oubli` : contient le code et `"10 minutes"`.
- [ ] **Étape 2 :** lancer `.venv/Scripts/python -m unittest tests.test_courriel tests.test_messages -v`. Attendu : échec à l'import.
- [ ] **Étape 3 :** écrire `courriel.py`, `messages.py`, puis `CourrielFactice`.
- [ ] **Étape 4 :** relancer, puis toute la suite. Attendu : tout passe.
- [ ] **Étape 5 :** commit `feat(mail): send plain-text mails over smtp tls and write their texts`.

### Tâche 5 : connexion de l'administrateur

**Fichiers :** créer `voixfongbe/connexion.py`, `tests/test_connexion.py`.

**Produit :**
- `empreinte_mdp(mdp) -> str` au format d'AgriFon `scrypt:<sel, 32 hex>:<128 hex>` (`hashlib.scrypt(n=16384, r=8, p=1, dklen=64)`, les réglages par défaut de Node) ; `mdp_correct(mdp, empreinte) -> bool`.
- Exceptions : `Bloque(attente_s: int)`, `TropDeCodes(attente_s: int)`, `PasConfigure`.
- `Connexion(chemin)`, fichier `admin.json` : empreinte du mot de passe ; sessions (empreinte SHA-256 du jeton et dernière activité) ; échecs par empreinte d'IP ; code en cours (empreinte salée, expiration, essais restants) ; envois de codes du jour. Méthodes :
  - `configure() -> bool` ;
  - `definir_mdp(mdp, maintenant)` : `ValueError` sous 12 caractères ; ferme toutes les sessions ; efface le code en cours ;
  - `ouvrir(mdp, ip, maintenant) -> str | None` : lève `Bloque` si l'IP est bloquée (avant tout contrôle du mot de passe) ; `None` si le mot de passe est faux ou pas encore défini ; le troisième échec bloque l'IP 10 minutes ; un succès remet son compteur à zéro ; rend un jeton `secrets.token_urlsafe(32)` ;
  - `valide(jeton, maintenant) -> bool` : `False` après 10 minutes sans activité ; sinon prolonge la session et purge les sessions mortes ;
  - `fermer(jeton)` ;
  - `demander_code(maintenant) -> str` : 8 chiffres (`secrets.randbelow`, zéros en tête gardés) ; lève `PasConfigure` sans mot de passe, `TropDeCodes` si un code est parti il y a moins de 10 minutes ou si 3 codes sont déjà partis ce jour (de Porto-Novo) ;
  - `changer_avec_code(code, nouveau, maintenant) -> bool` : `ValueError` sous 12 caractères ; `False` si le code est faux, expiré ou épuisé (5 essais) ; sinon appelle `definir_mdp` et rend `True`.

- [ ] **Étape 1 :** écrire les tests :
  - `test_format_d_empreinte` : correspond à `^scrypt:[0-9a-f]{32}:[0-9a-f]{128}$` ; `mdp_correct` est juste et refuse un autre mot de passe ;
  - `test_mdp_trop_court` : 11 caractères lèvent `ValueError` ;
  - `test_session_ouverte_et_jeton_absent_du_fichier` ;
  - `test_session_expire_apres_10_minutes_sans_activite` : `valide` à `T + 9 min` prolonge, donc `T + 18 min` est encore valide ; 10 min 01 s après la dernière activité, c'est fini ;
  - `test_sessions_partagees_entre_instances` : ouverte par une instance, valide pour une autre sur le même fichier (deux processus) ;
  - `test_trois_echecs_bloquent_l_ip_10_minutes` : après 3 échecs, même le bon mot de passe lève `Bloque` avec `attente_s` de 600 ; une autre IP se connecte ; à `T + 10 min 01 s`, l'IP repasse ;
  - `test_succes_remet_le_compteur` : 2 échecs, 1 succès, 2 échecs : pas de blocage ;
  - `test_code_change_le_mdp_et_ferme_les_sessions` : l'ancien mot de passe et l'ancienne session ne marchent plus, le nouveau mot de passe oui ;
  - `test_code_expire_apres_10_minutes` ;
  - `test_cinq_essais_par_code` : après 5 codes faux, le bon rend `False` ;
  - `test_un_code_par_10_minutes_et_3_par_jour` : deuxième demande à `T + 5 min` : `TropDeCodes` ; à `+10` et `+20` minutes : ça passe ; quatrième le même jour : `TropDeCodes` ; le lendemain : ça passe ;
  - `test_code_jamais_en_clair` ;
  - `test_sans_mdp_defini` : `ouvrir` rend `None` et `demander_code` lève `PasConfigure`.
- [ ] **Étape 2 :** lancer `.venv/Scripts/python -m unittest tests.test_connexion -v`. Attendu : échec à l'import.
- [ ] **Étape 3 :** écrire `connexion.py`.
- [ ] **Étape 4 :** relancer, puis toute la suite. Attendu : tout passe.
- [ ] **Étape 5 :** commit `feat(admin): add password, sessions, lockout and reset code`.

### Tâche 6 : lecture du journal des appels

**Fichiers :** modifier `voixfongbe/journal.py`, `tests/test_journal.py`.

**Produit :**
- `Journal.lire(jour: date, *, projet: str | None = None, page: int = 1, par_page: int = 50) -> dict` : `{"lignes": list[dict], "total": int, "page": int, "pages": int}`, plus récentes d'abord ; une ligne abîmée est sautée ; un jour sans fichier donne `total` 0 et `pages` 1.
- `Journal.resume(jour: date) -> dict` : `{"demandes": int, "erreurs": int, "temps_moyen_ms": int | None}`, où `erreurs` compte les codes à partir de 400 et `temps_moyen_ms` est la moyenne des réponses 200 hors cache (`None` s'il n'y en a pas).
- `Journal.jours() -> list[str]` : jours qui ont un fichier, plus récents d'abord.

- [ ] **Étape 1 :** écrire les tests :
  - `test_lire_filtre_par_projet` ;
  - `test_pagination` : 120 lignes donnent `pages` 3, et la page 3 en a 20 ; la première ligne de la page 1 est la plus récente ;
  - `test_jour_sans_fichier` ;
  - `test_ligne_abimee_sautee` ;
  - `test_resume` : deux 200 hors cache de 1 000 et 3 000 ms, un 200 en cache de 10 ms, un 401 et un 429 donnent `{"demandes": 5, "erreurs": 2, "temps_moyen_ms": 2000}` ;
  - `test_jours`.
- [ ] **Étape 2 :** lancer `.venv/Scripts/python -m unittest tests.test_journal -v`. Attendu : échecs.
- [ ] **Étape 3 :** modifier `journal.py`.
- [ ] **Étape 4 :** relancer, puis toute la suite. Attendu : tout passe.
- [ ] **Étape 5 :** commit `feat(log): read, filter, page and summarise the call log`.

### Tâche 7 : socle web, demande d'accès et lien d'accès

**Fichiers :** créer `voixfongbe/reponses.py`, `voixfongbe/web.py`, `voixfongbe/publiques.py`, `voixfongbe/web/demande.html`, `voixfongbe/web/acces.html` et `voixfongbe/web/style.css` (squelettes, dessinés en tâche 9), `tests/test_publiques.py` ; modifier `voixfongbe/app.py`, `tests/aides.py`.

**Consomme :** tâches 1 à 4.

**Produit :**
- `reponses.py` : `MESSAGES`, `ErreurApi(code, entetes=None, *, message=None, donnees=None)`, `reponse_json(statut, donnees, entetes=None)` et `reponse_erreur(e)`, sortis de `app.py` sans changer leur comportement. `reponse_erreur` ajoute `donnees` au JSON (par exemple `{"champ": "nom"}`). Nouveaux codes, avec leur statut ; le texte est libre, en français :

| Code | Statut | Code | Statut |
| --- | --- | --- | --- |
| `origine` | 403 | `mdp_faux` | 401 |
| `type_contenu` | 415 | `bloque` | 429, `Retry-After` |
| `champ_invalide` | 400 | `pas_configure` | 503 |
| `trop_de_demandes` | 429 | `trop_de_codes` | 429, `Retry-After` |
| `demandes_fermees` | 503 | `code_faux` | 400 |
| `lien_invalide` | 410 (le message cite `technum.services@bytechnum.com`) | `mdp_court` | 400 |
| `non_connecte` | 401 | `valeur_invalide` | 400 |
| `projet_pris` | 409 | `projet_inconnu`, `demande_inconnue` | 404 |
| `deja_decidee` | 409 | `etat_incompatible` | 409 |
| `courriel_absent` | 400 | `smtp_absent` | 503 |

- `web.py` :
  - `@dataclass Contexte(config, moteur, horloge, cles, quotas, reglages, demandes, connexion, courriel, journal)` ;
  - `ip_client(environ) -> str` : dernière entrée de `X-Forwarded-For`, sinon `REMOTE_ADDR`, sinon `"inconnue"` ;
  - `meme_origine(environ, hote) -> bool` : l'hôte de `Origin` vaut `hote`, ou, sans `Origin`, celui de `Referer` ; aucun des deux donne `False` ;
  - `lire_cookie(environ, nom) -> str | None` ;
  - `lire_corps_json(environ, max_corps) -> dict` : lève `ErreurApi("type_contenu")` si `CONTENT_TYPE` n'est pas `application/json`, puis suit les règles de `lire_corps` d'aujourd'hui ;
  - `controler_post(environ, ctx)` : lève `ErreurApi("origine")` si `meme_origine` échoue, puis `ErreurApi("type_contenu")` si le corps n'est pas du JSON ;
  - `page(nom) -> tuple` : HTML avec `ENTETES_PAGE` = `Content-Type: text/html; charset=utf-8`, `Cache-Control: no-store`, `X-Frame-Options: DENY`, et `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'` ;
  - `statique(nom) -> tuple | None` : seulement les fichiers `.css`, `.js` et `.woff2` présents dans `voixfongbe/web/`, listés au chargement. Types `text/css; charset=utf-8`, `text/javascript; charset=utf-8` et `font/woff2` ; `Cache-Control: public, max-age=3600` (polices : `max-age=31536000, immutable`).
- `app.py` : une seule table de routes `(motif compilé, méthodes, gestionnaire)`, parcourue avec `fullmatch` pour décider 404, 405 (`Allow`) et la redirection HTTPS (inchangée), puis pour appeler le gestionnaire. Les routes `/v1/…` et `/robots.txt` gardent leur code. `creer_application(config, moteur=None, horloge=None, courriel=None)` construit le `Contexte` : fichiers `reglages.json`, `demandes.json`, `admin.json`, `smtp.json` dans le stockage. Routes de `publiques.ROUTES` :

| Route | Méthodes | Effet |
| --- | --- | --- |
| `/demande` | GET | page `demande.html` |
| `/api/demande` | GET | `{"ouvertes": bool}` |
| `/api/demande` | POST | même origine et JSON ; champ piège `site_web` rempli : 200 `{"ok": true}` sans rien garder ni envoyer ; `valider`, puis `deposer(pris=` noms de `cles.lister()`) ; annonce envoyée à `reglages.lire()["adresse"]` (un échec n'empêche pas la réponse) ; 200 `{"ok": true}` |
| `/acces/(?P<jeton>[A-Za-z0-9_-]{43})` | GET | page `acces.html` ; ne consomme rien |
| `/api/acces/(?P<jeton>…)` | GET | `{"valide": bool}` ; ne consomme rien |
| `/api/acces/(?P<jeton>…)` | POST | même origine et JSON ; `utiliser_lien` ; 200 `{"projet", "cle", "limite", "guide"}` avec `Cache-Control: no-store`, ou 410 `lien_invalide` |
| `/static/(?P<nom>[a-z0-9-]+\.(?:css\|js\|woff2))` | GET | `statique(nom)` ou 404 |

- `tests/aides.py` : `appeler(app, methode, chemin, corps=None, entetes=None, requete="")` remplit `QUERY_STRING` ; `ORIGINE = {"Origin": "https://voix.bytechnum.com"}`.

- [ ] **Étape 1 :** écrire `tests/test_publiques.py` :

```python
def test_lien_ouvert_par_un_antivirus_reste_utilisable(self):  # point de vigilance 1
    jeton = self.cles.preparer("alpha", courriel="koffi@exemple.bj", maintenant=T)
    for _ in range(2):
        self.assertEqual(appeler(self.app, "GET", f"/acces/{jeton}")[0], 200)
        self.assertEqual(json.loads(appeler(self.app, "GET", f"/api/acces/{jeton}")[2]), {"valide": True})
    statut, entetes, corps = appeler(self.app, "POST", f"/api/acces/{jeton}", {}, ORIGINE)
    self.assertEqual((statut, entetes["Cache-Control"]), (200, "no-store"))
    self.assertEqual(self.cles.verifier(json.loads(corps)["cle"]), "alpha")
    self.assertEqual(self.code(appeler(self.app, "POST", f"/api/acces/{jeton}", {}, ORIGINE)), (410, "lien_invalide"))
```

  Autres tests :
  - `test_page_demande_protegee` : 200, `text/html`, la CSP contient `frame-ancestors 'none'` et `script-src 'self'`, `X-Frame-Options: DENY`, `X-Robots-Tag: noindex, nofollow` ;
  - `test_demande_enregistree_et_annoncee` : 200 ; une demande en attente ; un seul e-mail, adressé à `eliseeatonde@gmail.com`, et aucun au demandeur ;
  - `test_demande_sans_origine_ou_d_ailleurs_403` : sans en-tête, ou avec `Origin: https://ailleurs.example` ;
  - `test_referer_de_la_page_accepte` : `Referer: https://voix.bytechnum.com/demande` ;
  - `test_champ_piege_ignore_en_silence` : 200, aucune demande, aucun e-mail ;
  - `test_champ_invalide_donne_le_champ` : 400, `code` `champ_invalide`, `champ` `description` ;
  - `test_quatrieme_demande_de_la_meme_ip_429` : `X-Forwarded-For` `10.0.0.1, 203.0.113.7`, puis `10.9.9.9, 203.0.113.7` : comptées ensemble ;
  - `test_demandes_fermees` : 50 en attente donnent `{"ouvertes": false}` et un POST en 503 ;
  - `test_annonce_en_panne_n_empeche_pas_la_demande` ;
  - `test_post_acces_sans_origine_403` et `test_lien_expire_410` ;
  - `test_post_sans_json_415` : `CONTENT_TYPE` `application/x-www-form-urlencoded` ;
  - `test_statique_et_traversee` : `/static/style.css` donne 200 `text/css` ; `/static/../app.py`, `/static/inconnu.js` et `/static/app.py` donnent 404 ;
  - `test_redirection_https_des_nouvelles_routes` : `/demande` avec `X-Forwarded-Proto: http` donne 301 vers `https://voix.bytechnum.com/demande` ;
  - `test_methode_405_avec_allow` : `DELETE /api/demande` donne 405, `Allow: GET, POST`.
- [ ] **Étape 2 :** lancer `.venv/Scripts/python -m unittest tests.test_publiques -v`. Attendu : échecs.
- [ ] **Étape 3 :** écrire `reponses.py` (puis vérifier que `tests.test_app` passe toujours), `web.py`, `publiques.py`, les trois squelettes (une page avec un formulaire minimal et `<script src="/static/…">`), puis la table des routes de `app.py`.
- [ ] **Étape 4 :** relancer, puis toute la suite. Attendu : tout passe.
- [ ] **Étape 5 :** commit `feat(web): add the access request form and the one-time key link`.

### Tâche 8 : API de l'espace d'administration

**Fichiers :** créer `voixfongbe/admin.py`, `voixfongbe/web/admin.html` (squelette), `tests/test_admin.py` ; modifier `voixfongbe/app.py` (ajout de `admin.ROUTES`).

**Consomme :** tâches 1 à 7.

**Produit :**
- Cookie de session `__Host-voix-admin=<jeton>; Path=/; HttpOnly; Secure; SameSite=Strict`, sans durée (session du navigateur) ; à la déconnexion, `Max-Age=0`.
- Toute réponse de `/api/admin/…` a `Cache-Control: no-store`. Tout POST passe par `controler_post`. Hors `etat`, `connexion`, `oubli` et `oubli/changer`, une session valide est exigée, sinon 401 `non_connecte`.
- Routes de `admin.ROUTES` :

| Route | Méthode | Corps et réponse |
| --- | --- | --- |
| `/admin` | GET | page `admin.html` |
| `/api/admin/etat` | GET | `{"configure", "connecte"}` |
| `/api/admin/connexion` | POST | `{"mot_de_passe"}` ; 200 et cookie, 401 `mdp_faux`, 429 `bloque`, 503 `pas_configure` |
| `/api/admin/deconnexion` | POST | ferme la session |
| `/api/admin/oubli` | POST | code envoyé à l'adresse des réglages : 200 `{"ok": true}` ; 429 `trop_de_codes` ; 503 `pas_configure` ou `smtp_absent` |
| `/api/admin/oubli/changer` | POST | `{"code", "mot_de_passe"}` ; 200 et e-mail d'alerte ; 400 `code_faux` ou `mdp_court` |
| `/api/admin/demandes` | GET | `{"en_attente": [...], "historique": [...]}` |
| `/api/admin/demandes/(?P<id>[0-9a-f]{16})/approuver` | POST | `{"projet"?, "limite"?}` (par défaut le nom proposé et 100) : `preparer`, puis `marquer_approuvee`, puis e-mail `acces_accorde` avec `https://{hote}/acces/{jeton}` ; 200 `{"ok": true, "courriel_envoye": bool}` ; 409 `deja_decidee` ou `projet_pris` ; 400 `valeur_invalide` |
| `/api/admin/demandes/(?P<id>…)/refuser` | POST | `{"motif"?}` (500 caractères au plus) ; e-mail `refus` ; même forme de réponse |
| `/api/admin/projets` | GET | `{"plafond", "total_jour", "projets": [...]}`. Chaque projet reprend `lister()`, plus `aujourd_hui` (décompte du jour) et `depasse_plafond` (`limite > plafond`) |
| `/api/admin/projets/(?P<projet>[a-z0-9-]{2,40})/limite` | POST | `{"limite"}` |
| `…/courriel` | POST | `{"courriel"}` |
| `…/revoquer` | POST | |
| `…/nouvelle-cle` | POST | états `active` ou `revoquee`, sinon 409 `etat_incompatible` ; 400 `courriel_absent` ; `nouveau_lien`, puis e-mail ; `{"ok", "courriel_envoye"}` |
| `…/nouveau-lien` | POST | états `lien_en_attente` ou `lien_expire` ; le reste comme `nouvelle-cle` |
| `…/supprimer` | POST | 409 `etat_incompatible` si le projet n'est pas révoqué ; `supprimer` puis `demandes.effacer_projet` |
| `/api/admin/appels` | GET | requête `jour` (jour de Porto-Novo par défaut ; refusé s'il est invalide ou a plus de 90 jours), `projet`, `page` ; `{"jour", "jours", "projet", "resume", "lignes", "total", "page", "pages"}` |
| `/api/admin/reglages` | GET | `{"adresse", "plafond", "smtp": {"configure"}, "voix": {"pret", "version"}}` |
| `/api/admin/reglages` | POST | `{"adresse"?, "plafond"?}` ; 400 `valeur_invalide` |
| `/api/admin/reglages/essai` | POST | e-mail `essai` à l'adresse ; 503 `smtp_absent` ; `{"ok", "courriel_envoye"}` |

- [ ] **Étape 1 :** écrire `tests/test_admin.py`, avec une horloge réglable (`self.maintenant`), un `CourrielFactice`, un mot de passe défini dans `setUp`, et des aides locales : `post(chemin, corps)` (avec `ORIGINE` et le cookie de la session ouverte), `code(reponse)` et `deposer_demande() -> id` :

```python
def test_double_approbation(self):  # point de vigilance 3
    ident = self.deposer_demande()
    r1 = self.post(f"/api/admin/demandes/{ident}/approuver", {"projet": "alpha-uac", "limite": 200})
    r2 = self.post(f"/api/admin/demandes/{ident}/approuver", {"projet": "alpha-uac", "limite": 200})
    self.assertEqual(r1[0], 200)
    self.assertEqual(self.code(r2), (409, "deja_decidee"))
    self.assertEqual(len([e for e in self.courriel.envoyes if e["a"] == "koffi@exemple.bj"]), 1)

def test_smtp_en_panne_pendant_l_approbation(self):  # point de vigilance 4
    ident = self.deposer_demande()
    self.courriel.en_panne = True
    statut, _, corps = self.post(f"/api/admin/demandes/{ident}/approuver", {"projet": "alpha"})
    self.assertEqual((statut, json.loads(corps)), (200, {"ok": True, "courriel_envoye": False}))
    self.assertEqual(self.cles.lister(T)[0]["etat"], "lien_en_attente")
    self.courriel.en_panne = False
    self.assertEqual(self.post("/api/admin/projets/alpha/nouveau-lien", {})[0], 200)
    jeton = re.search(r"/acces/([A-Za-z0-9_-]{43})", self.courriel.envoyes[-1]["texte"]).group(1)
    self.assertEqual(appeler(self.app, "POST", f"/api/acces/{jeton}", {}, ORIGINE)[0], 200)
```

  Autres tests :
  - `test_etat_sans_session` ;
  - `test_cookie_de_session_strict` : `Set-Cookie` contient `__Host-voix-admin=`, `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/` ;
  - `test_donnees_refusees_sans_session` : les quatre GET donnent 401 `non_connecte` ;
  - `test_post_admin_d_ailleurs_403_meme_connecte` ;
  - `test_mdp_faux_puis_blocage` : 401, 401, 401, puis 429 `bloque` ;
  - `test_deconnexion` ;
  - `test_session_expiree_apres_10_minutes` ;
  - `test_approuver_cree_le_projet_et_envoie_le_lien` : projet `alpha-uac` en `lien_en_attente`, limite 200 ; le lien de l'e-mail, ouvert par POST, donne une clé qui marche sur `/v1/synthese` ;
  - `test_approuver_nom_pris_409` ;
  - `test_refuser_avec_motif` ;
  - `test_limite_jusqu_a_un_million` : 1 000 000 donne 200 ; `0` et `"abc"` donnent 400 `valeur_invalide` ;
  - `test_depassement_du_plafond_signale` : limite 500 et plafond 300 donnent `depasse_plafond` `True` ;
  - `test_compte_du_jour` : après un appel à `/v1/synthese`, `aujourd_hui` vaut 1 ;
  - `test_projet_ssh_recoit_une_adresse_puis_un_lien` : `projet-collegue` créé par `creer` ; `nouvelle-cle` donne 400 `courriel_absent` ; après `courriel`, 200 et e-mail envoyé ; l'ancienne clé ne marche plus ;
  - `test_revoquer_puis_supprimer_efface_la_demande` et `test_supprimer_un_projet_actif_409` ;
  - `test_appels_filtres_et_pagines` : `requete="jour=2026-11-09&projet=demo&page=1"` ; `jour=2026-13-01` et un jour d'il y a 91 jours donnent 400 ;
  - `test_reglages_lus_et_modifies` et `test_essai_d_envoi` (503 `smtp_absent` si `configure_` vaut `False`) ;
  - `test_mot_de_passe_oublie_de_bout_en_bout` : code envoyé à l'adresse des réglages ; `oubli/changer` donne 200 ; un e-mail d'alerte part ; l'ancienne session donne 401 ; le nouveau mot de passe ouvre une session ;
  - `test_deuxieme_code_trop_tot_429`.
- [ ] **Étape 2 :** lancer `.venv/Scripts/python -m unittest tests.test_admin -v`. Attendu : échecs.
- [ ] **Étape 3 :** écrire `admin.py` et le squelette `admin.html`, puis brancher `admin.ROUTES` dans `app.py`.
- [ ] **Étape 4 :** relancer, puis toute la suite. Attendu : tout passe.
- [ ] **Étape 5 :** commit `feat(admin): add the admin api for requests, projects, calls and settings`.

### Tâche 9 : pages, styles, polices et essai sur le PC

**Fichiers :** créer `voixfongbe/web/demande.js`, `acces.js`, `admin.js`, les polices `montserrat-latin-400.woff2`, `-600`, `-700` et `montserrat-latin-ext-400.woff2`, `-600`, `-700`, `OFL.txt` (copies de `C:\wamp64\www\demo_agrifon\demo_agriculture\site\fonts\…-normal.woff2`, renommées), `scripts/essai_local.py`, `tests/test_pages.py` ; finir `demande.html`, `acces.html`, `admin.html` et `style.css` ; ajouter `*.woff2 binary` à `.gitattributes`.

**Consomme :** les routes et réponses des tâches 7 et 8.

Avant d'écrire, charger les skills `frontend-design` et `web-anti-cliches-ia`. Suivre les maquettes validées : `C:\wamp64\www\demo_agrifon\.superpowers\brainstorm\2861-1794248193\content\demande-de-cle.html` et `espace-admin.html`. Couleurs : bleu `#405FE0`, charcoal `#373536`, fond `#F4F6FB`. Montserrat 400, 600 et 700, déclarée avec `unicode-range` (latin et latin-ext, pour `ɔ`, `ɛ` et `ɖ`). Pages lisibles à 390 px de large, avec 16 px de marge et sans défilement horizontal de la page : un tableau large défile dans son cadre. Focus clavier visible.

Contenu des pages :
- `demande.html` : titre « Demander un accès à la voix fon » ; une phrase (« gratuite et réservée aux projets non commerciaux ») ; champs nom et prénom, adresse e-mail, organisation (facultatif), projet en quelques lignes (compteur sur 1 000) ; case d'accord avec la mention exacte ; bouton « Envoyer ma demande » ; sous le bouton, la notice : données servant seulement à traiter la demande et à vous contacter, demandes refusées effacées après 90 jours, contact `technum.services@bytechnum.com`. Champ piège `site_web` sorti de l'écran par une classe, `tabindex="-1"`, `autocomplete="off"`, `aria-hidden="true"`. Après l'envoi : « Demande reçue. Vous recevrez un e-mail dès qu'elle aura été examinée. » Si les demandes sont fermées (`GET /api/demande`), la page le dit à la place du formulaire. Une erreur s'affiche sous son champ (`aria-describedby`).
- `acces.html` : si `GET /api/acces/<jeton>` donne `valide`, un bouton « Afficher ma clé » ; après le POST, la clé en police à chasse fixe, un bouton « Copier » (`navigator.clipboard.writeText`, avec sélection du texte en repli), et les consignes : elle ne sera plus jamais affichée, la ranger dans une variable d'environnement du serveur et jamais dans une page web, le guide, la limite, la mention. Lien invalide : la page invite à écrire à `technum.services@bytechnum.com`.
- `admin.html` :
  - écran de connexion : mot de passe, « Se connecter », puis « Mot de passe oublié ? » qui mène à « Envoyer un code », au code et au nouveau mot de passe saisi deux fois ;
  - si `configure` vaut `false`, l'écran renvoie à `EXPLOITATION.md` ;
  - une fois connecté : bandeau « Voix fon · Administration », état de la voix et sa version, « Se déconnecter » ; onglets Demandes (avec le nombre en attente), Projets et limites, Appels, Réglages, au contenu de la conception (§ 6.3) ;
  - nom du projet modifiable avant « Approuver », et limite dans la même action ; limite modifiable dans sa case (champ nombre, 1 à 1 000 000, enregistrée par Entrée ou par un bouton, avec une confirmation visible) ; avertissement quand elle dépasse le plafond ; confirmation avant Révoquer, Nouvelle clé, Supprimer et Refuser ;
  - quand un e-mail n'est pas parti, l'écran le dit et propose « Nouveau lien » ;
  - lignes d'erreur des Appels mises en évidence ;
  - une réponse 401 `non_connecte` ramène à l'écran de connexion.
- Scripts : tout passe par `textContent`, `createElement` et `setAttribute` ; aucune chaîne HTML construite.
- `scripts/essai_local.py [--exemples]` : sert l'application avec `wsgiref.simple_server` sur `localhost:8765` (`hote="localhost:8765"`, stockage dans `tmp/essai-local/`, modèle `modele/` s'il est là). `--exemples` remplit des demandes, des projets dans chaque état et des lignes de journal fictives, définit un mot de passe aléatoire et l'affiche dans la console : c'est un mot de passe local d'essai, jamais celui du serveur.

- [ ] **Étape 1 :** écrire `tests/test_pages.py` :
  - `test_ni_script_ni_style_en_ligne` : avec `html.parser`, chaque `<script>` a un `src`, aucun élément `<style>`, aucun attribut `style` ni `on…` ;
  - `test_scripts_sans_injection_html` (point de vigilance 5) : aucun fichier `.js` ne contient `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval(` ou `new Function` ;
  - `test_ressources_locales` : tout `src` et tout `<link href>` commence par `/static/` ;
  - `test_polices_servies` : `/static/montserrat-latin-ext-400.woff2` donne 200, `font/woff2`, et un corps qui commence par `b"wOF2"` ;
  - `test_contact_public` : `demande.html` contient `technum.services@bytechnum.com` et pas `eliseeatonde@gmail.com` ;
  - `test_mention_exacte` : `demande.html` et `acces.html` contiennent « Voix : MMS-TTS de Meta (CC BY-NC 4.0) ».
- [ ] **Étape 2 :** lancer `.venv/Scripts/python -m unittest tests.test_pages -v`. Attendu : échecs (polices et scripts absents).
- [ ] **Étape 3 :** copier les polices et `OFL.txt`, modifier `.gitattributes`, écrire les pages, `style.css`, les trois scripts et `scripts/essai_local.py`.
- [ ] **Étape 4 :** relancer, puis toute la suite. Attendu : tout passe.
- [ ] **Étape 5 :** lancer `.venv/Scripts/python scripts/essai_local.py --exemples`. Avec Playwright, à 1 280 et à 390 px de large, faire le parcours entier : envoyer une demande ; se connecter ; approuver en changeant le nom et la limite ; ouvrir le lien (affichage, puis « Copier ») ; changer une limite au-delà du plafond ; révoquer, puis supprimer ; filtrer les appels ; essai d'envoi (non configuré) ; mot de passe oublié jusqu'au message d'envoi impossible. Attendu : aucune erreur dans la console (CSP comprise), aucun défilement horizontal de la page, un nom piégé `<img src=x onerror=alert(1)>` affiché en texte. Si Chromium refuse le cookie `__Host-` sur `http://localhost`, ne pas affaiblir le cookie de production : noter une décision dans le registre et contourner seulement dans `essai_local.py`. Garder les captures pour Elisée.
- [ ] **Étape 6 :** commit `feat(web): design the request, key and admin pages`.

### Tâche 10 : scripts SSH, documents et contrôle après déploiement

**Fichiers :** créer `scripts/admin.py`, `tests/test_scripts.py` ; modifier `scripts/cles.py`, `scripts/deployer.sh`, `README.md`, `EXPLOITATION.md`.

**Consomme :** `Connexion.definir_mdp`, `courriel.ecrire_reglages`, `Courriel.envoyer`, `messages.essai`, `Reglages.lire`, `Cles.lister`.

**Produit :**
- `scripts/admin.py`, mêmes conventions que `scripts/cles.py` (`RACINE`, `Config.depuis_env`, stockage en 700) :
  - `mot-de-passe` : `getpass` deux fois, jamais d'argument en ligne de commande ; code de sortie 1 si les deux saisies diffèrent ou si le mot de passe fait moins de 12 caractères ; sinon « Mot de passe enregistré. Toutes les sessions sont fermées. », puis l'e-mail `alerte_mdp` à l'adresse des réglages si l'envoi est configuré (conception § 6.4 : alerte après chaque changement) ;
  - `smtp` : `input` pour l'hôte (`mail.spacemail.com` par défaut), le port (465), l'utilisateur et l'expéditeur (l'utilisateur par défaut) ; `getpass` pour le mot de passe ; écrit `smtp.json` ; n'affiche jamais le mot de passe ;
  - `essai-smtp` : envoie `messages.essai()` à l'adresse des réglages ; affiche le résultat ; code 1 en cas d'échec.
- `scripts/cles.py lister` affiche aussi l'état et la limite ; `revoquer` dit que la fiche reste visible dans l'espace admin.
- `scripts/deployer.sh` : après le contrôle de `/v1/etat`, contrôle que `/demande` et `/admin` répondent 200.
- `README.md` : nouvelle section « Demander un accès », avant « 1. Votre clé d'accès ». Elle donne le formulaire `https://voix.bytechnum.com/demande`, la décision par e-mail, le lien valable 7 jours qui affiche la clé une seule fois, et le contact pour un nouveau lien. Mettre à jour § 1 et § 7 : limite propre à chaque projet, 100 par défaut, indiquée dans l'e-mail.
- `EXPLOITATION.md` :
  - premier mot de passe (`scripts/admin.py mot-de-passe`) ;
  - boîte d'envoi (`scripts/admin.py smtp`, puis `essai-smtp`) : une adresse `@bytechnum.com` chez Spacemail ;
  - l'espace admin et ce qu'on y fait ;
  - mot de passe oublié ;
  - les nouveaux fichiers du stockage (`admin.json`, `smtp.json`, `reglages.json`, `demandes.json`) ;
  - les données personnelles gardées et leur durée ;
  - les commandes SSH qui restent utiles.

- [ ] **Étape 1 :** écrire `tests/test_scripts.py` (module chargé par `importlib`, `VOIX_STOCKAGE_DIR` vers un dossier temporaire, `getpass.getpass` et `builtins.input` remplacés) :
  - `test_mot_de_passe_enregistre` : `Connexion.configure()` vaut ensuite `True` ;
  - `test_mot_de_passe_differents_ou_court` : code 1 ;
  - `test_smtp_ecrit_sans_afficher_le_mot_de_passe` : `smtp.json` a les cinq clés, et la sortie capturée ne contient pas le mot de passe ;
  - `test_lister_affiche_etat_et_limite`.
- [ ] **Étape 2 :** lancer `.venv/Scripts/python -m unittest tests.test_scripts -v`. Attendu : échecs.
- [ ] **Étape 3 :** écrire `scripts/admin.py`, modifier `scripts/cles.py` et `scripts/deployer.sh`, puis les deux documents.
- [ ] **Étape 4 :** relancer, puis toute la suite. Attendu : tout passe (99 tests d'avant, en comptant ceux qui ont été modifiés, plus les nouveaux).
- [ ] **Étape 5 :** vérifier qu'aucun commit de la branche ne contient de trace d'outil d'IA : `git log main..HEAD --format='%B' | grep -inE 'claude|anthropic|co-authored-by|generated (with|by)'`. Attendu : aucune ligne.
- [ ] **Étape 6 :** commit `docs: explain access requests, the admin space and its first setup`.

## Après le plan

1. Relecture finale de toute la branche (executing-plans), puis superpowers:finishing-a-development-branch. Pousser et ouvrir la PR demande l'accord d'Elisée ; c'est lui qui fusionne.
2. Déploiement par `scripts/deployer.sh`, sur son accord explicite.
3. Étapes d'Elisée, en SSH : créer la boîte d'envoi chez Spacemail si elle n'existe pas ; puis `scripts/admin.py mot-de-passe`, `scripts/admin.py smtp` et `scripts/admin.py essai-smtp` ; enfin ouvrir `https://voix.bytechnum.com/admin` et saisir l'adresse de `projet-collegue` s'il veut pouvoir lui envoyer un nouveau lien.
