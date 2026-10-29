# Mettre JARVIS en ligne sans serveur et sans terminal

**Pour qui** : cette méthode n'utilise ni ton hébergement OVH, ni ton serveur, ni
Anna. Tout se fait dans un navigateur, en cliquant.

**Ce que tu obtiens** : une adresse du type `https://jarvis-quelquechose.onrender.com`,
en HTTPS, avec la connexion Google. Toi seul entres.

**Temps** : 15 à 20 minutes, dont 5 d'attente pendant que ça se construit.

---

## Avant de commencer

Il te faut deux choses que tu as déjà :

- ton **compte GitHub** (celui qui a servi à créer `lowrenzu/grok-briefing`) ;
- ton **compte Google** `funk.e.lee@gmail.com` (déjà autorisé dans Google Auth Platform).

Et les deux valeurs Google. **Elles ne sont pas écrites dans ce fichier, exprès** :
le dépôt est public, et un code secret n'a rien à y faire. Tu les trouves :

- dans le fichier `config.json` de ton ordinateur (ouvert avec le Bloc-notes) ;
- ou dans le message privé que je t'ai préparé ;
- ou, en dernier recours, tu en régénères un chez Google (Clients → JARVIS web →
  Ajouter un secret) et tu prends le nouveau.

---

## Étape 1 — Créer un compte Render (2 min)

1. Va sur **https://render.com**
2. **Get Started** / **Sign Up**
3. Choisis **GitHub** (le plus simple : ça relie directement tes dépôts)
4. Autorise Render à voir tes dépôts

> Pas de carte bancaire pour l'offre gratuite. Render peut la demander pour
> l'offre payante seulement.

---

## Étape 2 — Créer le service (3 min)

1. En haut à droite : **New +** → **Blueprint**
2. Choisis le dépôt **`grok-briefing`**
3. Branche : **`arena/b5439b0b-grok-briefing`**
4. Render lit le fichier `render.yaml` et affiche un formulaire avec les variables à remplir.

Remplis les cinq champs :

| Variable | Valeur à coller |
|---|---|
| `JARVIS_GOOGLE_CLIENT_ID` | ton ID client (voir ci-dessus) |
| `JARVIS_GOOGLE_CLIENT_SECRET` | ton code secret (voir ci-dessus) |
| `JARVIS_ALLOWED_EMAILS` | `funk.e.lee@gmail.com` |
| `JARVIS_ADMIN_EMAIL` | `funk.e.lee@gmail.com` |
| `JARVIS_PUBLIC_URL` | laisse **vide** pour l'instant (on la met à l'étape 4) |

> Ces valeurs restent **chez l'hébergeur**, jamais dans le code. Ne les colle
> dans aucun fichier du dépôt : il est public, et GitHub refuserait l'envoi.

5. **Apply** / **Create**

> **Si le bouton Blueprint n'existe pas dans ton interface** : **New +** →
> **Web Service** → onglet **Public Git repository** → colle
> `https://github.com/lowrenzu/grok-briefing` → branche
> `arena/b5439b0b-grok-briefing` → **Runtime : Docker** → puis les mêmes
> variables dans **Environment**.

---

## Étape 3 — Attendre la construction (5 min)

Render affiche des lignes de log qui défilent. Tu attends que le statut passe à
**Live** (vert).

Ton adresse apparaît en haut, sous la forme :

```
https://jarvis-xxxx.onrender.com
```

