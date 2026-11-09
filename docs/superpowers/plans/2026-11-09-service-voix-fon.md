# Service voix fon (MMS-TTS en ONNX) : plan de réalisation

> **Pour l'exécutant :** suivre superpowers:executing-plans (ou subagent-driven-development) tâche par tâche. Les étapes sont des cases à cocher.

**But :** mettre en ligne sur `https://voix.bytechnum.com` une API protégée par clé qui transforme un texte fon en MP3 ou WAV avec la voix MMS-TTS de Meta convertie en ONNX, et remettre au collègue d'Elisée un README autonome.

**Architecture :** sur le PC d'Elisée, des outils convertissent `facebook/mms-tts-fon` en ONNX et vérifient sa fidélité. Sur le serveur, une application WSGI sans framework (Passenger) prépare le texte, fait la synthèse avec onnxruntime, encode en MP3 avec lameenc, et gère clés, quotas, cache et journal dans des fichiers JSON protégés par verrou.

**Outils :** Python 3.13 (serveur), Python 3.14 (tests sur le PC), Python 3.10 (outils de conversion sur le PC) ; `onnxruntime==1.31.1`, `numpy==2.5.4`, `lameenc==1.9.0` ; tests `unittest`.

**Conception :** `docs/superpowers/specs/2026-11-09-voix-fon-design.md` (à lire avant de commencer : elle fait foi).

## Contraintes globales

- Dépendances du serveur limitées à `onnxruntime==1.31.1`, `numpy==2.5.4`, `lameenc==1.9.0` (`requirements.txt`). `torch`, `transformers`, `optimum-onnx` seulement dans `outils/requirements.txt`.
- Code compatible Python 3.13 et 3.14. Aucun framework web.
- Textes visibles (README, erreurs, messages des scripts) en français. Identifiants du code en français, comme AgriFon.
- Licence de la voix : CC BY-NC 4.0, mention « Voix : MMS-TTS de Meta (CC BY-NC 4.0) ». Code du dépôt sous licence MIT.
- Le modèle (`modele/`) et le stockage (`stockage/`) ne vont jamais dans Git. Fichiers de stockage en droits 600.
- Aucun dossier `public/` dans l'application : sur ce serveur, Passenger sert ce dossier sans passer par l'application, donc sans contrôle.
- Jamais le texte reçu dans un journal. Jamais une clé en clair ailleurs que dans la sortie du script de création.
- Git : messages au nom d'Elisée seul, aucune trace d'outil d'IA (pas de `Co-Authored-By`, pas de « Generated with »). Elisée fusionne les PR. Rien n'est poussé ni déployé sans son accord explicite.
- Sur le PC, pip passe par l'antivirus Avast : définir `PIP_CERT`, `REQUESTS_CA_BUNDLE` et `SSL_CERT_FILE` vers un fichier qui concatène le `cacert.pem` de certifi et `C:\ProgramData\Avast Software\Avast\wscert.pem`.
- Serveur : `cqfjoztqtf@203.161.45.23`, port 21098, clé `~/.ssh/id_ed25519_uacmap`. Application dans `~/voixfongbe-app`, domaine `voix.bytechnum.com`.
- Valeurs fixées par la conception : 1 000 caractères par demande (comptés avant préparation) ; 100 demandes par jour et par clé ; 300 par jour en tout ; jour de Porto-Novo (UTC+1) ; corps de 8 192 octets au plus ; 30 s de synthèse au plus ; cache de 200 Mo ; journal gardé 90 jours ; MP3 mono 16 kHz 48 kbit/s.

## Points de vigilance de la relecture

Cas que la conception implique sans les nommer ; chacun a son test dans la tâche indiquée.

