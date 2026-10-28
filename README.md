# JARVIS — votre second cerveau

Un assistant personnel **local-first** inspiré du *JARVIS Prompt Pack* et de la maquette fournie : hologramme central de JARVIS, cockpit de briefing, profils d'agents et suggestions de démonstration. Il transforme aussi des notes Markdown en galaxie de connaissances, répond à des questions à partir de ces notes, peut parler et retenir de nouveaux souvenirs.

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
  "notes_dir": "/Users/vous/Documents/mon-vault",
  "api_key": "PUT-YOUR-KEY-HERE",
  "model": "claude-opus-4-8"
}
```

Le cœur est composé de quatre calques PNG transparents dans `viewer/assets/`, assemblés du plus grand au plus petit comme la planche éclatée de référence : couronne d’acier (`jarvis-core-ring.png`), mécanique interne (`jarvis-core-veil.png`), anneau HUD cyan (`jarvis-core-disc.png`) et œil lumineux (`jarvis-core-light.png`). L’interface reproduit la géométrie « cover » du décor pour que l’ensemble reste posé au-dessus du projecteur du cockpit. Les calques se régénèrent avec `python3 tools/build-jarvis-core.py` (Pillow et numpy requis, uniquement pour cette commande) ; les images sources sont dans `tools/sources/`. Le générateur écrit deux fichiers par calque : la version **AVIF** servie au navigateur (≈ 60 Ko, neuf fois plus légère que le PNG) et un repli **PNG** pour les navigateurs anciens. Les deux nappes de voix `jarvis-core-hud-violet` et `jarvis-core-hud-ambre` teintent l’anneau pendant la synthèse ; elles se déduisent de `tools/sources/hud-violet.jpg` et `hud-ambre.jpg`. Le cœur n’apparaît qu’une fois tous ses calques décodés (`body.core-ready`, posé par `viewer/app.js`), pour éviter de voir les anneaux se poser un par un.

`config.json`, les captures créées par JARVIS et l'index de notes généré sont ignorés par Git. **Ne mettez pas vos notes privées dans le dépôt.** Les captures créées par « Souviens-toi que… » sont enregistrées dans `captures/` à l'intérieur de votre dossier de notes.

## Activer les réponses IA (facultatif)

Sans clé, la recherche locale par mots-clés fonctionne déjà et affiche les extraits les plus pertinents. Pour obtenir une synthèse rédigée, collez votre clé Anthropic dans `api_key` de `config.json`, ou définissez la variable d'environnement `ANTHROPIC_API_KEY`. Vous pouvez modifier `model` dans le même fichier. **Ne collez jamais une clé dans le chat ou dans le code du navigateur.**

Quand une clé est configurée, le serveur envoie à Anthropic la question et le texte des six notes les mieux classées pour produire la réponse. La clé reste sur le serveur et n'est jamais incluse dans les pages servies. La voix utilise les fonctions intégrées au navigateur; aucune clé ni service vocal payant n'est requis.

## Ce que vous pouvez essayer

- Faire glisser la galaxie pour l'explorer, zoomer et cliquer sur une étoile pour lire sa note.
- Demander « Résume mes notes » ou rechercher une idée dans la barre en haut.
- Demander « Quelle météo à Sanguinet ? » pour interroger Open-Meteo; la météo est récupérée côté serveur et mise en cache dix minutes.
- Activer la lecture vocale : le cœur de JARVIS s’anime — quatre anneaux concentriques qui tournent à des vitesses différentes, disque et orbe qui s’éclairent au rythme des syllabes. Le bouton micro permet aussi la dictée (Chrome/Edge).
- Écrire ou dicter : « **Souviens-toi que…** » pour créer une vraie note et l'ajouter immédiatement à la galaxie.

Les liens du graphe sont détectés quand une note mentionne le titre d'une autre ou partage des liens `[[wikilinks]]`. Les notes sont indexées localement au démarrage; relancez le serveur après avoir ajouté ou modifié des fichiers.
