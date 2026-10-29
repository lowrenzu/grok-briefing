Réparer l'accès de JARVIS — la fiche à garder sous les yeux
===========================================================

Il y a CINQ lignes dans Render → Environment. Une seule est fausse.
Voici les cinq, au caractère près. Rien d'autre à comprendre.

KEY (à gauche)                    VALUE (à droite)
-------------------------------------------------------------
JARVIS_GOOGLE_CLIENT_ID            l'identifiant client Google
JARVIS_GOOGLE_CLIENT_SECRET        le code secret Google
JARVIS_ALLOWED_EMAILS              funk.e.lee@gmail.com
JARVIS_ADMIN_EMAIL                 funk.e.lee@gmail.com
JARVIS_PUBLIC_URL                  https://jarvis-lowrenzu.onrender.com


LES TROIS CHOSES À REGARDER
-------------------------------------------------------------
1. Le KEY de gauche est écrit EN ENTIER, avec ses tirets bas.
   Le piège : ..._EMAIL sans le S final.

2. Le VALUE n'est jamais vide.

3. Pour l'adresse e-mail : aucun guillemet, aucun espace avant ou après.
   Exactement :  funk.e.lee@gmail.com


COMMENT SAVOIR LAQUELLE EST FAUSSE
-------------------------------------------------------------
JARVIS a répondu ceci sur ton adresse :

   « Aucune adresse autorisée n'est configurée »

Donc c'est la ligne JARVIS_ALLOWED_EMAILS : son KEY est mal écrit,
ou son VALUE est vide.

(La porte Google, elle, fonctionne : JARVIS a bien lu
l'identifiant client et le code secret. C'est déjà acquis.)


ENSUITE
-------------------------------------------------------------
Un seul bouton :   Save, rebuild, and deploy
Puis attendre le statut « Live » (2 à 4 minutes).

Vérification qui compte : ouvrir la même adresse dans une fenêtre
de navigation privée. On doit tomber sur une page GOOGLE, et non
sur le cockpit de JARVIS.
