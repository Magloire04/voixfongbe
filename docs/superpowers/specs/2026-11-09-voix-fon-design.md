# Voix fon de Meta sur voix.bytechnum.com : conception

Date : 9 novembre 2026. Rédigée avec Elisée, qui a validé chaque point en conversation.
Dépôt : https://github.com/Magloire04/voixfongbe (créé par Elisée le 9 novembre 2026, public). Sous-domaine `voix.bytechnum.com` créé par Elisée le même jour (domaine additionnel, racine `~/voix.bytechnum.com`).

## 1. Intention

Un collègue d'Elisée prépare un projet proche d'AgriFon : une application qui répond à voix haute, en fon, pendant que l'utilisateur attend. Il a besoin d'une voix de synthèse fon accessible par Internet. Elisée a utilisé au début d'AgriFon la voix fon de Meta, MMS-TTS (`facebook/mms-tts-fon`), générée alors sur un PC. Le but est de faire tourner cette voix sur le serveur Spaceship d'Elisée, derrière une petite API protégée par clé, et de remettre au collègue un README qui lui permet de l'utiliser seul dans son projet.

Le besoin est celui d'une démonstration : moins d'une dizaine de phrases par jour, dites en direct.

## 2. Objectifs

- Une adresse, `https://voix.bytechnum.com`, qui transforme un texte fon en son (MP3 par défaut, WAV sur demande).
- Une réponse rapide alors que le service est presque toujours « froid » : l'hébergement arrête une application inutilisée au bout de quelques minutes, donc presque chaque demande la réveille.
- Un accès réservé aux projets autorisés, par une clé par projet.
- Un README en français pour le collègue, utilisable sans aide.

## 3. Non-objectifs

- D'autres langues que le fon (l'architecture ne doit pas l'empêcher plus tard, mais rien n'est prévu).
- Une page web pour essayer la voix.
- Des comptes utilisateurs, un tableau de bord, une facturation.
- Un usage commercial (interdit par la licence de la voix).

## 4. Anti-objectifs (ce qui serait un échec même si « ça marche »)

- Ralentir ou faire tomber les autres sites du compte (AgriFon, bytechnum.com, uacmap, oeil360finance, provia…) en consommant la mémoire partagée.
- Une clé exposée dans le navigateur des utilisateurs du collègue : n'importe qui pourrait alors utiliser le serveur.
- Un réveil si lent que la démonstration paraît en panne (plus de 5 secondes).
- Diffuser la voix sans sa licence et sa mention d'origine.
- Garder les textes envoyés dans des journaux (ils peuvent contenir des données personnelles).

## 5. Contraintes

