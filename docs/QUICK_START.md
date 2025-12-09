# 🚀 DkbSign V3 - Feuille de Route de Déploiement Docker

## 📋 Résumé de l'Infrastructure

```
┌─────────────────────────────────────────────────────────┐
│                  Nginx (Reverse Proxy)                  │
│                   Ports: 80, 443                        │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
┌───────▼────────┐      ┌────────▼────────┐
│  Flask App     │      │     Redis       │
│  Port: 5000    │◄─────┤  Port: 6379     │
│  Gunicorn      │      │   Cache         │
└───────┬────────┘      └─────────────────┘
        │
┌───────▼────────┐
│  MySQL 8.0     │
│  Port: 3306    │
└────────────────┘
```

---

## 🎯 Feuille de Route Complète

### PHASE 1 : PRÉPARATION DU SERVEUR (15 min)

#### Étape 1.1 : Connexion et Mise à Jour
```bash
# Se connecter au serveur
ssh votre-utilisateur@ip-serveur

# Mise à jour du système
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y curl git nano
```

#### Étape 1.2 : Installation de Docker
```bash
# Télécharger le script d'installation Docker
curl -fsSL https://get.docker.com -o get-docker.sh

# Installer Docker
sudo sh get-docker.sh

# Vérifier l'installation
docker --version
docker compose version

# Ajouter l'utilisateur au groupe docker
sudo usermod -aG docker $USER

# Appliquer les changements
newgrp docker

# Tester Docker sans sudo
docker ps
```

**✅ Vérification** : La commande `docker ps` doit fonctionner sans erreur

---

### PHASE 2 : TÉLÉCHARGEMENT DE L'APPLICATION (5 min)

#### Étape 2.1 : Créer le Répertoire
```bash
# Créer le dossier d'installation
sudo mkdir -p /opt/dkbsign
sudo chown $USER:$USER /opt/dkbsign
cd /opt/dkbsign
```

#### Étape 2.2 : Télécharger le Code
```bash
# Option A : Via Git (si vous avez accès au repo)
git clone https://github.com/votre-org/DkbsignV3_Public.git .

# Option B : Via Archive (si vous avez reçu un fichier)
# Uploader le fichier puis :
tar -xzf dkbsign-v3.tar.gz
```

#### Étape 2.3 : Vérifier les Fichiers
```bash
# Lister les fichiers
ls -la

# Vous devez voir :
# - Dockerfile
# - docker-compose.yml
# - .env.example
# - app/
# - docker/
```

**✅ Vérification** : Tous les fichiers essentiels sont présents

---

### PHASE 3 : CONFIGURATION (10 min)

#### Étape 3.1 : Créer le Fichier de Configuration
```bash
# Copier le template
cp .env.example .env
```

#### Étape 3.2 : Générer les Clés Secrètes
```bash
# Générer SECRET_KEY
echo "SECRET_KEY=$(openssl rand -hex 32)"

# Générer JWT_SECRET_KEY
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)"

# Générer DB_ROOT_PASSWORD
echo "DB_ROOT_PASSWORD=$(openssl rand -base64 32)"

# Générer DB_PASSWORD
echo "DB_PASSWORD=$(openssl rand -base64 32)"

# Générer REDIS_PASSWORD
echo "REDIS_PASSWORD=$(openssl rand -base64 32)"
```

**📝 IMPORTANT** : Copiez ces valeurs, vous en aurez besoin !

#### Étape 3.3 : Éditer la Configuration
```bash
# Ouvrir le fichier .env
nano .env
```

**Paramètres à modifier dans .env** :

```bash
# 1. SÉCURITÉ (copier les valeurs générées ci-dessus)
SECRET_KEY=votre-secret-key-generee
JWT_SECRET_KEY=votre-jwt-secret-key-generee

# 2. BASE DE DONNÉES
DB_ROOT_PASSWORD=votre-db-root-password-genere
DB_NAME=dkbsignv3
DB_USER=dkbsign
DB_PASSWORD=votre-db-password-genere

# 3. REDIS
REDIS_PASSWORD=votre-redis-password-genere

# 4. EMAIL (exemple avec Gmail)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=votre-email@gmail.com
MAIL_PASSWORD=votre-mot-de-passe-application
MAIL_USE_TLS=True
MAIL_USE_SSL=False
MAIL_DEFAULT_SENDER=votre-email@gmail.com

# 5. APPLICATION
APP_URL=https://sign.votre-domaine.com
FLASK_ENV=production
DEBUG=False
```

