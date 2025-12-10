# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copie seulement requirements d'abord (cache optimal)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensuite le reste du code
COPY . .

# Port que ton Flask écoute (change 5000 si tu utilises un autre)
EXPOSE 5000

# Commande de démarrage (adapte si tu utilises gunicorn ou autre)
#CMD ["python", "run.py"]
# ou si ton fichier principal s'appelle autrement :
# CMD ["python", "main.py"]
# ou avec gunicorn (recommandé en prod) :
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "run:app"]