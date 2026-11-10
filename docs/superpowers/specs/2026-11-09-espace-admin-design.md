# Espace d'administration et demandes de clé : conception

Date : 9 novembre 2026. Rédigée avec Elisée, qui a validé chaque point en conversation (maquettes `demande-de-cle.html` et `espace-admin.html`).
S'appuie sur le service de voix en ligne (`docs/superpowers/specs/2026-11-09-voix-fon-design.md`, PR #1 à #3).

## 1. Intention

Aujourd'hui, chaque clé se crée en SSH par Elisée, et rien ne montre l'usage du service sans lire des fichiers sur le serveur. Elisée veut que des collègues ou d'autres personnes puissent **demander un accès** par une page web, qu'il **valide dans un espace d'administration**, et qu'ils reçoivent leur accès **par e-mail, sans que personne n'ouvre un terminal**. Le même espace doit montrer les appels et permettre d'**augmenter à volonté la limite d'un projet**.

## 2. Objectifs

- Page publique `https://voix.bytechnum.com/demande` : formulaire de demande d'accès.
- Espace `https://voix.bytechnum.com/admin`, réservé à Elisée : demandes, projets et limites, appels, réglages.
- À l'approbation : clé créée sans terminal, e-mail avec un lien à usage unique qui affiche la clé une fois.
- Limite quotidienne de chaque projet réglable à n'importe quelle valeur.

## 3. Non-objectifs