**Sauvegarder** : `Ctrl+O` puis `Enter`, puis `Ctrl+X` pour quitter

**✅ Vérification** : Le fichier .env est configuré avec vos valeurs

---

### PHASE 4 : CONFIGURATION SSL (10 min)

#### Option A : Certificat Let's Encrypt (PRODUCTION)

```bash
# Installer Certbot
sudo apt-get install -y certbot

# Générer le certificat (remplacer par votre domaine)
sudo certbot certonly --standalone -d sign.votre-domaine.com

# Créer le dossier SSL
sudo mkdir -p docker/nginx/ssl

# Copier les certificats
sudo cp /etc/letsencrypt/live/sign.votre-domaine.com/fullchain.pem docker/nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/sign.votre-domaine.com/privkey.pem docker/nginx/ssl/key.pem

# Ajuster les permissions
sudo chmod 644 docker/nginx/ssl/cert.pem
sudo chmod 600 docker/nginx/ssl/key.pem
sudo chown $USER:$USER docker/nginx/ssl/*.pem
```

#### Option B : Certificat Auto-signé (TEST/DEV)

```bash
# Créer le dossier SSL
mkdir -p docker/nginx/ssl

# Générer le certificat auto-signé
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout docker/nginx/ssl/key.pem \
  -out docker/nginx/ssl/cert.pem \
  -subj "/C=FR/ST=IDF/L=Paris/O=VotreEntreprise/CN=sign.votre-domaine.com"
```

#### Étape 4.2 : Configurer Nginx
```bash
# Éditer la configuration Nginx
nano docker/nginx/conf.d/dkbsign.conf

# Remplacer "server_name _;" par votre domaine :
# server_name sign.votre-domaine.com;

# Sauvegarder : Ctrl+O, Enter, Ctrl+X
```

**✅ Vérification** : Les certificats SSL sont en place

---

### PHASE 5 : DÉPLOIEMENT (10 min)

#### Étape 5.1 : Rendre les Scripts Exécutables
```bash
# Rendre tous les scripts exécutables
chmod +x docker/scripts/*.sh
```

#### Étape 5.2 : Déploiement Automatique
```bash
# Lancer le script de déploiement
./docker/scripts/deploy.sh
```

**Le script va automatiquement** :
1. ✅ Vérifier les prérequis
2. ✅ Construire les images Docker
3. ✅ Démarrer tous les services (MySQL, Redis, App, Nginx)
4. ✅ Attendre que les services soient "healthy"
5. ✅ Exécuter les migrations de base de données
6. ✅ Afficher le statut final

**Durée estimée** : 5-10 minutes

#### OU Étape 5.2 Alternative : Déploiement Manuel
```bash
# Construction des images
docker compose build --no-cache

# Démarrage des services
docker compose up -d

# Attendre 30 secondes
sleep 30

# Vérifier le statut
docker compose ps

# Exécuter les migrations
docker compose exec app flask db upgrade
```

**✅ Vérification** : Tous les containers affichent "Up (healthy)"

---

### PHASE 6 : INITIALISATION (5 min)

#### Étape 6.1 : Vérifier les Services
```bash
# Vérifier que tous les containers sont démarrés
docker compose ps

# Résultat attendu :
# NAME              STATUS
# dkbsign_app       Up (healthy)
# dkbsign_db        Up (healthy)
# dkbsign_redis     Up (healthy)
# dkbsign_nginx     Up (healthy)
```

#### Étape 6.2 : Tester l'Endpoint de Santé
```bash
# Test local
curl http://localhost/health

# Résultat attendu :
# {"status":"healthy","service":"DkbSign V3 API","database":"connected"}
```

#### Étape 6.3 : Créer l'Utilisateur Administrateur
```bash
# Accéder au shell Flask
docker compose exec app flask shell
```

