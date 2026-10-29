# JARVIS sur ton ordinateur — trois gestes

Pas de serveur, pas de compte, pas de case à remplir. Tes notes restent chez toi.

---

## 1. Télécharger et décompresser

Tu as déjà `JARVIS-app.zip`.

- Clic droit sur le fichier → **Extraire tout**
- Tu obtiens un dossier **`JARVIS`**. Ouvre-le.

> Tu peux le mettre où tu veux (Bureau, Documents). Évite seulement de le
> déplacer après le premier démarrage, sinon tu perdras le chemin de tes notes.

## 2. Double-cliquer sur le bon fichier

| Ton ordinateur | Le fichier à double-cliquer |
|---|---|
| **Windows** | `LANCER-JARVIS.bat` |
| **Mac** | `Lancer-JARVIS.command` |

Une petite fenêtre noire s'ouvre, puis ton navigateur affiche JARVIS.

**Ne ferme pas la fenêtre noire** : c'est JARVIS qui tourne. Tant qu'elle est
ouverte, JARVIS fonctionne.

## 3. C'est tout

Tu es dedans. Pas de mot de passe, pas d'inscription : l'application n'écoute
que sur ton ordinateur.

---

## Tes notes sont dans un dossier, sur ton disque

Au premier démarrage, un dossier **`mes-notes`** est créé à côté de
`server.py`, avec 25 notes d'exemple pour ne pas commencer sur du vide.

- tu peux ouvrir ce dossier dans l'Explorateur et **modifier, ajouter,
  supprimer des fichiers `.md`** ;
- au démarrage suivant, JARVIS les relit ;
- rien n'est envoyé sur Internet.

## Changer ton nom et ta couleur

Dans JARVIS : l'engrenage **⚙** en haut à droite → section **Identité**.

- **Nom affiché** : tape le tien, appuie sur Entrée ;
- **Teinte** : Bleu, Violet, Ambre, Prune, ou **Auto** (suit l'heure).

Ces réglages sont enregistrés sur ton disque et te suivent au redémarrage.

## Pour arrêter

Ferme la **fenêtre noire** (ou Ctrl+C dedans). C'est tout : plus rien ne tourne.

---

## Si Python n'est pas installé

La fenêtre noire affichera un message avec le lien. En résumé :

1. **https://www.python.org/downloads/**
2. le gros bouton **Download Python**
3. lance le fichier téléchargé
4. ⚠️ **coche « Add python.exe to PATH »** sur le premier écran — c'est la seule
   case de toute cette page qui compte
5. **Install Now**, puis reviens et double-clique à nouveau `LANCER-JARVIS.bat`

## Si Windows affiche un avertissement bleu

« Windows a protégé votre PC » : clique **Informations complémentaires** puis
**Exécuter quand même**. C'est normal pour un fichier téléchargé.

---

## Plus tard, si tu veux y accéder depuis ton téléphone ou avec Anna

Ça demande un serveur, et c'est **ce qu'on avait commencé**. Rien n'est perdu :
le dossier contient toute la configuration nécessaire (`MESSAGE-POUR-ANNA.txt`,
`DEPLOY-RAPIDE.md`). Mais tu peux vivre très bien sans, et y revenir quand tu
veux, sans rien refaire ici.

## Une seule chose à savoir

**Ce JARVIS local est réservé à cet ordinateur.** Personne d'autre ne peut s'y
connecter — ni depuis ton téléphone, ni depuis Internet. C'est voulu, et c'est
ce qui le rend simple.
