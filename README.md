# JARVIS — votre second cerveau

> **Pas de serveur, pas de terminal ?** Suivre `DEPLOY-RAPIDE.md` : mise en ligne en cliquant, chez un hébergeur (Render), avec la connexion Google.

Un assistant personnel **local-first** inspiré du *JARVIS Prompt Pack* et de la maquette fournie : hologramme central de JARVIS, cockpit de briefing, profils d'agents et suggestions de démonstration. Il transforme aussi des notes Markdown en galaxie de connaissances, répond à des questions à partir de ces notes, peut parler et retenir de nouveaux souvenirs.

## Personnaliser : nom et teinte

Dans **Réglages → Identité**, chaque compte choisit :

- le **nom affiché** (24 caractères au plus) — il remplace « JARVIS » partout :
  marque, titre de l'onglet, placeholder du chat, messages d'attente, réponses de
  l'assistant (« Je suis Cortex… »), **icône et nom de l'application installée** ;
- la **teinte d'accent** : Bleu JARVIS, Violet, Ambre, Prune, ou **Auto** — dans ce
  dernier cas elle suit l'heure locale (bleu le jour, ambre de 18 h à 22 h, violet
  la nuit) et bascule d'elle-même sans recharger la page.

Ces préférences sont **propres à chaque compte** : Anna peut appeler son JARVIS
autrement et le teinter en prune sans que cela change quoi que ce soit chez
quiconque. Elles sont enregistrées côté serveur (`data/prefs/`), donc retrouvées
sur tous les appareils du même compte, et le choix de teinte est aussi gardé dans
le navigateur pour s'afficher sans clignotement au chargement.

## Installer JARVIS sur le téléphone

JARVIS est une **application web installable** (PWA) : une fois en ligne, il
s'ajoute à l'écran d'accueil et s'ouvre en plein écran, sans barre d'adresse.

- **iPhone / iPad** (Safari) : bouton **Partager** → *Sur l'écran d'accueil*.
- **Android** (Chrome) : menu **⋮** → *Installer l'application*.

L'icône est la composition du cœur JARVIS. Le service worker ne met en cache que
la présentation (styles, images, icônes) : **la page, le graphe et les API
viennent toujours du réseau**, pour qu'un changement de compte ne puisse jamais
afficher les notes d'une autre personne.

## Démarrage rapide

Prérequis : Python 3.10+ et Chrome ou Edge pour la dictée vocale.

```bash
python3 server.py
```

Puis ouvrez **http://localhost:4700**. Le serveur écoute uniquement sur votre ordinateur par défaut. Le projet contient 25 notes fictives autour d'un projet de pêche nommé Lure Skills pour essayer l'interface sans préparer de dossier. La météo de Sanguinet et ses prévisions viennent d'Open-Meteo, sans clé API, via le serveur JARVIS (cache de 10 minutes); si la source est inaccessible, le tableau de bord indique le cache ou repasse explicitement aux exemples. Seules les coordonnées fixes de Sanguinet sont envoyées au fournisseur météo. Les autres profils d'agents, spots, activités et recommandations restent des maquettes, pas des services connectés ni des conseils de pêche. Pointez JARVIS vers votre propre dossier de notes quand vous serez prêt.

## Brancher vos notes

1. Copiez `config.example.json` vers `config.json`.
2. Remplacez `notes_dir` par le chemin de votre dossier Markdown. Un chemin relatif est résolu depuis ce projet; un chemin absolu ou `~/...` convient aussi.
3. Redémarrez le serveur. JARVIS parcourt les fichiers `.md` récursivement.

Exemple :

```json
{
  "provider": "anthropic",
  "notes_dir": "/Users/vous/Documents/mon-vault",
  "api_key": "PUT-YOUR-KEY-HERE",
  "model": "claude-opus-4-8"
}
```

`provider` vaut `anthropic`, `openai`, `mistral`, `groq`, `ollama` ou `custom`; `base_url` permet d’indiquer l’adresse d’un service libre (Ollama, LM Studio…). Tout cela se règle aussi depuis le panneau **Réglages**, sans éditer le fichier.

## Le mettre sur un serveur, en privé

Trois recettes détaillées dans **[DEPLOY.md](DEPLOY.md)** : Tailscale (aucun port ouvert, recommandé), un VPS derrière un proxy avec mot de passe et HTTPS, ou un simple tunnel SSH. Retenez surtout qu'il ne faut jamais exposer le port 4700 directement : JARVIS n'a pas de mot de passe par défaut. Pour un accès public, activez la **connexion Google** : renseignez `auth.google_client_id`, `auth.google_client_secret`, `auth.allowed_emails` et `auth.public_url` dans `config.json`. Tant que la liste `allowed_emails` est vide, personne ne peut entrer ; une fois remplie, tout le serveur (page, scripts et API) exige une session Google. Le premier compte (ou `auth.admin_email`) devient administrateur et gère la liste des accès directement dans **Réglages → Accès** : ajouter, retirer, voir qui est connecté. Cette liste est conservée dans `access.json` (droits `600`, ignoré par Git).

