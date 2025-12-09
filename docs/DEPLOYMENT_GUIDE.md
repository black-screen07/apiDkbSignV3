# DkbSign V3 - Guide de Déploiement DevOps

## 📋 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Prérequis](#prérequis)
3. [Architecture](#architecture)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Déploiement](#déploiement)
7. [Monitoring et Maintenance](#monitoring-et-maintenance)
8. [Sécurité](#sécurité)
9. [Backup et Restauration](#backup-et-restauration)
10. [Troubleshooting](#troubleshooting)
11. [Scaling](#scaling)

---

## 🎯 Vue d'ensemble

DkbSign V3 est une application de signature électronique containerisée avec Docker, conçue pour un déploiement production-ready sur n'importe quel serveur.

### Stack Technique
- **Application**: Flask (Python 3.11)
- **Base de données**: MySQL 8.0
- **Cache**: Redis 7
- **Reverse Proxy**: Nginx
- **Containerisation**: Docker & Docker Compose
- **WSGI Server**: Gunicorn

---

## 🔧 Prérequis

### Serveur Minimum
- **OS**: Ubuntu 20.04+ / Debian 11+ / CentOS 8+ / RHEL 8+
- **CPU**: 2 cores
- **RAM**: 4 GB
- **Stockage**: 50 GB SSD
- **Réseau**: Connexion internet stable

### Serveur Recommandé (Production)
- **OS**: Ubuntu 22.04 LTS
- **CPU**: 4+ cores
- **RAM**: 8+ GB
- **Stockage**: 100+ GB SSD
- **Réseau**: 100 Mbps+

### Logiciels Requis
```bash
# Docker Engine 20.10+
docker --version

# Docker Compose 2.0+
docker-compose --version

# Git
git --version

# OpenSSL (pour les certificats SSL)
openssl version
```

---

## 🏗️ Architecture

### Containers

```
┌─────────────────────────────────────────────────────────┐
│                     Nginx (Port 80/443)                 │
│              Reverse Proxy + SSL Termination            │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
┌───────▼────────┐      ┌────────▼────────┐
│  Flask App     │      │     Redis       │
│  (Port 5000)   │◄─────┤  (Port 6379)    │
│  Gunicorn      │      │   Cache         │
└───────┬────────┘      └─────────────────┘
        │
        │
┌───────▼────────┐
│  MySQL 8.0     │
│  (Port 3306)   │
│  Database      │
└────────────────┘
```

### Volumes Persistants
- `mysql_data`: Données MySQL
- `redis_data`: Données Redis
- `app_data`: Données application
- `./certificates`: Certificats utilisateurs
- `./documents`: Documents signés
- `./signatures`: Signatures
- `./stamps`: Tampons
- `./logs`: Logs applicatifs

---

## 📦 Installation

### 1. Installation de Docker

#### Ubuntu/Debian
```bash
# Mise à jour du système
sudo apt-get update
sudo apt-get upgrade -y

# Installation des dépendances
sudo apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Ajout du repository Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Installation Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Vérification
sudo docker --version
sudo docker compose version
```

#### CentOS/RHEL
```bash
# Installation des dépendances
sudo yum install -y yum-utils

# Ajout du repository
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# Installation
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Démarrage du service
sudo systemctl start docker
sudo systemctl enable docker
```

### 2. Configuration de l'utilisateur Docker
```bash
# Ajouter l'utilisateur au groupe docker
sudo usermod -aG docker $USER

# Appliquer les changements (ou se reconnecter)
newgrp docker

# Vérifier
docker ps
```

### 3. Cloner le projet
```bash
# Cloner le repository
git clone https://github.com/votre-org/DkbsignV3_Public.git
cd DkbsignV3_Public

# Vérifier la structure
ls -la
```

---

## ⚙️ Configuration

### 1. Configuration de l'environnement

```bash
# Copier le fichier d'exemple
cp .env.example .env

# Éditer la configuration
nano .env
```

### 2. Variables d'environnement critiques

```bash
# Sécurité (GÉNÉRER DES VALEURS UNIQUES!)
SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET_KEY=$(openssl rand -hex 32)

# Base de données
DB_ROOT_PASSWORD=$(openssl rand -base64 32)
DB_NAME=dkbsignv3
DB_USER=dkbsign
DB_PASSWORD=$(openssl rand -base64 32)

# Redis
REDIS_PASSWORD=$(openssl rand -base64 32)

# Email (SMTP)
MAIL_SERVER=smtp.votre-domaine.com
MAIL_PORT=465
MAIL_USERNAME=no-reply@votre-domaine.com
MAIL_PASSWORD=votre-mot-de-passe-email
MAIL_USE_SSL=True
MAIL_DEFAULT_SENDER=no-reply@votre-domaine.com

# Application
APP_URL=https://votre-domaine.com
FLASK_ENV=production
DEBUG=False
```

### 3. Génération des certificats SSL

#### Option A: Let's Encrypt (Recommandé pour production)
```bash
# Installer certbot
sudo apt-get install -y certbot

# Générer le certificat
sudo certbot certonly --standalone -d votre-domaine.com -d www.votre-domaine.com

# Copier les certificats
sudo cp /etc/letsencrypt/live/votre-domaine.com/fullchain.pem docker/nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/votre-domaine.com/privkey.pem docker/nginx/ssl/key.pem
sudo chmod 644 docker/nginx/ssl/cert.pem
sudo chmod 600 docker/nginx/ssl/key.pem
```

#### Option B: Certificat auto-signé (Développement/Test)
```bash
# Créer le dossier SSL
mkdir -p docker/nginx/ssl

# Générer le certificat
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout docker/nginx/ssl/key.pem \
  -out docker/nginx/ssl/cert.pem \
  -subj "/C=FR/ST=IDF/L=Paris/O=DkbSign/CN=votre-domaine.com"
```

### 4. Configuration Nginx

Éditer `docker/nginx/conf.d/dkbsign.conf` pour adapter le `server_name`:

```nginx
server {
    listen 443 ssl http2;
    server_name votre-domaine.com www.votre-domaine.com;
    # ... reste de la configuration
}
```

---

## 🚀 Déploiement

### Déploiement Automatisé (Recommandé)

```bash
# Rendre le script exécutable
chmod +x docker/scripts/deploy.sh

# Lancer le déploiement
./docker/scripts/deploy.sh
```

Le script effectue automatiquement:
1. ✅ Vérification des prérequis
2. ✅ Création d'un backup de la base de données
3. ✅ Pull des images Docker
4. ✅ Build de l'application
5. ✅ Démarrage des services
6. ✅ Health checks
7. ✅ Migrations de base de données
8. ✅ Rollback automatique en cas d'erreur

### Déploiement Manuel

```bash
# 1. Build des images
docker-compose build --no-cache

# 2. Démarrage des services
docker-compose up -d

# 3. Vérifier les logs
docker-compose logs -f app

# 4. Vérifier le statut
docker-compose ps

# 5. Exécuter les migrations
docker-compose exec app flask db upgrade

# 6. Vérifier la santé
curl http://localhost/health
```

### Premier Démarrage

```bash
# Créer un utilisateur admin (optionnel)
docker-compose exec app flask shell
>>> from app import db
>>> from app.models import User
>>> admin = User(email='admin@dkbsign.com', name='Admin', is_admin=True)
>>> admin.set_password('ChangeMe123!')
>>> db.session.add(admin)
>>> db.session.commit()
>>> exit()
```

---

## 📊 Monitoring et Maintenance

### Health Checks

```bash
# Script de monitoring automatisé
chmod +x docker/scripts/health-check.sh
./docker/scripts/health-check.sh

# Endpoints de santé
curl http://localhost/health      # Santé globale
curl http://localhost/live        # Liveness probe
curl http://localhost/ready       # Readiness probe
```

### Logs

```bash
# Script de visualisation des logs
chmod +x docker/scripts/logs.sh

# Voir les logs de l'application
./docker/scripts/logs.sh -s app -n 100

# Suivre les logs en temps réel
./docker/scripts/logs.sh -s app -f

# Logs Nginx
./docker/scripts/logs.sh -s nginx -f

# Logs base de données
./docker/scripts/logs.sh -s db -n 50
```

### Métriques Docker

```bash
# Statistiques des containers
docker stats

# Utilisation disque
docker system df

# Logs d'un service spécifique
docker-compose logs --tail=100 -f app
```

### Nettoyage

```bash
# Nettoyer les images non utilisées
docker image prune -a

# Nettoyer les volumes non utilisés
docker volume prune

# Nettoyage complet (ATTENTION!)
docker system prune -a --volumes
```

---

## 🔒 Sécurité

### Checklist de Sécurité

- [ ] Certificats SSL/TLS configurés
- [ ] Mots de passe forts générés pour DB et Redis
- [ ] SECRET_KEY et JWT_SECRET_KEY uniques
- [ ] Firewall configuré (UFW/iptables)
- [ ] Ports exposés minimaux
- [ ] Backups automatisés activés
- [ ] Logs de sécurité activés
- [ ] Rate limiting configuré dans Nginx
- [ ] CORS configuré correctement
- [ ] Headers de sécurité activés

### Configuration Firewall (UFW)

```bash
# Installer UFW
sudo apt-get install -y ufw

# Configuration de base
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Autoriser SSH
sudo ufw allow 22/tcp

# Autoriser HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Activer le firewall
sudo ufw enable

# Vérifier le statut
sudo ufw status verbose
```

### Mise à jour de Sécurité

```bash
# Mise à jour du système
sudo apt-get update
sudo apt-get upgrade -y

# Mise à jour des images Docker
docker-compose pull
docker-compose up -d

# Redémarrage avec zero-downtime
docker-compose up -d --no-deps --build app
```

---

## 💾 Backup et Restauration

### Backup Automatique

```bash
# Rendre le script exécutable
chmod +x docker/scripts/backup.sh

# Backup manuel
docker-compose run --rm backup

# Configurer un cron job pour backup quotidien
crontab -e

# Ajouter cette ligne (backup tous les jours à 2h du matin)
0 2 * * * cd /path/to/DkbsignV3_Public && docker-compose run --rm backup
```

### Backup Manuel

```bash
# Backup de la base de données
docker-compose exec db mysqldump -u root -p${DB_ROOT_PASSWORD} ${DB_NAME} | gzip > backup_$(date +%Y%m%d).sql.gz

# Backup des fichiers
tar -czf files_backup_$(date +%Y%m%d).tar.gz documents/ certificates/ signatures/ stamps/
```

### Restauration

```bash
# Rendre le script exécutable
chmod +x docker/scripts/restore.sh

# Restaurer depuis un backup
./docker/scripts/restore.sh ./backups/backup_20231207_020000.sql.gz
```

---

## 🔧 Troubleshooting

### Problèmes Courants

#### 1. Container ne démarre pas
```bash
# Vérifier les logs
docker-compose logs app

# Vérifier la configuration
docker-compose config

# Reconstruire l'image
docker-compose build --no-cache app
docker-compose up -d app
```

#### 2. Erreur de connexion à la base de données
```bash
# Vérifier que MySQL est démarré
docker-compose ps db

# Vérifier les logs MySQL
docker-compose logs db

# Tester la connexion
docker-compose exec app flask shell
>>> from app import db
>>> db.session.execute('SELECT 1')
```

#### 3. Problèmes de permissions
```bash
# Corriger les permissions des dossiers
sudo chown -R 1000:1000 documents/ certificates/ signatures/ stamps/ logs/
sudo chmod -R 755 documents/ certificates/ signatures/ stamps/
sudo chmod -R 777 logs/
```

#### 4. Erreur 502 Bad Gateway (Nginx)
```bash
# Vérifier que l'app est démarrée
docker-compose ps app

# Vérifier les logs Nginx
docker-compose logs nginx

# Vérifier la connectivité
docker-compose exec nginx ping app
```

#### 5. Manque d'espace disque
```bash
# Vérifier l'espace disque
df -h

# Nettoyer les logs
docker-compose exec app find /app/logs -name "*.log" -mtime +30 -delete

# Nettoyer Docker
docker system prune -a
```

### Commandes de Diagnostic

```bash
# État des services
docker-compose ps

# Ressources utilisées
docker stats

# Logs en temps réel
docker-compose logs -f

# Inspecter un container
docker inspect dkbsign_app

# Accéder au shell d'un container
docker-compose exec app bash

# Vérifier la configuration réseau
docker network inspect dkbsignv3_public_dkbsign_network
```

---

## 📈 Scaling

### Scaling Horizontal (Multiple Workers)

Éditer `docker-compose.yml`:

```yaml
app:
  deploy:
    replicas: 3
  environment:
    - GUNICORN_WORKERS=4
```

### Scaling avec Load Balancer

```yaml
# docker-compose.prod.yml
services:
  app:
    deploy:
      replicas: 3
    
  nginx:
    depends_on:
      - app
    # Nginx fera automatiquement du load balancing
```

Déployer:
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale app=3
```

### Optimisation des Performances

#### 1. Augmenter les workers Gunicorn
```bash
# Dans .env
GUNICORN_WORKERS=8  # (2 x CPU cores) + 1
GUNICORN_THREADS=4
```

#### 2. Optimiser MySQL
```bash
# Créer docker/mysql/my.cnf
[mysqld]
max_connections = 200
innodb_buffer_pool_size = 2G
innodb_log_file_size = 512M
query_cache_size = 64M
```

#### 3. Optimiser Redis
```bash
# Dans docker-compose.yml
redis:
  command: redis-server --maxmemory 1gb --maxmemory-policy allkeys-lru
```

---

## 📞 Support

### Logs Importants

- **Application**: `./logs/app.log`
- **Nginx Access**: Container logs
- **Nginx Error**: Container logs
- **MySQL**: Container logs

### Commandes Utiles

```bash
# Redémarrer un service
docker-compose restart app

# Reconstruire et redémarrer
docker-compose up -d --build app

# Arrêter tous les services
docker-compose down

# Arrêter et supprimer les volumes (ATTENTION!)
docker-compose down -v

# Exporter les logs
docker-compose logs > dkbsign_logs_$(date +%Y%m%d).txt
```

---

## 📝 Checklist de Déploiement

### Avant le Déploiement
- [ ] Serveur configuré avec les prérequis
- [ ] Docker et Docker Compose installés
- [ ] Fichier `.env` configuré avec des valeurs de production
- [ ] Certificats SSL générés et installés
- [ ] Firewall configuré
- [ ] Domaine DNS pointant vers le serveur

### Pendant le Déploiement
- [ ] Backup de la base de données existante (si migration)
- [ ] Build des images Docker
- [ ] Démarrage des services
- [ ] Vérification des health checks
- [ ] Exécution des migrations
- [ ] Tests de fumée (smoke tests)

### Après le Déploiement
- [ ] Vérifier tous les endpoints critiques
- [ ] Configurer les backups automatiques
- [ ] Configurer le monitoring
- [ ] Tester la restauration depuis backup
- [ ] Documenter les credentials
- [ ] Former l'équipe sur les procédures

---

## 🎓 Ressources Additionnelles

- [Documentation Docker](https://docs.docker.com/)
- [Documentation Flask](https://flask.palletsprojects.com/)
- [Documentation Nginx](https://nginx.org/en/docs/)
- [Documentation MySQL](https://dev.mysql.com/doc/)
- [Best Practices Docker](https://docs.docker.com/develop/dev-best-practices/)

---

**Version**: 1.0.0  
**Dernière mise à jour**: Décembre 2024  
**Auteur**: DkbSign DevOps Team