**Dans le shell Python, copier-coller** :
```python
from app import db
from app.models import User
from werkzeug.security import generate_password_hash

# Créer l'admin (MODIFIER L'EMAIL ET LE MOT DE PASSE)
admin = User(
    email='admin@votre-entreprise.com',
    name='Administrateur',
    password=generate_password_hash('MotDePasseSecurise123!')
)

db.session.add(admin)
db.session.commit()

print(f"✅ Utilisateur admin créé : {admin.email}")
exit()
```

**✅ Vérification** : L'utilisateur admin est créé

---

### PHASE 7 : CONFIGURATION DNS ET FIREWALL (5 min)

#### Étape 7.1 : Configuration DNS
```bash
# Chez votre fournisseur DNS, créer un enregistrement A :
# Type: A
# Nom: sign (ou votre sous-domaine)
# Valeur: IP_DE_VOTRE_SERVEUR
# TTL: 3600
```

#### Étape 7.2 : Configuration Firewall
```bash
# Installer UFW (si pas déjà installé)
sudo apt-get install -y ufw

# Autoriser SSH
sudo ufw allow 22/tcp

# Autoriser HTTP et HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Activer le firewall
sudo ufw --force enable

# Vérifier le statut
sudo ufw status
```

**✅ Vérification** : Le firewall est configuré

---

### PHASE 8 : TESTS FINAUX (5 min)

#### Étape 8.1 : Test Complet de Santé
```bash
# Exécuter le script de health check
./docker/scripts/health-check.sh
```

#### Étape 8.2 : Accès Web
```bash
# Ouvrir dans le navigateur :
# https://sign.votre-domaine.com

# Ou tester avec curl :
curl -k https://sign.votre-domaine.com/health
```

#### Étape 8.3 : Test de Connexion
```bash
# Se connecter avec les identifiants admin créés :
# Email: admin@votre-entreprise.com
# Mot de passe: MotDePasseSecurise123!
```

**✅ Vérification** : L'application est accessible et fonctionnelle

---

### PHASE 9 : CONFIGURATION POST-DÉPLOIEMENT (10 min)

#### Étape 9.1 : Configurer les Backups Automatiques
```bash
# Éditer le crontab
crontab -e

# Ajouter cette ligne (backup quotidien à 2h du matin)
0 2 * * * cd /opt/dkbsign && docker compose run --rm backup
```

#### Étape 9.2 : Configurer le Renouvellement SSL (Let's Encrypt uniquement)
```bash
# Éditer le crontab
sudo crontab -e

# Ajouter cette ligne (renouvellement quotidien à 3h du matin)
0 3 * * * certbot renew --quiet && cd /opt/dkbsign && docker compose restart nginx
```

#### Étape 9.3 : Créer un Backup Initial
```bash
# Créer le premier backup
docker compose run --rm backup

# Vérifier le backup
ls -lh backups/
```

**✅ Vérification** : Les tâches automatiques sont configurées

---

## 📊 COMMANDES DE GESTION QUOTIDIENNE

### Visualiser les Logs
```bash
# Logs de l'application (temps réel)
docker compose logs -f app

# Logs de tous les services
docker compose logs -f

# Dernières 100 lignes
docker compose logs --tail=100 app

# Logs d'un service spécifique
docker compose logs nginx
docker compose logs db
docker compose logs redis
```

### Gestion des Services
```bash
# Voir le statut
docker compose ps

# Redémarrer tous les services
docker compose restart

# Redémarrer un service spécifique
docker compose restart app

# Arrêter tous les services
docker compose stop

# Démarrer tous les services
docker compose start

# Arrêter et supprimer les containers (données préservées)
docker compose down
```

### Monitoring
```bash
# Statistiques en temps réel
docker stats

# Utilisation disque
df -h
docker system df

# Health check complet
./docker/scripts/health-check.sh

# Vérifier l'endpoint de santé
curl http://localhost/health
```

### Maintenance
```bash
# Nettoyer les images non utilisées
docker image prune -a

# Nettoyer tout (ATTENTION : supprime les images)
docker system prune -a

# Voir les logs d'un container spécifique
docker logs dkbsign_app

# Accéder au shell d'un container
docker compose exec app bash
docker compose exec db bash
```

### Backup et Restauration
```bash
# Backup manuel
docker compose run --rm backup

# Lister les backups
ls -lh backups/

# Restaurer depuis un backup
./docker/scripts/restore.sh backups/backup_20231207_020000.sql.gz
```

