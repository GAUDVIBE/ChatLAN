#!/bin/bash
# Raccourci de lancement de ChatLAN (double-clic depuis le Finder, macOS).
# Se place dans le dossier du script lui-meme : marche quel que soit l'emplacement du clone.
cd "$(dirname "$0")" || { echo "Impossible d'acceder au dossier de l'app."; exit 1; }

PORT=$(grep -m1 '^PORT' chat.py | tr -dc '0-9')
PORT=${PORT:-8090}

# Si une instance tourne deja sur ce port, on la reutilise
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ChatLAN tourne deja sur le port $PORT."
else
  echo "Demarrage de ChatLAN sur le port $PORT..."
fi

# Ouvre le navigateur peu apres le demarrage
( sleep 1; open "http://localhost:$PORT" ) >/dev/null 2>&1 &

# Lance le serveur (Ctrl+C pour arreter ; fermer cette fenetre arrete aussi le serveur)
exec python3 chat.py