**Copie-la** (clic sur l'icône à côté). C'est l'adresse de ton JARVIS.

---

## Étape 4 — Lui donner sa propre adresse (1 min)

1. Dans Render : **Environment** (menu de gauche)
2. Modifie `JARVIS_PUBLIC_URL` → colle ton adresse complète, par exemple
   `https://jarvis-xxxx.onrender.com`
3. **Save Changes** → le service redémarre tout seul (1 à 2 min)

Sans cette étape, Google refusera de te renvoyer vers JARVIS après la connexion.

---

## Étape 5 — Autoriser cette adresse chez Google (2 min)

1. Va sur <https://console.cloud.google.com/auth/clients?hl=fr>
2. Projet **JarvisLowrenzu** → **JARVIS web**
3. Dans **URI de redirection autorisés** → **Ajouter un URI**
4. Colle : `https://jarvis-xxxx.onrender.com/auth/callback`
   (remplace `jarvis-xxxx` par ton vrai nom, et **garde** `/auth/callback` à la fin)
5. **Enregistrer**

---

## Étape 6 — Essayer

1. Ouvre ton adresse `https://jarvis-xxxx.onrender.com`
2. Tu dois voir une page **Google** (pas JARVIS) : c'est bon signe, la porte est fermée
3. Connecte-toi avec `funk.e.lee@gmail.com`
4. JARVIS s'ouvre

**Vérification qui compte** : ouvre la même adresse dans une **fenêtre de
navigation privée**. Tu dois retomber sur Google, sans voir aucune note.
Si tu vois les notes, dis-le moi tout de suite, ce n'est pas normal.

---

## Étape 7 — Ajouter Anna

Deux endroits, comme prévu :

1. **Google** → <https://console.cloud.google.com/auth/audience?hl=fr> →
   **Utilisateurs tests** → **Ajouter des utilisateurs** → son adresse Gmail
2. **JARVIS** → ⚙ **Réglages** → **Accès** → son adresse → **Ajouter**

---

## Combien ça coûte, honnêtement

| Formule | Prix | Ce que ça change |
|---|---|---|
| **Gratuit** | 0 € | Le service s'endort après 15 min sans visite (30 s de réveil à la première ouverture). La liste d'accès revient à son état de départ à chaque redémarrage : **toi tu restes admin**, mais Anna serait à re-ajouter. |
| **Starter** (+ disque 1 Go) | environ 7 €/mois | Ne s'endort jamais, et la liste d'accès est conservée définitivement. |

Pour « un projet pour voir », **commence par le gratuit**. Tu passeras au payant
si l'outil te sert vraiment.

---

## Si ça bloque

| Message | Cause | Solution |
|---|---|---|
| `redirect_uri_mismatch` | L'adresse de retour chez Google ne correspond pas | Étape 5 : vérifier qu'il n'y a ni faute de frappe ni `/` final en trop |
| `invalid_client` | Code secret mal recopié | Un caractère peut être un `l` minuscule ou un `I` majuscule. Dans Google → Clients → JARVIS web → **Ajouter un secret**, en générer un neuf, puis remplacer la variable dans Render |
| `Error 403: access_denied` | Ton adresse n'est pas dans les utilisateurs tests | Google → Audience → Utilisateurs tests → ajouter `funk.e.lee@gmail.com` |
| La page reste sur « Deploying » | La construction prend du temps, ou échoue | Ouvre **Logs** et envoie-moi les dernières lignes |
| Erreur 502 | Le service n'écoute pas sur le bon port | Envoie-moi les **Logs** : `server.py` lit normalement `PORT` tout seul |

---

## Ce qu'il faut m'envoyer si ça ne marche pas

1. l'**adresse** Render obtenue ;
2. une **capture** de l'écran au moment du blocage ;
3. les **10 dernières lignes** de **Logs** dans Render.

Avec ça, je corrige sans te faire deviner.

---

## Brancher l'IA (facultatif, mais c'est là que JARVIS devient vivant)

Sans clé, JARVIS cherche des mots-clés dans vos notes. Avec une clé, il **comprend**
la question et rédige une vraie réponse à partir de vos notes.

### Le choix le plus simple : Groq (gratuit, sans carte bancaire)

1. <https://console.groq.com/keys> → créez un compte (Google, GitHub ou e-mail).
2. **Create API Key** → copiez la clé, elle commence par `gsk_`.
3. Dans JARVIS → ⚙ **Réglages** → service **Groq (rapide)** → collez la clé → **Tester** → **Enregistrer**.

Le modèle est pré-rempli (`llama-3.3-70b-versatile`). Gratuit : 1 000 requêtes par
jour, largement suffisant pour un usage personnel.

### Les autres options

| Service | Modèle pré-rempli | À savoir |
|---|---|---|
| **Anthropic (Claude)** | `claude-sonnet-5-5` | La meilleure qualité de rédaction. Carte bancaire requise, facturé à l'usage (quelques centimes par mois pour un usage perso). <https://console.anthropic.com/settings/keys> |
| **Mistral AI** | `mistral-small-latest` | Entreprise française, offre gratuite d'expérimentation. <https://console.mistral.ai/api-keys> |
| **OpenAI** | `gpt-4o-mini` | Carte bancaire requise. <https://platform.openai.com/api-keys> |
| **Ollama** | `llama3.2` | 100 % local et gratuit, mais il faut un ordinateur qui fait tourner Ollama : inadapté à un petit serveur. |

Le bouton **Tester**, dans le panneau, vérifie la clé sans rien enregistrer en cas d'erreur.

### Où vit la clé

Dans `config.json`, sur le serveur, en droits `600` — jamais dans le navigateur,
jamais dans le dépôt. Le panneau n'affiche que ses quatre derniers caractères.