- Comptes pour les demandeurs (pas d'espace utilisateur, pas de mot de passe côté demandeur).
- Plusieurs administrateurs.
- Facturation, offres payantes (la licence de la voix l'interdit).
- Modifier depuis l'écran les limites techniques (1 000 caractères par demande, délai de 30 s, une synthèse à la fois, morceaux de 120 caractères) : elles protègent la mémoire du serveur partagé.

## 4. Anti-objectifs

- Une clé en clair stockée sur le serveur ou envoyée dans un e-mail.
- Un formulaire public qui sert à envoyer des e-mails à n'importe quelle adresse (relais de spam) : **aucun e-mail n'est envoyé au demandeur tant qu'Elisée n'a pas décidé**.
- Un lien d'accès consommé par l'aperçu automatique d'une messagerie (les antivirus de messagerie ouvrent les liens) avant que la personne ne le voie.
- Un espace d'administration attaquable par devinette du mot de passe ou par une page tierce (CSRF).
- Casser les appels des projets existants pendant la mise à jour (la clé `projet-collegue` doit continuer de marcher).

## 5. Contraintes

Celles du service de voix (même application WSGI sans framework, Python 3.13 sur le serveur, plusieurs processus Passenger possibles, stockage en fichiers JSON sous verrou, secrets dans des fichiers en droits 600, aucun texte demandé dans les journaux, messages en français, commits sans trace d'IA, Elisée fusionne, déploiement sur son accord). En plus :

- Dépendances : aucune nouvelle ; e-mails par `smtplib` et `ssl` de la bibliothèque standard.
- Interface en HTML, CSS et JavaScript sans bibliothèque, servie par l'application (jamais par un dossier `public/`), aux couleurs de TECHNUM (bleu `#405FE0`, charcoal `#373536`, fond `#F4F6FB`), police Montserrat embarquée (fichiers `woff2` sous licence OFL, déjà dans le dépôt AgriFon).
- Données personnelles des demandeurs (nom, e-mail, organisation, description) : loi béninoise 2017-20 ; une notice courte sur le formulaire.

## 6. Décisions

« Elisée » : validé par lui ; « choix de conception » : proposé et accepté dans la conversation ; « à vérifier » : tranché à la relecture, à vérifier par Elisée.

### 6.1 Demande d'accès (`/demande`)

- Champs : nom et prénom, e-mail, organisation (facultatif), description du projet (20 à 1 000 caractères), case obligatoire « Mon projet n'est pas commercial, et j'afficherai la mention « Voix : MMS-TTS de Meta (CC BY-NC 4.0) » » (choix de conception).
- Notice sous le bouton : données utilisées seulement pour traiter la demande et contacter le demandeur ; demandes refusées effacées après 90 jours ; contact : `technum.services@bytechnum.com` (Elisée).
- Après l'envoi : « Demande reçue. Vous recevrez un e-mail dès qu'elle aura été examinée. » **Aucun e-mail au demandeur à ce stade.** Elisée reçoit un e-mail d'annonce (choix de conception).
- Protection : champ piège invisible (rempli par un robot : demande ignorée en silence) ; 3 demandes par jour et par adresse IP (dernière entrée de `X-Forwarded-For`, comme AgriFon) ; 50 demandes en attente au plus, au-delà la page dit « Les demandes sont momentanément fermées » ; même origine exigée pour l'envoi.
- Nom du projet : tiré du nom ou de l'organisation, mis au format des clés (`^[a-z0-9-]{2,40}$`, suffixe numérique si déjà pris) ; modifiable par Elisée avant l'approbation.

### 6.2 Approbation et accès par lien (Elisée)

- **Approuver** : crée le projet avec sa limite (100 par défaut, modifiable dans la même action) et un **jeton d'accès** aléatoire (32 octets), dont seule l'empreinte SHA-256 est gardée, valable 7 jours. E-mail au demandeur : lien `https://voix.bytechnum.com/acces/<jeton>`, lien du README, limite, rappel de la licence.
- **La clé n'existe pas encore à l'approbation** : elle est créée au moment où le demandeur l'affiche. Ainsi aucune clé en clair n'est jamais stockée.
- Page `/acces/<jeton>` : un `GET` affiche « Afficher ma clé » sans rien consommer (les aperçus automatiques des messageries ne la grillent pas) ; le clic envoie un `POST` qui crée la clé, marque le jeton utilisé et affiche la clé **une seule fois**, avec un bouton « Copier » et les consignes. Jeton expiré ou déjà utilisé : page claire qui invite à contacter Elisée.
- **Refuser** : motif facultatif ; e-mail poli au demandeur, avec le motif s'il y en a un.
- **Nouvelle clé** (projet existant) : révoque la clé actuelle et envoie un nouveau lien à l'adresse du projet. **Nouveau lien** : renvoie un lien si le précédent a expiré sans être utilisé.
- Les projets créés en SSH (comme `projet-collegue`) apparaissent dans la liste, sans adresse e-mail : Elisée peut en saisir une pour pouvoir leur envoyer un nouveau lien.

### 6.3 Espace d'administration (`/admin`)

Quatre onglets (maquette validée) :

1. **Demandes** : en attente (nom, e-mail, organisation, description, date), avec Approuver / Refuser ; historique des décisions.
2. **Projets et limites** :
   - par projet : demandes du jour, limite quotidienne **librement modifiable** (tout entier de 1 à 1 000 000), adresse, date de création, état (actif, révoqué, lien en attente) ; actions Révoquer, Nouvelle clé, Nouveau lien, et Supprimer pour un projet déjà révoqué (efface ses données personnelles ; à vérifier) ;
   - le plafond commun à tous les projets (300 aujourd'hui), modifiable de la même façon ;
   - avertissement quand la limite d'un projet dépasse le plafond commun (Elisée).
3. **Appels** : journal existant (heure, projet, caractères, format, durée, cache, code), filtres par projet et par jour, 90 jours, 50 lignes par page, erreurs mises en évidence ; chiffres du jour (demandes, temps moyen, erreurs).
4. **Réglages** : adresse qui reçoit les annonces et les codes (par défaut `eliseeatonde@gmail.com`), état de l'envoi d'e-mails (configuré ou non, essai d'envoi à cette adresse), état de la voix.

### 6.4 Connexion de l'administrateur

- Mot de passe (12 caractères au moins), empreinte scrypt dans le stockage, défini la première fois en SSH (`scripts/admin.py mot-de-passe`), comme AgriFon.
- **Mot de passe oublié** : code à 8 chiffres envoyé à l'adresse des réglages, valable 10 minutes, 5 essais, 1 envoi par 10 minutes et 3 par jour ; nouveau mot de passe actif sans redémarrage ; toutes les sessions fermées ; e-mail d'alerte après chaque changement. Même comportement que le « mot de passe oublié » d'AgriFon (choix de conception, accepté).
- Sessions : jeton aléatoire en cookie `HttpOnly; Secure; SameSite=Strict`, empreinte stockée sur disque (plusieurs processus), 10 minutes sans activité. 3 mots de passe faux par IP : blocage 10 minutes.
- Toute action qui modifie (`POST`) exige la même origine (`Origin` ou `Referer` de `voix.bytechnum.com`), en plus du cookie `SameSite=Strict`.

### 6.5 Envoi des e-mails

- SMTP sur TLS (port 465) avec une boîte d'envoi `@bytechnum.com` chez Spacemail, comme le « mot de passe oublié » d'AgriFon (choix de conception, accepté). Identifiants saisis par Elisée en SSH (`scripts/admin.py smtp`), stockés en droits 600, jamais affichés.
- Expéditeur : la boîte d'envoi ; nom affiché « Voix fon ». E-mails en texte simple, en français.
- Six e-mails : annonce d'une demande (à Elisée), accès accordé (lien), refus, nouveau lien, code de mot de passe oublié, alerte de changement de mot de passe.
- Un échec d'envoi n'annule pas la décision : l'écran le dit, et « Nouveau lien » permet de renvoyer.

### 6.6 Quotas

- La limite par clé devient celle du projet (fichier des clés), et le plafond commun celui des réglages. Les décomptes existants (`quotas.json`) restent valables.
- Migration douce : un projet sans limite enregistrée prend 100 ; sans réglage, le plafond commun reste 300.

### 6.7 Sécurité de l'interface

- Pages `/admin`, `/demande` et `/acces` : `Content-Security-Policy` stricte (`default-src 'self'`, pas de script en ligne), `X-Frame-Options: DENY` (ou `frame-ancestors 'none'`), `noindex`, et les en-têtes déjà en place.
- L'API `/api/admin/*` répond en JSON ; aucune donnée de l'administration sans session valide.
- Jetons d'accès et de session : comparés par empreinte, en temps constant.

### 6.8 Choix faits à la relecture (à vérifier par Elisée)

- **Contact affiché sur la page publique** : `technum.services@bytechnum.com` (Elisée), et non le Gmail des réglages, qui reste privé.
- **Révoquer un projet** annule aussi son lien d'accès en attente.
- **Conservation** : les demandes refusées sont effacées après 90 jours ; celles approuvées restent avec le projet (nom, adresse, organisation), et sont effacées si Elisée supprime le projet.
- La police Montserrat et les feuilles de style sont servies par l'application (routes dédiées), jamais par un dossier `public/`.

### 6.9 Tests et documents

- Tests `unittest` pour chaque règle ci-dessus, avec un faux serveur SMTP (`smtplib` vers un serveur de test local, ou envoi remplacé par une fonction factice).
- README : section « Demander un accès » (lien vers `/demande`). EXPLOITATION.md : premier mot de passe, SMTP, gestion par l'écran.

## 7. Laissé au constructeur

- Organisation du code et des fichiers, noms internes.
- Mise en page exacte, dans le respect de la maquette et des couleurs.
- Formulation exacte des e-mails et des messages, en français, sans détail technique.
- Mécanisme exact des sessions partagées entre processus.

## 8. Étapes qui demandent Elisée

- Définir le premier mot de passe en SSH, puis saisir les identifiants de la boîte d'envoi.
- Fusionner les PR et donner l'accord de déploiement.
- Saisir l'adresse e-mail du projet `projet-collegue` s'il veut pouvoir lui envoyer un nouveau lien depuis l'écran.