- **Hébergement** : compte mutualisé Spaceship (`cqfjoztqtf@203.161.45.23`, port SSH 21098), CloudLinux avec CageFS, LiteSpeed, applications lancées par Passenger. Limites du compte, partagées par tous les sites : 3 Go de mémoire, 2 cœurs, 30 processus d'entrée simultanés, 200 processus, 50 Go de disque (1,6 utilisé), 500 000 fichiers (66 000 utilisés). Pas de processus permanent hors Passenger.
- **Python** : 3.10 à 3.13 disponibles (le service tourne en 3.13 sur le serveur ; sur le PC d'Elisée, tests en 3.14 et outils de conversion en 3.10) par « Setup Python App » (`cloudlinux-selector --interpreter=python`). glibc 2.28. Pas de ffmpeg sur le serveur.
- **Licence de la voix** : CC BY-NC 4.0. Usage non commercial uniquement, attribution obligatoire. Le service la rappelle dans ses réponses et le README l'impose au collègue.
- **Secrets** : restent sur le serveur, jamais dans Git ni dans le chat. Fichiers de secrets en droits 600.
- **Git** : messages au nom d'Elisée seul, sans aucune trace d'outil d'IA. Elisée fusionne les PR lui-même. Déploiement seulement sur son accord explicite.
- **Langue** : README, messages d'erreur et documentation en français.

## 6. Décisions prises

Chaque point indique qui l'a tranché : « Elisée » (validé en conversation) ou « choix de conception » (proposé, présenté à Elisée, accepté sans modification).

### 6.1 Le modèle et son moteur

- **Modèle officiel `facebook/mms-tts-fon`** (Elisée). Le modèle tiers `Devsyril/mms-tts-fon-sherpa-onnx` publié sur Hugging Face n'est pas utilisé : origine inconnue, jamais téléchargé.
- **Conversion en ONNX sur le PC d'Elisée, exécution avec onnxruntime sur le serveur, sans PyTorch** (choix de conception, accepté). Raison : avec PyTorch, environ 1 Go de mémoire et 10 à 15 s de réveil par processus ; avec ONNX, de l'ordre de 200 à 300 Mo et 1 à 2 s. Conversion par l'export officiel de Hugging Face (`optimum-onnx`, tâche `text-to-audio`, classe `VitsOnnxConfig`).
- **Vérification de fidélité avant toute mise en ligne** : sur le PC, comparer la sortie ONNX à celle de PyTorch (`transformers.VitsModel`) sur une dizaine de phrases fon. La synthèse VITS est aléatoire ; la comparaison se fait donc avec le bruit neutralisé (`noise_scale` et `noise_scale_duration` à 0 des deux côtés), puis à l'écoute avec les réglages normaux. Si l'ONNX s'écarte (durées ou formes d'onde différentes au-delà du bruit numérique), on repasse à PyTorch sur le serveur et on revoit les mesures de la section 6.6.
- Réglages du modèle : 16 kHz, `noise_scale` 0,667, `noise_scale_duration` 0,8, `speaking_rate` 1 (valeurs de `config.json`, gardées).
- Le fichier ONNX (environ 145 Mo) n'entre pas dans Git. Il est copié sur le serveur hors du dépôt, avec son empreinte SHA-256 vérifiée par le service au démarrage.

### 6.2 La préparation du texte

- Reproduire exactement le `VitsTokenizer` du modèle, sans installer `transformers` sur le serveur : mise en minuscules, caractères absents de `vocab.json` retirés, puis un symbole de remplissage (`_`, identifiant 0) intercalé entre chaque symbole et aux deux bouts (`add_blank: true`). Pas de romanisation (`is_uroman: false`).
- Avant cela, la préparation d'AgriFon (`scripts/voix/generer.py`, commit `cfc74a2` du dépôt `demo_agriculture`) : normalisation NFC ; un caractère du vocabulaire est gardé tel quel ; sinon il est décomposé et on garde la lettre de base avec seulement les accents connus en combinaison (aigu U+0301, caron U+030C) ; la ponctuation `.,;:?!` devient une espace. Le vocabulaire compte 46 symboles, dont `è`, `ì`, `é`, `ɔ`, `ɖ`, `ɛ` et des voyelles à caron.
- Un texte vide après préparation est refusé (400).
- Un jeu de phrases de référence, préparé sur le PC avec le vrai `VitsTokenizer`, sert de test : le service doit produire exactement les mêmes identifiants.

### 6.3 L'API

- **Adresse** : `https://voix.bytechnum.com` (choix de conception, accepté). Sous-domaine à créer dans cPanel, certificat Let's Encrypt automatique.
- `POST /v1/synthese`
  - En-tête `Authorization: Bearer <clé>`.
  - Corps JSON : `{"texte": "...", "format": "mp3"}` ; `format` vaut `mp3` (défaut) ou `wav`. Corps de 8 Ko au plus.
  - Réponse 200 : le son (`audio/mpeg` ou `audio/wav`), en-têtes `X-Voix-Licence: MMS-TTS de Meta, CC BY-NC 4.0` et `X-Voix-Cache: oui|non`.
