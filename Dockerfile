# JARVIS — image minimale, aucune dépendance à installer.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    JARVIS_HOST=0.0.0.0 \
    JARVIS_ACCESS_PATH=/data/access.json

WORKDIR /app

COPY . /app

# Utilisateur non privilégié + dossier de données inscriptible.
RUN useradd --system --uid 10001 jarvis \
 && mkdir -p /data \
 && chown -R jarvis:jarvis /data /app

USER jarvis

# Le port réel est imposé par l'hébergeur via la variable PORT.
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python3 -c "import os,sys,urllib.request; p=os.environ.get('PORT','8080'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{p}/api/session', timeout=4).status == 200 else 1)"

CMD ["python3", "-u", "server.py"]
