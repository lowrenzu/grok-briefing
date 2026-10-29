# JARVIS sur Windows 11 — en trois gestes

Pas de serveur, pas de compte, pas d'adresse à taper. Tes notes restent chez toi.

---

## 1. Décompresser

Clic droit sur `JARVIS-app.zip` → **Extraire tout** → tu obtiens un dossier **`JARVIS`**.

Mets-le où tu veux (Bureau, Documents). Évite seulement de le déplacer après le
premier démarrage.

## 2. Double-cliquer sur `LANCER-JARVIS.bat`

C'est tout. Une fenêtre noire s'ouvre, puis **JARVIS s'ouvre dans sa propre
fenêtre** — sans barre d'adresse, sans onglet, avec son icône dans la barre des
tâches.

**Ne ferme pas la petite fenêtre noire** : c'est JARVIS qui tourne.
Fermer la **fenêtre JARVIS**, en revanche, arrête tout proprement.

## 3. (Facultatif) Une vraie application autonome

Au premier lancement, JARVIS s'ouvre dans ton navigateur. Pour avoir une
**fenêtre d'application** au lieu d'une page :

- double-clique sur **`INSTALLER-APPLICATION.bat`** — une seule fois ;
- cela installe un petit composant gratuit (`pywebview`), qui utilise
  **Edge WebView2, déjà présent dans Windows 11** ;
- ensuite, `LANCER-JARVIS.bat` ouvre JARVIS dans sa propre fenêtre.

Rien n'est cassé si tu sautes cette étape : JARVIS fonctionne dans le
navigateur, simplement avec les onglets autour.

---

## Tes notes sont un dossier, sur ton disque

Au premier démarrage, un dossier **`mes-notes`** est créé à côté du programme,
avec 25 notes d'exemple pour ne pas commencer sur du vide.

Tu peux l'ouvrir dans l'Explorateur : ajouter, modifier, supprimer des fichiers
`.md`. JARVIS les relit au démarrage suivant. **Rien ne part sur Internet.**

## Changer ton nom et ta couleur

Engrenage **⚙** en haut à droite → section **Identité** :

- **Nom affiché** : tape le tien, appuie sur Entrée ;
- **Teinte** : Bleu, Violet, Ambre, Prune, ou **Auto** (suit l'heure).

C'est enregistré sur ton disque : ça te suit au redémarrage.

---

## Si Python n'est pas installé

La fenêtre noire te donnera le lien. En résumé :

1. **https://www.python.org/downloads/**
2. le gros bouton **Download Python**
3. lance le fichier téléchargé
4. ⚠️ **coche « Add python.exe to PATH »** sur le premier écran — la seule case
   de toute cette page qui compte
5. **Install Now**, puis reviens et double-clique à nouveau `LANCER-JARVIS.bat`

## Si Windows affiche un avertissement bleu

« Windows a protégé votre PC » → **Informations complémentaires** → **Exécuter
quand même**. C'est normal pour un fichier téléchargé.

## Et si je veux quand même l'ouvrir comme une app, sans rien installer ?

Dans **Edge** (ou Chrome), une fois JARVIS ouvert : menu **⋮** →
**Applications** → **Installer ce site en tant qu'application**.

Tu obtiens une icône dans le menu Démarrer et une fenêtre sans onglets. C'est la
même chose que l'étape 3, sans composant à installer.

---

## Le partage, plus tard

**Ce JARVIS ne sert qu'à cet ordinateur.** Ni ton téléphone, ni Anna, ni
Internet ne peuvent y entrer — c'est ce qui le rend simple.

Tu as **Tailscale** : c'est la seule façon propre d'y accéder depuis ton
téléphone plus tard, sans ouvrir ta box sur Internet. On le fera si tu le
demandes, calmement — ce n'est pas nécessaire pour commencer.

Et pour qu'Anna ait le sien, tout est prêt dans le dossier
(`MESSAGE-POUR-ANNA.txt`). Ça reste possible un autre jour, sans rien refaire
ici.
