# Voix fon : guide d'utilisation de l'API

Ce service transforme un texte écrit en fon (fongbé) en son, avec la voix de synthèse fon de Meta (MMS-TTS). Vous lui envoyez une phrase, il vous rend un fichier MP3 ou WAV à faire écouter à vos utilisateurs.

- Adresse : `https://voix.bytechnum.com`
- Langue : fon uniquement.
- Usage **non commercial uniquement** (licence de la voix, voir plus bas).

## 1. Votre clé d'accès

Chaque projet a sa propre clé. Elle vous est transmise par Elisée. Elle ne sera plus jamais réaffichée : gardez-la précieusement.

- Rangez-la dans une **variable d'environnement de votre serveur**, par exemple `VOIX_FON_CLE`.
- Ne la mettez **jamais** dans le code d'une page web ou d'une application mobile : n'importe qui pourrait la lire et utiliser votre quota.
- En cas de fuite, demandez une nouvelle clé : l'ancienne sera révoquée.

Le service n'accepte pas les appels directs depuis un navigateur. Le navigateur appelle **votre serveur**, qui appelle la voix (voir l'exemple de relais, section 4).

## 2. Faire parler la voix

Une seule demande : `POST /v1/synthese`.

- En-tête `Authorization: Bearer <votre clé>`
- En-tête `Content-Type: application/json`
- Corps JSON, en UTF-8 : `{"texte": "Mi kú abɔ.", "format": "mp3"}`. `format` vaut `mp3` (par défaut, plus léger) ou `wav`.

La réponse est directement le son : `audio/mpeg` pour le MP3, `audio/wav` pour le WAV. Son mono, 16 kHz.

En-têtes utiles de la réponse :

| En-tête | Sens |
| --- | --- |
| `X-Voix-Licence` | `MMS-TTS de Meta, CC BY-NC 4.0` |
| `X-Voix-Cache` | `oui` si la phrase avait déjà été dite et revient tout de suite, `non` sinon |
| `X-Voix-Caracteres-Ignores` | nombre de caractères que la voix n'a pas pu dire (chiffres, émojis, lettres étrangères au fon...). S'il n'est pas à 0, relisez votre texte (section 6). |

## 3. Exemples prêts à copier

Dans tous les exemples, la clé est lue dans la variable d'environnement `VOIX_FON_CLE`.

### Ligne de commande (curl)

```bash
printf '{"texte": "Mi kú abɔ ɖo gle ɔ mɛ."}' > demande.json
curl -sS -o voix.mp3 -w "%{http_code}\n" \
  -H "Authorization: Bearer $VOIX_FON_CLE" -H "Content-Type: application/json" \
  --data-binary @demande.json https://voix.bytechnum.com/v1/synthese
```

Passez le texte par un fichier (`--data-binary @fichier`) : sous Windows, curl abîme les lettres fon (ɖ, ɔ, ɛ...) écrites directement dans la ligne de commande.

### JavaScript (Node.js 18 ou plus récent)

```js
import { writeFile } from 'node:fs/promises';

const reponse = await fetch('https://voix.bytechnum.com/v1/synthese', {
  method: 'POST',
  headers: { Authorization: `Bearer ${process.env.VOIX_FON_CLE}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({ texte: 'Mi kú abɔ ɖo gle ɔ mɛ.', format: 'mp3' }),
});
if (!reponse.ok) {
  const { code, erreur } = await reponse.json();
  throw new Error(`${reponse.status} ${code} : ${erreur}`);
}
await writeFile('voix.mp3', Buffer.from(await reponse.arrayBuffer()));
```

### Python 3 (sans bibliothèque à installer)

```python
import json, os, urllib.request, urllib.error

