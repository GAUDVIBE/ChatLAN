CHAT LAN - Demarrage sur Mac
=============================

Prerequis
---------
- Python 3 (installe par defaut sur macOS recent).
  Pour verifier, ouvrir Terminal et taper :
      python3 --version
  Si Mac propose d'installer les Command Line Tools, accepter.

Lancement
---------
1. Ouvrir Terminal.
2. Aller dans le dossier de l'app :
      cd /Users/gaudry/test-claude/app
3. Demarrer le serveur :
      python3 chat.py

Le terminal affiche deux URLs :
   Local  : http://localhost:8080
   Reseau : http://<ip-du-mac>:8080

Connexion depuis les autres machines
------------------------------------
Sur tout appareil connecte au meme Wi-Fi/LAN, ouvrir l'URL "Reseau"
dans un navigateur, saisir un nom, et chatter.

Si on ne connait pas l'IP du Mac, dans un autre Terminal :
      ipconfig getifaddr en0     (Wi-Fi)
      ipconfig getifaddr en1     (Ethernet/USB-C)

L'IP actuelle de ce Mac est : 10.10.100.3
URL Reseau complete : http://10.10.100.3:8080

Premiere connexion : macOS peut demander l'autorisation reseau pour
Python. Cliquer "Autoriser".

Arret
-----
Dans le Terminal qui fait tourner le serveur : Ctrl+C.

Notes
-----
- Aucune dependance a installer : le serveur utilise uniquement la
  bibliotheque standard de Python.
- L'historique des messages (200 derniers) est en memoire et perdu a
  l'arret.
- Pour changer le port, editer la ligne PORT = 8080 en haut de chat.py.