**Chacun son JARVIS.** Le compte administrateur garde les notes historiques ; tout autre compte autorisé reçoit à sa première connexion un **espace personnel** (`data/users/<empreinte>/notes/`), avec une note d'accueil. Les notes, le graphe, les souvenirs et le compteur sont propres à chaque compte : rien ne se mélange, et un invité ne voit ni les notes d'un autre ni le nombre de comptes autorisés. Les réglages du cerveau (fournisseur d'IA, clé) restent communs et réservés à l'administrateur. Sur un serveur partagé, ajoutez `JARVIS_SETTINGS=0` pour rendre le panneau Réglages en lecture seule et garder la clé dans `config.json`.

Le cœur est composé de quatre calques PNG transparents dans `viewer/assets/`, assemblés du plus grand au plus petit comme la planche éclatée de référence : couronne d’acier (`jarvis-core-ring.png`), mécanique interne (`jarvis-core-veil.png`), anneau HUD cyan (`jarvis-core-disc.png`) et œil lumineux (`jarvis-core-light.png`). L’interface reproduit la géométrie « cover » du décor pour que l’ensemble reste posé au-dessus du projecteur du cockpit. Les libellés des thèmes et des notes ne sont pas dessinés dans le canvas : ce sont des éléments DOM (`#nodeLabels`) positionnés à chaque image, donc rendus par le navigateur à la résolution exacte de l’écran — le texte reste aussi net que le reste de l’interface. Les calques se régénèrent avec `python3 tools/build-jarvis-core.py` (Pillow et numpy requis, uniquement pour cette commande) ; les images sources sont dans `tools/sources/`. Le générateur écrit deux fichiers par calque : la version **AVIF** servie au navigateur (≈ 60 Ko, neuf fois plus légère que le PNG) et un repli **PNG** pour les navigateurs anciens. Les deux nappes de voix `jarvis-core-hud-violet` et `jarvis-core-hud-ambre` teintent l’anneau pendant la synthèse ; elles se déduisent de `tools/sources/hud-violet.jpg` et `hud-ambre.jpg`. Le cœur n’apparaît qu’une fois tous ses calques décodés (`body.core-ready`, posé par `viewer/app.js`), pour éviter de voir les anneaux se poser un par un.

`config.json`, les captures créées par JARVIS et l'index de notes généré sont ignorés par Git. **Ne mettez pas vos notes privées dans le dépôt.** Les captures créées par « Souviens-toi que… » sont enregistrées dans `captures/` à l'intérieur de votre dossier de notes.

## Activer les réponses IA (facultatif)

Sans clé, la recherche locale par mots-clés fonctionne déjà et affiche les extraits les plus pertinents. Pour obtenir une synthèse rédigée, ouvrez le panneau **Réglages** (l’engrenage en haut à droite de la page), choisissez un fournisseur, collez votre clé et cliquez sur **Tester** puis **Enregistrer**. Aucun redémarrage n’est nécessaire : le serveur applique les réglages immédiatement.

Fournisseurs proposés : **Anthropic** (Claude), **OpenAI**, **Mistral**, **Groq**, **Ollama** (modèle installé sur votre PC, gratuit et hors ligne) et **tout service compatible OpenAI** (LM Studio, OpenRouter, vLLM…) avec son adresse.

Le panneau peut aussi changer le **dossier de notes** ; l’index est reconstruit à l’enregistrement. Les réglages sont écrits dans `config.json` avec des droits `600` (propriétaire uniquement).

Toujours possible en ligne de commande : `api_key` et `model` dans `config.json`, ou la variable d’environnement `ANTHROPIC_API_KEY` / `JARVIS_API_KEY` (prioritaire sur le fichier). **Ne collez jamais une clé dans le chat ou dans le code du navigateur.**

Sécurité : le serveur ne renvoie au navigateur qu’une clé **masquée** (`••••••••4f2a`), jamais la clé complète. Les écritures de réglages sont réservées au PC où tourne JARVIS, exigent l’en-tête `X-Jarvis-Settings: 1` (protection contre les formulaires forgés par un site tiers) et restent refusées depuis la tablette, sauf si vous lancez le serveur avec `JARVIS_SETTINGS_LAN=1`.

Quand une clé est configurée, le serveur envoie au fournisseur choisi la question et le texte des six notes les mieux classées. La clé reste sur le serveur et n'est jamais incluse dans les pages servies. La voix utilise les fonctions intégrées au navigateur; aucune clé ni service vocal payant n'est requis.

## Ce que vous pouvez essayer

- Faire glisser la galaxie pour l'explorer, zoomer et cliquer sur une étoile pour lire sa note.
- Demander « Résume mes notes » ou rechercher une idée dans la barre en haut.
- Demander « Quelle météo à Sanguinet ? » pour interroger Open-Meteo; la météo est récupérée côté serveur et mise en cache dix minutes.
- Activer la lecture vocale : le cœur de JARVIS s’anime — quatre anneaux concentriques qui tournent à des vitesses différentes, disque et orbe qui s’éclairent au rythme des syllabes. Le bouton micro permet aussi la dictée (Chrome/Edge).
- Écrire ou dicter : « **Souviens-toi que…** » pour créer une vraie note et l'ajouter immédiatement à la galaxie.

Les liens du graphe sont détectés quand une note mentionne le titre d'une autre ou partage des liens `[[wikilinks]]`. Les notes sont indexées localement au démarrage; relancez le serveur après avoir ajouté ou modifié des fichiers.

## Tests

```bash
python3 tests/test_isolation.py
```

Ce test démarre un JARVIS complet avec un faux fournisseur Google, connecte deux
personnes différentes, et vérifie que ni les notes, ni les souvenirs, ni le
graphe, ni la liste des comptes ne passent d'un espace à l'autre.

```bash
npm install jsdom && node tests/ui_check.js   # interface : teintes et nom
```