- `GET /v1/etat` (sans clé) : `{ "service": "voix fon", "version": "...", "modele": "facebook/mms-tts-fon", "licence": "CC BY-NC 4.0", "pret": true }`. Ne révèle ni clés, ni quotas, ni chemins.
- Erreurs en JSON `{ "erreur": "<phrase en français>", "code": "<code>" }` :
  - 400 `json_invalide`, `texte_absent`, `texte_vide`, `texte_trop_long`, `format_inconnu` ;
  - 401 `cle_absente`, `cle_invalide` ;
  - 404, 405 ;
  - 413 `corps_trop_grand` ;
  - 429 `quota_jour`, avec `Retry-After` jusqu'à minuit (heure de Porto-Novo) ;
  - 503 `modele_indisponible` (fichier ONNX absent ou empreinte fausse) ;
  - 500 `erreur_interne`, sans détail technique dans la réponse.
- **Pas de CORS** (choix de conception) : le navigateur des utilisateurs du collègue ne peut pas appeler le service directement. Les appels se font depuis le serveur du collègue, où la clé reste cachée. Le README l'explique avec un exemple de relais.

### 6.4 Clés, limites, cache, journal

- **Une clé par projet** (Elisée). Créée sur le serveur par un script en SSH : 32 octets aléatoires (`secrets.token_urlsafe`), affichée une seule fois dans le terminal d'Elisée, qui la transmet lui-même au collègue. Le serveur ne garde que son empreinte SHA-256, avec le nom du projet et la date, dans un fichier de stockage en droits 600. Le même script liste les projets et révoque une clé. Comparaison des empreintes en temps constant.
- **Limites par clé** (choix de conception, accepté) : 1 000 caractères par demande (comptés avant préparation), 100 demandes par jour (jour de Porto-Novo, UTC+1). Une réponse servie depuis le cache compte dans le quota.
- **Cache** (choix de conception, accepté) : un son déjà fabriqué est gardé sur disque, nommé par l'empreinte SHA-256 de (version du modèle, format, texte préparé). Taille totale plafonnée à 200 Mo, les plus anciens effacés d'abord. La synthèse étant aléatoire, la première version d'une phrase devient sa version définitive tant qu'elle est en cache.
- **Journal** : une ligne JSON par demande (date, projet, nombre de caractères, format, durée de synthèse, cache oui/non, code de résultat). Jamais le texte. Effacé après 90 jours.
- **Écritures sur disque** : chaque fichier de stockage est écrit dans un fichier temporaire puis renommé ; une file d'écriture qui survit à une erreur (le défaut connu de `server/signalement.js` dans AgriFon ne doit pas être reproduit). Plusieurs processus Passenger peuvent tourner : les compteurs de quota doivent rester justes (verrou de fichier ou équivalent).

### 6.5 Sécurité de l'application