### Mise à Jour de l'Application
```bash
# Télécharger la nouvelle version
cd /opt/dkbsign
git pull origin main
# ou extraire la nouvelle archive

# Reconstruire et redémarrer
docker compose build --no-cache
docker compose up -d

# Vérifier les logs
docker compose logs -f app
```

---

## 🔧 DÉPANNAGE RAPIDE

### Problème : Container ne démarre pas
```bash
# Voir les logs d'erreur
docker compose logs app

# Reconstruire l'image
docker compose build --no-cache app
docker compose up -d app
```

### Problème : Erreur de connexion base de données
```bash
# Vérifier MySQL
docker compose ps db
docker compose logs db

# Redémarrer MySQL
docker compose restart db

# Attendre 10 secondes
sleep 10

# Redémarrer l'app
docker compose restart app
```

### Problème : Erreur 502 Bad Gateway
```bash
# Vérifier que l'app est démarrée
docker compose ps app

# Vérifier les logs
docker compose logs app
docker compose logs nginx

# Redémarrer les services
docker compose restart app nginx
```

### Problème : Manque d'espace disque
```bash
# Vérifier l'espace
df -h

# Nettoyer les logs anciens
find /opt/dkbsign/logs -name "*.log" -mtime +30 -delete

# Nettoyer Docker
docker system prune -a

# Nettoyer les backups anciens (>30 jours)
find /opt/dkbsign/backups -name "*.sql.gz" -mtime +30 -delete
```

---

## ✅ CHECKLIST DE DÉPLOIEMENT

Cochez chaque étape au fur et à mesure :

### Préparation
- [ ] Serveur accessible via SSH
- [ ] Docker installé et fonctionnel
- [ ] Code source téléchargé
- [ ] Fichiers vérifiés

### Configuration
- [ ] Fichier .env créé
- [ ] Clés secrètes générées
- [ ] Mots de passe configurés
- [ ] Configuration email testée
- [ ] Certificats SSL installés
- [ ] Configuration Nginx adaptée

### Déploiement
- [ ] Images Docker construites
- [ ] Services démarrés
- [ ] Health checks OK
- [ ] Migrations exécutées
- [ ] Utilisateur admin créé

### Post-Déploiement
- [ ] DNS configuré
- [ ] Firewall configuré
- [ ] Application accessible via HTTPS
- [ ] Backups automatiques configurés
- [ ] Renouvellement SSL configuré (Let's Encrypt)
- [ ] Tests de connexion réussis

---

## 📞 SUPPORT

### Informations à Fournir en Cas de Problème

```bash
# Collecter les informations de diagnostic
echo "=== SYSTEM INFO ===" > diagnostic.txt
uname -a >> diagnostic.txt
docker --version >> diagnostic.txt
docker compose version >> diagnostic.txt

echo "=== CONTAINERS STATUS ===" >> diagnostic.txt
docker compose ps >> diagnostic.txt

echo "=== APP LOGS ===" >> diagnostic.txt
docker compose logs --tail=100 app >> diagnostic.txt

echo "=== DISK SPACE ===" >> diagnostic.txt
df -h >> diagnostic.txt

# Envoyer diagnostic.txt au support
```

**Contact Support** :
- Email : support@dkbsign.com
- Documentation : DEPLOYMENT_GUIDE.md (guide complet)

---

## 🎓 RÉSUMÉ DES COMMANDES ESSENTIELLES

```bash
# DÉPLOIEMENT INITIAL
cd /opt/dkbsign
./docker/scripts/deploy.sh

# VÉRIFICATION
docker compose ps
curl http://localhost/health

# LOGS
docker compose logs -f app

# REDÉMARRAGE
docker compose restart

# BACKUP
docker compose run --rm backup

# MISE À JOUR
git pull && docker compose build --no-cache && docker compose up -d

# ARRÊT
docker compose stop
```

---

**🎉 Félicitations !**

Votre instance DkbSign V3 est maintenant opérationnelle !

**Temps total estimé** : 60-75 minutes

---

**Version** : 1.0.0  
**Date** : Décembre 2024  
**DkbSign V3** - Plateforme de Signature Électronique