demande = urllib.request.Request(
    "https://voix.bytechnum.com/v1/synthese",
    data=json.dumps({"texte": "Mi kú abɔ ɖo gle ɔ mɛ.", "format": "mp3"}).encode("utf-8"),
    headers={"Authorization": "Bearer " + os.environ["VOIX_FON_CLE"], "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(demande, timeout=60) as reponse:
        open("voix.mp3", "wb").write(reponse.read())
except urllib.error.HTTPError as e:
    print(e.code, json.loads(e.read()))
```

### PHP

```php
<?php
$ch = curl_init('https://voix.bytechnum.com/v1/synthese');
curl_setopt_array($ch, [
    CURLOPT_POST => true,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT => 60,
    CURLOPT_HTTPHEADER => ['Authorization: Bearer ' . getenv('VOIX_FON_CLE'), 'Content-Type: application/json'],
    CURLOPT_POSTFIELDS => json_encode(['texte' => 'Mi kú abɔ ɖo gle ɔ mɛ.', 'format' => 'mp3']),
]);
$son = curl_exec($ch);
$statut = curl_getinfo($ch, CURLINFO_HTTP_CODE);
if ($statut === 200) {
    file_put_contents('voix.mp3', $son);
} else {
    $e = json_decode($son, true);
    echo "$statut {$e['code']} : {$e['erreur']}\n";
}
```

## 4. Faire écouter la voix dans une page web : le relais

La page ne connaît pas la clé. Elle appelle une adresse de **votre** serveur, qui ajoute la clé et renvoie le son. Exemple minimal en Node.js 18+ (aucune bibliothèque) :

```js
// relais.mjs : node relais.mjs (écoute sur le port 8080)
import { createServer } from 'node:http';

createServer(async (req, res) => {
  if (req.method !== 'POST' || req.url !== '/voix') { res.writeHead(404).end(); return; }
  try {
    let corps = '';
    for await (const morceau of req) {
      corps += morceau;
      if (corps.length > 8192) { res.writeHead(413).end(); return; }
    }
    const { texte } = JSON.parse(corps || '{}');
    const reponse = await fetch('https://voix.bytechnum.com/v1/synthese', {
      method: 'POST',
      headers: { Authorization: `Bearer ${process.env.VOIX_FON_CLE}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ texte, format: 'mp3' }),
    });
    res.writeHead(reponse.status, { 'Content-Type': reponse.headers.get('content-type') });
    res.end(Buffer.from(await reponse.arrayBuffer()));
  } catch {
    // Corps illisible ou voix injoignable : une erreur pour ce visiteur, sans arrêter le relais.
    if (!res.headersSent) res.writeHead(502);
    res.end();
  }
}).listen(8080);
```

L'adresse `/voix` doit être servie **par le même site que la page** (même domaine et même port, par exemple derrière le même serveur web) : sinon le navigateur bloque l'appel. Si votre site tourne déjà sous Node.js, ajoutez simplement cette route à votre serveur.

Côté page :

```js
const reponse = await fetch('/voix', { method: 'POST', body: JSON.stringify({ texte: 'Mi kú abɔ.' }) });
if (reponse.ok) new Audio(URL.createObjectURL(await reponse.blob())).play();
```

Ajoutez à votre relais vos propres règles (utilisateur connecté, limite par visiteur) : sinon n'importe qui peut épuiser votre quota à travers lui.

## 5. Erreurs

Toute erreur rend du JSON : `{"erreur": "<explication en français>", "code": "<code>"}`.

| Statut | Code | Que faire |
| --- | --- | --- |
| 400 | `json_invalide` | Envoyer un objet JSON en UTF-8, avec l'en-tête `Content-Type: application/json`. |
| 400 | `texte_absent` | Le champ `texte` manque ou n'est pas une chaîne. |
| 400 | `texte_trop_long` | 1 000 caractères au plus : couper le texte en phrases. |
| 400 | `format_inconnu` | `format` vaut `mp3` ou `wav`. |
| 400 | `texte_vide` | Rien de prononçable : le texte ne contient aucune lettre fon, seulement des chiffres, signes ou émojis (section 6). |
| 401 | `cle_absente` / `cle_invalide` | Vérifier l'en-tête `Authorization: Bearer <clé>` et la clé. |
| 404 | `introuvable` | Adresse inconnue : seules `/v1/synthese` et `/v1/etat` existent. |
| 405 | `methode` | Mauvaise méthode : `POST` pour `/v1/synthese`, `GET` pour `/v1/etat`. |
| 413 | `corps_trop_grand` | Corps de plus de 8 Ko. |
| 429 | `quota_jour` | Quota du jour atteint (le vôtre, ou celui de tout le service). L'en-tête `Retry-After` donne le nombre de secondes jusqu'à minuit, heure de Porto-Novo. |
| 503 | `voix_occupee` | La voix prépare déjà une autre phrase : réessayer après le nombre de secondes indiqué par `Retry-After`. |
| 503 | `modele_indisponible` / `delai_depasse` | Voix momentanément indisponible ou trop lente : réessayer un peu plus tard, avec un texte plus court. Si la phrase était trop longue, elle sera souvent prête au nouvel essai (`X-Voix-Cache: oui`). |
| 500 | `erreur_interne` | Réessayer ; si cela dure, prévenir Elisée. |

Seules les demandes qui rendent un son comptent dans le quota : les erreurs ne vous coûtent rien.

## 6. Écrire le fon pour la voix

La voix ne connaît que les lettres du fon et quelques accents. Le service prépare le texte avant de le dire :

- **Majuscules** : sans effet, tout est mis en minuscules.
- **Lettres reconnues** : a à z sauf q et r, ainsi que ɔ, ɛ, ɖ, đ, et l'apostrophe (droite ou typographique) et le trait d'union.
- **Accents gardés** : l'aigu et le caron, sur toute lettre reconnue (á, é, ɔ́, ɛ́, ń, ǎ, ě, ǒ...), et l'accent grave sur è et ì. Sur les autres lettres, l'accent grave est retiré et la lettre reste.
- **Ponctuation et blancs** : `. , ; : ? !` font une petite pause. Les retours à la ligne et tabulations comptent comme des espaces. Le reste des signes est ignoré.
- **Texte sans lettre** : un texte qui ne contient aucune lettre fon (« 300 - 400 ») est refusé (`texte_vide`) plutôt que de produire un souffle.
- **Chiffres** : ignorés. **Écrivez les nombres en toutes lettres, en fon** : « 300 F » ne serait pas dit. L'en-tête `X-Voix-Caracteres-Ignores` vous signale ce qui a été sauté.
- **Longueur** : préférez des phrases courtes, envoyées une par une. La voix répond plus vite, et l'utilisateur entend la première phrase pendant que la suivante se prépare.

La prononciation reste celle d'une voix de synthèse : faites relire vos phrases par un locuteur, et gardez à l'écran le texte écrit.

## 7. Limites et temps de réponse

- 1 000 caractères au plus par demande.
- 100 demandes par jour pour votre projet (jour de Porto-Novo, UTC+1), y compris les phrases servies par le cache ; et 300 par jour pour l'ensemble des projets qui utilisent le service.
- Une seule phrase fabriquée à la fois : si deux demandes arrivent ensemble, la seconde reçoit `voix_occupee` et réessaie quelques secondes plus tard.
- Une phrase déjà dite revient tout de suite (`X-Voix-Cache: oui`).
- Temps de réponse : **à mesurer après la mise en ligne**. Le service s'endort quand personne ne l'utilise : la première demande après une pause est plus lente que les suivantes.

## 8. Licence et mention obligatoire

La voix est le modèle [facebook/mms-tts-fon](https://huggingface.co/facebook/mms-tts-fon) de Meta, sous licence [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/deed.fr) :

- **usage non commercial uniquement** : pas de vente, pas de service payant, pas de publicité ;
- **mention obligatoire** dans votre application, près du lecteur ou dans les crédits : « Voix : MMS-TTS de Meta (CC BY-NC 4.0) ».

## 9. État du service et contact

`GET https://voix.bytechnum.com/v1/etat` (sans clé) indique si la voix est prête :

```json
{"service": "voix fon", "version": "9c0f27e0a199", "modele": "facebook/mms-tts-fon", "licence": "CC BY-NC 4.0", "pret": true}
```

Contact : Elisée, qui vous a transmis la clé.