1. Un texte qui ne contient que des chiffres, de la ponctuation, des émojis ou des lettres hors vocabulaire (`q`, `r`) devient vide après préparation : réponse 400 `texte_vide`, pas un son muet (tâche 2 et tâche 6).
2. Les chiffres disparaissent sans prévenir (« 300 F » n'est pas dit) : l'en-tête `X-Voix-Caracteres-Ignores` donne le nombre de caractères retirés, et le README dit d'écrire les nombres en toutes lettres en fon (tâche 6 et tâche 7).
3. Deux processus Passenger qui servent en même temps ne doivent ni perdre ni doubler un décompte de quota (tâche 5).
4. Le même texte en Unicode composé (NFC) ou décomposé (NFD) donne les mêmes identifiants, donc la même entrée de cache (tâche 2).
5. Modèle absent ou abîmé sur le serveur : `/v1/etat` dit `"pret": false` et `/v1/synthese` répond 503 `modele_indisponible`, sans plantage (tâche 3 et tâche 6).

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `voixfongbe/texte.py` | préparation du texte et identifiants (reproduit `VitsTokenizer`) |
| `voixfongbe/moteur.py` | chargement du modèle ONNX, vérification d'empreinte, synthèse |
| `voixfongbe/audio.py` | encodage WAV et MP3 |
| `voixfongbe/stockage.py` | écriture JSON atomique, verrou de fichier |
| `voixfongbe/cles.py` | clés par projet (empreintes SHA-256) |
| `voixfongbe/quotas.py` | quotas par jour |
| `voixfongbe/cache.py` | cache des sons sur disque |
| `voixfongbe/journal.py` | journal sans texte, purge à 90 jours |
| `voixfongbe/config.py` | réglages |
| `voixfongbe/app.py` | application WSGI : routes, erreurs, en-têtes |
| `passenger_wsgi.py` | point d'entrée Passenger |
| `scripts/cles.py` | créer, lister, révoquer une clé (SSH) |
| `scripts/deployer.sh` | déploiement sur le serveur |
| `outils/convertir.py`, `outils/fidelite.py`, `outils/reference_identifiants.py`, `outils/requirements.txt` | outils du PC |
| `tests/aides.py` | `MoteurFactice` et appel WSGI de test |
| `tests/test_*.py`, `tests/donnees/` | tests et données de référence |
| `README.md`, `EXPLOITATION.md`, `LICENSE`, `requirements.txt`, `.gitignore` | documents et réglages |

---

### Tâche 0 : dépôt initial

- [ ] **Étape 1 :** dans `C:\wamp64\www\voixfongbe` (clone vide de `Magloire04/voixfongbe`), créer `.gitignore` : `modele/`, `modele-test/`, `stockage/`, `fidelite/`, `.venv*/`, `__pycache__/`, `*.pyc`.
- [ ] **Étape 2 :** premier commit sur `main` avec `.gitignore`, la conception et ce plan : `docs: add design and plan for the fon voice service`.
- [ ] **Étape 3 :** avec l'accord d'Elisée, `git push -u origin main`, puis créer la branche `feature/service-voix` pour toutes les tâches suivantes.

### Tâche 1 : conversion ONNX et vérification de fidélité (PC)

Porte d'entrée du projet : si la fidélité échoue, s'arrêter et revenir vers Elisée (repli PyTorch, conception §6.1).

**Fichiers :** créer `outils/requirements.txt`, `outils/convertir.py`, `outils/fidelite.py`.

**Produit :** `modele/model.onnx`, `modele/vocab.json`, `modele/empreinte.txt` (empreinte SHA-256 hexadécimale de `model.onnx`, une ligne) ; `modele-test/model.onnx` (bruit nul) ; rapport de fidélité.

- [ ] **Étape 1 :** `py -3.10 -m venv .venv-outils`, puis installer `outils/requirements.txt` : `torch` (CPU), `transformers`, `optimum-onnx`, `onnx`, `onnxruntime`, `numpy`, `scipy`.
- [ ] **Étape 2 :** `outils/convertir.py [--bruit-nul]` : export par `optimum.exporters.onnx.main_export(model_name_or_path="facebook/mms-tts-fon", task="text-to-audio", output=...)` vers `modele/`. Copier `vocab.json`, écrire `empreinte.txt`. Avec `--bruit-nul` : sauvegarder une copie locale du modèle avec `noise_scale` et `noise_scale_duration` à 0 dans `config.json`, l'exporter vers `modele-test/`.
- [ ] **Étape 3 :** afficher les entrées et sorties du graphe (`onnxruntime.InferenceSession(...).get_inputs()/get_outputs()`) et les noter dans le rapport : la tâche 3 s'appuie sur ces noms.
- [ ] **Étape 4 :** `outils/fidelite.py` : pour 10 phrases de `tests/donnees/phrases.txt` (créé en tâche 2, étape 1 ; le créer ici s'il manque), comparer `transformers.VitsModel` (bruit à 0) et `modele-test/model.onnx`. Critère : même nombre d'échantillons et écart absolu maximal inférieur à 1e-3. Écrire aussi, avec les réglages normaux, une paire de WAV par phrase dans `fidelite/` pour l'écoute.
- [ ] **Étape 5 :** lancer les deux scripts. Attendu : 10 phrases sur 10 conformes. Faire écouter trois paires à Elisée. Si l'export fige le bruit et empêche le bruit nul, appliquer le repli de la conception §6.9 (durées et écoute).
- [ ] **Étape 6 :** commit `feat(tools): convert the mms fon voice to onnx and check fidelity`.

### Tâche 2 : préparation du texte et identifiants

**Fichiers :** créer `voixfongbe/__init__.py`, `voixfongbe/texte.py`, `outils/reference_identifiants.py`, `tests/donnees/phrases.txt`, `tests/donnees/vocab.json` (copie de `modele/vocab.json`), `tests/donnees/reference_identifiants.json`, `tests/test_texte.py`.

**Produit :**
- `charger_vocabulaire(chemin: Path) -> dict[str, int]`
- `preparer(texte: str, vocabulaire: Mapping[str, int]) -> str`
- `identifiants(texte_prepare: str, vocabulaire: Mapping[str, int]) -> list[int]`
- `caracteres_ignores(texte: str, vocabulaire: Mapping[str, int]) -> int` : nombre de caractères du texte d'origine (après NFC, hors espaces et ponctuation `.,;:?!`) qui ne laissent aucun symbole dans le texte préparé.

- [ ] **Étape 1 :** `tests/donnees/phrases.txt`, une phrase par ligne, au moins 30 : les phrases fon de `data/tour.json`, `data/reponses.json` et `data/solutions.json` du dépôt `demo_agriculture`, plus des cas limites : majuscules, texte en NFD, ponctuation, `q` et `r`, chiffres, émoji, `đ`, accent grave sur `ɔ`, voyelles à caron, espaces multiples, une ligne qui devient vide.
- [ ] **Étape 2 :** `outils/reference_identifiants.py` (dans `.venv-outils`) : pour chaque phrase, `preparer()` puis `VitsTokenizer.from_pretrained("facebook/mms-tts-fon")(...).input_ids`, écrits dans `reference_identifiants.json` (`[{"phrase", "preparee", "identifiants"}]`). Ce fichier, versionné, est la référence.
- [ ] **Étape 3 :** écrire les tests (ils échouent tant que `texte.py` n'existe pas) :

```python
def test_identiques_au_tokenizer_de_reference(self):
    for cas in REFERENCE:
        self.assertEqual(identifiants(preparer(cas["phrase"], VOCAB), VOCAB), cas["identifiants"], cas["phrase"])

def test_nfd_et_nfc_donnent_le_meme_texte(self):
    self.assertEqual(preparer(unicodedata.normalize("NFD", "Mi kú abɔ ɖo AgriFon ji."), VOCAB),
                     preparer("Mi kú abɔ ɖo AgriFon ji.", VOCAB))

def test_ponctuation_devient_espace_unique(self):
    self.assertEqual(preparer("Mi zìn,  fí élɔ !", VOCAB), "mi zìn fí élɔ")

def test_texte_sans_symbole_connu_devient_vide(self):
    self.assertEqual(preparer("300 ? 🙂 qr", VOCAB), "")

def test_caracteres_ignores_compte_les_chiffres(self):
    self.assertEqual(caracteres_ignores("È nɔ sa 300 F", VOCAB), 3)
```

`VOCAB` est lu dans `tests/donnees/vocab.json`, copie de `modele/vocab.json` versionnée pour les tests. Avant d'écrire la valeur attendue de `test_ponctuation_devient_espace_unique`, vérifier dans `reference_identifiants.json` ce que donne le vrai tokenizer pour l'accent grave de `zì`.

- [ ] **Étape 4 :** lancer `py -3.14 -m unittest tests.test_texte -v`. Attendu : échec à l'import.
- [ ] **Étape 5 :** écrire `texte.py`. `preparer` : la règle d'AgriFon (`scripts/voix/generer.py`, commit `cfc74a2` de `demo_agriculture`), en minuscules et NFC ; garder un caractère présent dans le vocabulaire ; sinon le décomposer et garder la lettre de base suivie des seuls accents U+0301 et U+030C, si la base est connue ; `.,;:?!` devient une espace ; tout le reste disparaît ; plusieurs espaces deviennent une seule ; espaces retirées aux bouts. `identifiants` : un symbole par caractère, puis `0` intercalé entre chaque symbole et aux deux bouts (`add_blank`).
- [ ] **Étape 6 :** relancer. Attendu : tous les tests passent.
- [ ] **Étape 7 :** commit `feat(text): prepare fon text and build voice token ids`.

### Tâche 3 : moteur ONNX et encodage

**Fichiers :** créer `voixfongbe/moteur.py`, `voixfongbe/audio.py`, `tests/test_moteur.py`, `tests/test_audio.py`, `requirements.txt`.

**Consomme :** les noms d'entrées et de sorties notés en tâche 1, étape 3.

**Produit :**
- `class ModeleIndisponible(Exception)`
- `class Moteur(dossier_modele: Path, fils: int = 2)`, avec :
  - `pret() -> bool` (fichiers présents et empreinte juste, vérifiée une fois puis gardée) ;
  - `vocabulaire -> dict[str, int]` ;
  - `version -> str` (12 premiers caractères de l'empreinte) ;
  - `synthetiser(ids: list[int]) -> numpy.ndarray` : `float32`, mono, 16 000 Hz. Lève `ModeleIndisponible` si pas prêt. Session onnxruntime créée au premier appel, `intra_op_num_threads=fils`, `inter_op_num_threads=1`. Fournit `attention_mask` (des 1) si le graphe l'attend.
- `TAUX = 16000`
- `en_wav(echantillons: numpy.ndarray, taux: int = TAUX) -> bytes` : PCM 16 bits, écrêté à [-1, 1].
- `en_mp3(echantillons: numpy.ndarray, taux: int = TAUX, debit_kbps: int = 48) -> bytes` : lameenc, mono.

- [ ] **Étape 1 :** `requirements.txt` avec les trois versions fixées ; `py -3.14 -m venv .venv` et installation.
- [ ] **Étape 2 :** tests :

```python
def test_empreinte_fausse_rend_le_moteur_indisponible(self):   # faux model.onnx, empreinte d'un autre contenu
    self.assertFalse(Moteur(dossier).pret())
    with self.assertRaises(ModeleIndisponible): Moteur(dossier).synthetiser([0, 5, 0])

def test_dossier_vide_rend_le_moteur_indisponible(self):
    self.assertFalse(Moteur(dossier_vide).pret())

@unittest.skipUnless(MODELE_REEL.exists(), "modèle absent")
def test_vraie_synthese_donne_un_son_de_16_khz(self):
    son = Moteur(MODELE_REEL).synthetiser(identifiants(preparer("Mi kú abɔ.", VOCAB), VOCAB))
    self.assertEqual(son.dtype, numpy.float32); self.assertGreater(len(son), 16000 * 0.3)

def test_wav_a_le_bon_entete(self):
    wav = en_wav(numpy.zeros(16000, numpy.float32))
    self.assertEqual(wav[:4], b"RIFF"); self.assertEqual(struct.unpack("<I", wav[24:28])[0], 16000)

def test_mp3_commence_par_une_trame_mp3(self):
    mp3 = en_mp3(numpy.sin(numpy.linspace(0, 2000, 16000)).astype(numpy.float32))
    self.assertTrue(mp3[:3] == b"ID3" or (mp3[0] == 0xFF and mp3[1] & 0xE0 == 0xE0))
```

- [ ] **Étape 3 :** lancer, constater l'échec, écrire `moteur.py` et `audio.py`, relancer. Attendu : tout passe (le test du vrai modèle tourne sur le PC, où `modele/` existe).
- [ ] **Étape 4 :** commit `feat(engine): run the onnx voice and encode wav and mp3`.

### Tâche 4 : stockage et clés

**Fichiers :** créer `voixfongbe/stockage.py`, `voixfongbe/cles.py`, `scripts/cles.py`, `tests/test_stockage.py`, `tests/test_cles.py`.

**Produit :**
- `ecrire_json(chemin: Path, donnees) -> None` : fichier temporaire dans le même dossier, `os.replace`, droits 600 (sous Windows, droits ignorés).
- `lire_json(chemin: Path, defaut)`
- `verrou(chemin: Path)` : gestionnaire de contexte, verrou exclusif sur `<chemin>.verrou` (`fcntl.flock` sous Linux, `msvcrt.locking` sous Windows).
- `class Cles(chemin: Path)`, avec :
  - `creer(projet: str) -> str` : nom `^[a-z0-9-]{2,40}$`, sinon `ValueError` ; projet déjà présent : `ValueError` ;
  - `verifier(cle: str) -> str | None` : nom du projet, ou `None` ;
  - `revoquer(projet: str) -> bool` ;
  - `lister() -> list[dict]` (`projet`, `cree_le`).

  Format du fichier : `{"projets": {"<projet>": {"empreinte": "<sha256 hex>", "cree_le": "<ISO 8601>"}}}`. La clé vaut `secrets.token_urlsafe(32)`. La vérification se fait avec `hmac.compare_digest` sur l'empreinte, sur tous les projets.

- `scripts/cles.py creer <projet> [--brut] | lister | revoquer <projet>`, sur le dossier de `Config.depuis_env`. `creer` affiche la clé une fois, avec la consigne de la transmettre de façon privée. `--brut` n'affiche que la clé, pour un usage par variable de shell.

- [ ] **Étape 1 :** tests : `test_cle_creee_est_reconnue`, `test_cle_inconnue_rend_none`, `test_fichier_ne_contient_pas_la_cle_en_clair`, `test_revoquer_rend_la_cle_inutilisable`, `test_nom_de_projet_invalide_refuse` (`"Mon Projet"`, `"a"`), `test_projet_en_double_refuse`, `test_ecriture_atomique_ne_laisse_pas_de_fichier_temporaire`, `test_ecrit_en_droits_600` (ignoré sous Windows).
- [ ] **Étape 2 :** lancer, constater l'échec, écrire le code, relancer. Attendu : tout passe.
- [ ] **Étape 3 :** commit `feat(keys): store project keys as sha-256 hashes`.

### Tâche 5 : quotas, cache, journal

**Fichiers :** créer `voixfongbe/quotas.py`, `voixfongbe/cache.py`, `voixfongbe/journal.py` et leurs tests.

**Consomme :** `ecrire_json`, `lire_json`, `verrou` (tâche 4).

**Produit :**
- `FUSEAU = timezone(timedelta(hours=1))`
- `class Quotas(chemin: Path, par_cle: int = 100, total: int = 300)` :
  - `consommer(projet: str, maintenant: datetime) -> int | None` : `None` si la demande passe (compteurs augmentés), sinon le nombre de secondes jusqu'au prochain minuit de Porto-Novo ;
  - ne garde que le jour en cours ; tout se fait sous `verrou`.
- `class Cache(dossier: Path, plafond: int = 200 * 1024 * 1024)` :
  - `cle(version: str, format: str, texte_prepare: str) -> str` (statique) : SHA-256 de `f"{version}\n{format}\n{texte_prepare}"` ;
  - `lire(cle: str) -> bytes | None` : remet à jour la date du fichier à chaque lecture ;
  - `ecrire(cle: str, donnees: bytes) -> None` : écriture atomique, puis suppression des fichiers les plus anciens jusqu'à repasser sous le plafond.
- `class Journal(dossier: Path, jours: int = 90)` :
  - `noter(*, projet: str | None, caracteres: int, format: str | None, duree_ms: int, cache: bool, code: int, maintenant: datetime) -> None` ;
  - une ligne JSON dans `journal-AAAA-MM-JJ.jsonl` (date de Porto-Novo) ; purge des fichiers de plus de `jours` jours, au plus une fois par jour et par processus.

- [ ] **Étape 1 :** tests :

```python
def test_centieme_demande_passe_la_suivante_attend_minuit(self):
    q = Quotas(f, par_cle=100, total=300); t = datetime(2026, 11, 9, 22, 30, tzinfo=FUSEAU)
    for _ in range(100): self.assertIsNone(q.consommer("demo", t))
    self.assertEqual(q.consommer("demo", t), 5400)

def test_compteurs_repartent_le_lendemain(self): ...      # 101e refusée à 23:59, acceptée à 00:01

def test_plafond_total_tous_projets(self): ...            # total=3 : a, b, c passent, d refusé

def test_deux_processus_ne_perdent_aucun_decompte(self):
    # multiprocessing : 2 processus x 50 consommer("demo") sur le même fichier -> compteur final 100
```

Ajouter aussi `test_cache_meme_texte_meme_cle`, `test_cache_purge_les_plus_anciens` (plafond 10 octets, trois écritures de 6 octets : seule la dernière reste), `test_journal_ne_contient_jamais_le_texte` (la ligne écrite n'a que les champs de `noter`), `test_journal_purge_apres_90_jours`.

- [ ] **Étape 2 :** lancer, constater l'échec, écrire le code, relancer. Attendu : tout passe.
- [ ] **Étape 3 :** commit `feat(storage): daily quotas, audio cache and text-free log`.

### Tâche 6 : application WSGI

**Fichiers :** créer `voixfongbe/config.py`, `voixfongbe/app.py`, `passenger_wsgi.py`, `tests/aides.py`, `tests/test_app.py`.

**Consomme :** tout ce qui précède.

**Produit :**
- `@dataclass(frozen=True) class Config`, avec les champs `racine`, `dossier_modele`, `dossier_stockage`, `fils=2`, `max_caracteres=1000`, `par_cle=100`, `total_jour=300`, `delai_s=30.0`, `plafond_cache=200*1024*1024`, `max_corps=8192`. `Config.depuis_env(racine: Path) -> Config` lit `VOIX_MODELE_DIR` (défaut `racine/"modele"`), `VOIX_STOCKAGE_DIR` (défaut `racine/"stockage"`) et `VOIX_FILS`.
- `creer_application(config: Config, moteur=None, horloge=None) -> Callable` : application WSGI. `moteur` vaut par défaut `Moteur(config.dossier_modele, config.fils)` ; `horloge` vaut par défaut l'heure UTC actuelle.
- `passenger_wsgi.py` : `application = creer_application(Config.depuis_env(Path(__file__).resolve().parent))`.
- `tests/aides.py` :
  - `MoteurFactice(pret=True, delai_s=0.0)`, même interface que `Moteur`. `synthetiser` rend une sinusoïde de `160 * len(ids)` échantillons après `delai_s` ;
  - `appeler(app, methode, chemin, corps=None, entetes=None) -> (statut: int, entetes: dict, corps: bytes)`.

**Comportement fixé** (ordre des contrôles pour `POST /v1/synthese`) :
1. Route inconnue : 404 `introuvable`. Mauvaise méthode : 405 `methode` avec `Allow`.
2. `X-Forwarded-Proto: http` : 301 vers la même adresse en `https://`.
3. Clé : en-tête `Authorization`, schéma `Bearer` sans tenir compte de la casse. Absente : 401 `cle_absente` ; inconnue : 401 `cle_invalide`.
4. Corps plus grand que `max_corps` : 413 `corps_trop_grand`.
5. JSON illisible : 400 `json_invalide`. `texte` absent ou pas une chaîne : 400 `texte_absent`. Plus de `max_caracteres` caractères : 400 `texte_trop_long`. `format` autre que `mp3` ou `wav` : 400 `format_inconnu`.
6. Quota : 429 `quota_jour` avec `Retry-After`.
7. Moteur pas prêt : 503 `modele_indisponible`.
8. Texte vide après préparation : 400 `texte_vide`.
9. Son en cache : réponse immédiate. Sinon synthèse dans un `ThreadPoolExecutor(max_workers=1)` du processus, `result(timeout=delai_s)` ; au-delà, 503 `delai_depasse`. Puis encodage et mise en cache.
10. Réponse 200 avec `Content-Type` (`audio/mpeg` ou `audio/wav`), `Content-Length`, `X-Voix-Licence: MMS-TTS de Meta, CC BY-NC 4.0`, `X-Voix-Cache: oui|non`, `X-Voix-Caracteres-Ignores: <n>`.
11. Toute exception imprévue : 500 `erreur_interne`, sans détail dans la réponse. Chaque demande passée par `/v1/synthese` est notée au journal, sans le texte.

Pour toutes les réponses : `Strict-Transport-Security: max-age=31536000`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex, nofollow`. Erreurs en JSON `{"erreur": "<phrase en français>", "code": "<code>"}` avec `Cache-Control: no-store`. `GET /v1/etat` répond `{"service": "voix fon", "version": <version du moteur ou null>, "modele": "facebook/mms-tts-fon", "licence": "CC BY-NC 4.0", "pret": <bool>}`. `GET /robots.txt` répond `User-agent: *` puis `Disallow: /`. Aucune réponse n'a d'en-tête `Access-Control-Allow-Origin`.

- [ ] **Étape 1 :** tests, un par ligne du comportement fixé, plus :

```python
def test_meme_texte_deux_fois_vient_du_cache(self):
    _, e1, c1 = appeler(app, "POST", "/v1/synthese", {"texte": "Mi kú abɔ."}, CLE)
    _, e2, c2 = appeler(app, "POST", "/v1/synthese", {"texte": "MI KÚ ABƆ !"}, CLE)
    self.assertEqual((e1["X-Voix-Cache"], e2["X-Voix-Cache"]), ("non", "oui")); self.assertEqual(c1, c2)

def test_chiffres_signales_dans_l_entete(self):
    _, e, _ = appeler(app, "POST", "/v1/synthese", {"texte": "È nɔ sa 300 F"}, CLE)
    self.assertEqual(e["X-Voix-Caracteres-Ignores"], "3")

def test_synthese_trop_longue_rend_503(self):   # MoteurFactice(delai_s=0.5), Config(delai_s=0.1)
    statut, _, corps = appeler(app_lente, "POST", "/v1/synthese", {"texte": "Mi kú."}, CLE)
    self.assertEqual((statut, json.loads(corps)["code"]), (503, "delai_depasse"))

def test_aucune_reponse_cors(self): ...          # OPTIONS et POST avec Origin : pas d'Access-Control-Allow-Origin

def test_etat_quand_modele_absent(self):         # MoteurFactice(pret=False)
    self.assertFalse(json.loads(appeler(app_sans_modele, "GET", "/v1/etat")[2])["pret"])
```

- [ ] **Étape 2 :** lancer, constater l'échec, écrire le code, relancer toute la suite (`py -3.14 -m unittest discover -s tests -v`). Attendu : tout passe.
- [ ] **Étape 3 :** essai local réel : `python -c "from wsgiref.simple_server import make_server; ..."` sur le port 8000 avec le vrai `modele/`, une clé créée par `scripts/cles.py creer essai --brut` dans un dossier de stockage temporaire, puis `curl` d'un MP3. Attendu : un fichier qui se lit, avec la voix fon. Supprimer ce stockage temporaire ensuite.
- [ ] **Étape 4 :** commit `feat(api): wsgi api for fon speech synthesis`.

### Tâche 7 : documents et déploiement

**Fichiers :** créer `README.md`, `EXPLOITATION.md`, `LICENSE` (MIT, au nom d'Elisée Magloire ATONDE), `scripts/deployer.sh`.

- [ ] **Étape 1 :** `README.md`, guide du collègue, avec les huit points de la conception §6.8. Exemples testés contre le service lancé en local à la tâche 6, étape 3 : `curl`, Node (`fetch`), Python (`urllib.request`), PHP (`curl_*`), et un relais Node minimal, où le navigateur appelle le serveur du collègue, qui ajoute la clé. Les temps de réponse restent « à mesurer » jusqu'à la tâche 8. Contact : « Elisée, qui vous a transmis la clé », sans adresse e-mail.
- [ ] **Étape 2 :** `EXPLOITATION.md` : déployer, créer, lister et révoquer une clé, envoyer ou remplacer le modèle et son empreinte, lire le journal, redémarrer, limites et où les régler.
- [ ] **Étape 3 :** `scripts/deployer.sh`, sur le modèle de `scripts/deployer.sh` d'AgriFon :
  - `git pull` dans `~/voixfongbe-app` (premier passage : `git clone https://github.com/Magloire04/voixfongbe ~/voixfongbe-app`) ;
  - déclaration de l'application si elle manque : `cloudlinux-selector create --json --interpreter=python --version=3.13 --app-root=voixfongbe-app --domain=voix.bytechnum.com --app-uri=/ --startup-file=passenger_wsgi.py --entry-point=application` ;
  - installation de `requirements.txt` dans `~/virtualenv/voixfongbe-app/3.13/` ;
  - `stockage/` créé en 700 ;
  - vérification que `modele/` et son empreinte existent (sinon message clair, sans arrêt du reste) ;
  - `cloudlinux-selector restart` ;
  - appel de `https://voix.bytechnum.com/v1/etat`.
- [ ] **Étape 4 :** suite de tests complète une dernière fois, puis commit `docs: guide for project developers and server operations`.
- [ ] **Étape 5 :** avec l'accord d'Elisée, pousser `feature/service-voix` et ouvrir la PR (titre et description sans trace d'IA). Elisée fusionne.

### Tâche 8 : mise en ligne et mesures (après fusion et accord d'Elisée)

- [ ] **Étape 1 :** sur le serveur, lancer `scripts/deployer.sh` depuis le dépôt cloné.
- [ ] **Étape 2 :** envoyer `modele/model.onnx`, `vocab.json` et `empreinte.txt` par `scp` (port 21098) dans `~/voixfongbe-app/modele/`, vérifier l'empreinte avec `sha256sum`, redémarrer. Attendu : `/v1/etat` répond `"pret": true`.
- [ ] **Étape 3 :** vérifier `http://voix.bytechnum.com/v1/etat`. Attendu : 301 vers https. Sinon, demander à Elisée d'activer la redirection HTTPS du domaine dans cPanel.
- [ ] **Étape 4 :** mesures, depuis le serveur, sans afficher de clé : `K=$(… scripts/cles.py creer mesure --brut)` ; redémarrer l'application, puis chronométrer la première demande (phrase de 100 caractères), cinq demandes suivantes avec des textes différents, et noter la mémoire (`ps -o rss`) des processus Python de l'application ; enfin `scripts/cles.py revoquer mesure`. Cibles : réveil sous 3 s, demande sous 2 s, mémoire sous 400 Mo.
- [ ] **Étape 5 :** écrire les mesures dans le README (y compris une cible manquée), commit `docs(readme): measured response times`, PR, fusion par Elisée, redéploiement.
- [ ] **Étape 6 :** Elisée crée la clé du collègue en SSH (`scripts/cles.py creer <projet>`) et la lui transmet avec le lien du README.