- HTTPS seulement : redirection depuis HTTP, en-tête `Strict-Transport-Security`.
- En-têtes : `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` sur les erreurs.
- Les fichiers du dépôt, du modèle et du stockage ne sont jamais servis comme fichiers statiques (piège connu de Passenger sur ce serveur : il sert tout dossier `public/` sans passer par l'application ; ne pas en créer).
- `robots.txt` et `X-Robots-Tag: noindex`.
- Délai maximal de synthèse par demande ; au-delà, 503.

### 6.6 Mesures attendues

À mesurer sur le serveur après le premier déploiement, et à noter dans le README :

| Mesure | Cible |
| --- | --- |
| Réveil (première demande après arrêt), phrase de 100 caractères | moins de 3 s |
| Phrase de 100 caractères, service déjà réveillé | moins de 2 s |
| Mémoire par processus | moins de 400 Mo |

Si une cible n'est pas tenue, l'écrire franchement dans le README plutôt que de la cacher.

### 6.7 Code, dépôt, déploiement

- **Nouveau dépôt GitHub, séparé d'AgriFon** (choix de conception, accepté) : `Magloire04/voixfongbe`, créé par Elisée.
- Application WSGI sans framework (fichier `passenger_wsgi.py`), Python 3.13. Dépendances du serveur réduites à `onnxruntime`, `numpy` et `lameenc`. Les outils de conversion (`optimum-onnx`, `torch`, `transformers`) ne servent que sur le PC, dans un fichier de dépendances à part.
- Dossier sur le serveur : `~/voixfongbe-app`, application déclarée avec `cloudlinux-selector`. Script de déploiement inspiré de `scripts/deployer.sh` d'AgriFon : récupérer le code, installer les dépendances, vérifier le modèle, redémarrer, appeler `/v1/etat`.
- **Tests** avec `unittest` (bibliothèque standard) : préparation du texte et identifiants (contre le jeu de référence), API (clés, quotas, limites, formats, erreurs, en-têtes), cache, journal sans texte, survie de la file d'écriture à une erreur. La comparaison ONNX contre PyTorch est un outil du PC, hors de la suite de tests du serveur.

### 6.8 Le README pour le collègue

En français, pour un développeur qui ne connaît ni le serveur ni AgriFon :

1. À quoi sert le service, et pour quel usage (non commercial).
2. Adresse, obtention de la clé (auprès d'Elisée), où la ranger (variable d'environnement de son serveur, jamais dans le code du navigateur).
3. Exemples prêts à copier : `curl`, JavaScript (Node, `fetch`), Python (`requests` ou `urllib`), PHP. Plus un exemple de relais : le navigateur appelle le serveur du collègue, qui appelle la voix.
4. Format des réponses, en-têtes, codes d'erreur et quoi faire pour chacun.
5. Limites (1 000 caractères, 100 demandes par jour), temps de réponse mesurés, cache.
6. Écrire le fon pour la voix : caractères reconnus, accents gardés ou retirés, ponctuation qui fait une pause, conseils tirés de l'expérience d'AgriFon (couper les longues réponses en phrases).
7. Licence et mention obligatoire : « Voix : MMS-TTS de Meta (CC BY-NC 4.0) », avec le lien vers la fiche du modèle.
8. Contact et état du service (`/v1/etat`).

### 6.9 Choix faits à la relecture (choix de conception, à vérifier par Elisée)

- **Dépôt public** (créé ainsi par Elisée ; la conception prévoyait un dépôt privé). Sans risque : il ne contient ni secret ni modèle. Le collègue peut lire le README directement sur GitHub.
- **Deux documents** : `README.md` est le guide du collègue (utiliser l'API) ; `EXPLOITATION.md` sert à Elisée (déployer, créer et révoquer des clés, lire le journal, remplacer le modèle).
- **Contact dans le README** : « Elisée, qui vous a transmis la clé ». Aucune adresse e-mail publiée dans le document.
- **Délai maximal de synthèse** : 30 s par demande.
- **Plafond global** : 300 demandes par jour, toutes clés confondues, en plus des 100 par clé.
- **MP3** : mono, 16 kHz, 48 kbit/s.
- **Export ONNX** : si l'export officiel fige les réglages de bruit dans le graphe, la comparaison du §6.1 se fait en exportant une seconde fois, pour le test seulement, avec le bruit à 0. Si ce n'est pas possible, on compare les durées des phrases et on écoute les deux versions.

## 7. Ce qui est laissé au constructeur

- L'organisation interne du code et le nom des fichiers et fonctions.
- La façon exacte de garder les compteurs justes entre processus.
- La formulation exacte des messages d'erreur, tant qu'ils restent en français et sans détail technique.
- Le réglage du nombre de fils d'exécution d'onnxruntime (2 cœurs au total pour le compte).

## 8. Étapes qui demandent Elisée

- Dépôt `voixfongbe` et sous-domaine `voix.bytechnum.com` : faits par Elisée le 9 novembre 2026.
- Accepter la déclaration de l'application Python sur le serveur et l'envoi du modèle.
- Lancer le script de création de clé en SSH et transmettre la clé au collègue.
- Fusionner les PR et donner l'accord de déploiement.
