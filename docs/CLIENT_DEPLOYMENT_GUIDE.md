# DkbSign V3 - Guide de Déploiement Client

## 📘 Introduction

Ce guide simplifié est destiné aux clients qui souhaitent déployer **DkbSign V3** sur leur propre infrastructure (Linux ou Windows).

### Prérequis Serveur

**Linux - Minimum** : Ubuntu 20.04+, 2 CPU, 4 GB RAM, 50 GB SSD  
**Linux - Recommandé** : Ubuntu 22.04 LTS, 4 CPU, 8 GB RAM, 100 GB SSD

**Windows - Minimum** : Windows Server 2019+, 2 CPU, 8 GB RAM, 50 GB SSD  
**Windows - Recommandé** : Windows Server 2022, 4 CPU, 16 GB RAM, 100 GB SSD

---

## 📑 Table des Matières

1. [Installation Linux](#-installation-linux)
2. [Installation Windows](#-installation-windows)
3. [Commandes Utiles](#-commandes-utiles)
4. [Support](#-support)

---

# 🐧 Installation Linux

## 🚀 Installation Rapide

### 1. Installer Docker

```bash
# Mise à jour système
sudo apt-get update && sudo apt-get upgrade -y

# Installation Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Ajouter utilisateur au groupe docker
sudo usermod -aG docker $USER
newgrp docker
```

### 2. Télécharger l'Application

```bash
# Créer le dossier
mkdir -p /opt/dkbsign && cd /opt/dkbsign

# Cloner ou extraire l'application
git clone <votre-repo> .
# ou
tar -xzf dkbsign-v3.tar.gz
```

### 3. Configurer l'Application

```bash
# Copier la configuration
cp .env.example .env

# Générer les clés secrètes
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env.tmp
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)" >> .env.tmp
echo "DB_ROOT_PASSWORD=$(openssl rand -base64 32)" >> .env.tmp
echo "DB_PASSWORD=$(openssl rand -base64 32)" >> .env.tmp
echo "REDIS_PASSWORD=$(openssl rand -base64 32)" >> .env.tmp

# Éditer .env avec vos paramètres
nano .env
```

**Paramètres à configurer dans .env** :
- Email SMTP (MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD)
- Domaine (APP_URL)
- Copier les mots de passe générés ci-dessus

### 4. Configurer SSL

```bash
# Option A : Let's Encrypt (Production)
sudo apt-get install -y certbot
sudo certbot certonly --standalone -d votre-domaine.com
sudo mkdir -p docker/nginx/ssl
sudo cp /etc/letsencrypt/live/votre-domaine.com/fullchain.pem docker/nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/votre-domaine.com/privkey.pem docker/nginx/ssl/key.pem

# Option B : Auto-signé (Test)
mkdir -p docker/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout docker/nginx/ssl/key.pem \
  -out docker/nginx/ssl/cert.pem \
  -subj "/C=FR/O=VotreEntreprise/CN=votre-domaine.com"
```

### 5. Déployer

```bash
# Rendre le script exécutable
chmod +x docker/scripts/deploy.sh

# Déployer
./docker/scripts/deploy.sh
```

### 6. Créer l'Utilisateur Admin

```bash
docker compose exec app flask shell

# Dans le shell Python :
from app import db
from app.models import User
from werkzeug.security import generate_password_hash

admin = User(
    email='admin@votre-entreprise.com',
    name='Administrateur',
    password=generate_password_hash('VotreMotDePasse123!')
)
db.session.add(admin)
db.session.commit()
exit()
```

### 7. Vérifier

```bash
# Vérifier les services
docker compose ps

# Tester l'application
curl http://localhost/health
```

---

# 🪟 Installation Windows

## 💻 Prérequis Windows

- Windows Server 2019+ ou Windows 10/11 Pro
- Hyper-V activé
- 8 GB RAM minimum (16 GB recommandé)

## 🔧 Installation Étape par Étape

### 1. Activer Hyper-V

**PowerShell (Administrateur)** :
```powershell
# Activer Hyper-V
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All

# Redémarrer
Restart-Computer
```

### 2. Installer Docker Desktop

```powershell
# Télécharger depuis : https://www.docker.com/products/docker-desktop
# Ou via PowerShell :
Invoke-WebRequest -Uri "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe" -OutFile "DockerDesktopInstaller.exe"

# Installer
Start-Process -Wait -FilePath ".\DockerDesktopInstaller.exe" -ArgumentList "install"

# Redémarrer
Restart-Computer

# Vérifier
docker --version
docker compose version
```

### 3. Télécharger l'Application

```powershell
# Créer le dossier
New-Item -Path "C:\DkbSign" -ItemType Directory -Force
Set-Location "C:\DkbSign"

# Télécharger (Git ou Archive)
git clone <votre-repo> .
# ou
Expand-Archive -Path "dkbsign-v3.zip" -DestinationPath "."
```

### 4. Configurer l'Application

```powershell
# Copier la configuration
Copy-Item ".env.example" -Destination ".env"

# Générer les clés secrètes
@"
function Generate-RandomKey {
    param([int]`$length = 32)
    `$bytes = New-Object byte[] `$length
    [Security.Cryptography.RNGCryptoServiceProvider]::Create().GetBytes(`$bytes)
    return [Convert]::ToBase64String(`$bytes)
}

Write-Host "SECRET_KEY=" -NoNewline
Generate-RandomKey -length 32
Write-Host "JWT_SECRET_KEY=" -NoNewline
Generate-RandomKey -length 32
Write-Host "DB_ROOT_PASSWORD=" -NoNewline
Generate-RandomKey -length 24
Write-Host "DB_PASSWORD=" -NoNewline
Generate-RandomKey -length 24
Write-Host "REDIS_PASSWORD=" -NoNewline
Generate-RandomKey -length 24
"@ | Out-File -FilePath "generate-keys.ps1" -Encoding UTF8

# Exécuter
powershell -ExecutionPolicy Bypass -File .\generate-keys.ps1

# Éditer .env
notepad .env
```

**Paramètres à configurer dans .env** :
```bash
# Copier les clés générées
SECRET_KEY=votre-cle-generee
JWT_SECRET_KEY=votre-jwt-generee
DB_ROOT_PASSWORD=votre-db-root-password
DB_PASSWORD=votre-db-password
REDIS_PASSWORD=votre-redis-password

# Email (exemple Office 365)
MAIL_SERVER=smtp.office365.com
MAIL_PORT=587
MAIL_USERNAME=no-reply@votre-entreprise.com
MAIL_PASSWORD=votre-mot-de-passe
MAIL_USE_TLS=True

# Application
APP_URL=https://sign.votre-entreprise.com
```

### 5. Adapter docker-compose.yml pour Windows

```powershell
notepad docker-compose.yml
```

**Modifier les volumes** :
```yaml
volumes:
  - C:/DkbSign/certificates:/app/certificates
  - C:/DkbSign/documents:/app/documents
  - C:/DkbSign/signatures:/app/signatures
  - C:/DkbSign/stamps:/app/stamps
  - C:/DkbSign/logs:/app/logs
```

### 6. Configurer SSL

**Option A : Certificat Auto-signé (Test)** :
```powershell
# Créer le dossier
New-Item -Path "docker\nginx\ssl" -ItemType Directory -Force

# Générer le certificat
$cert = New-SelfSignedCertificate -DnsName "sign.votre-entreprise.com" -CertStoreLocation "Cert:\LocalMachine\My" -NotAfter (Get-Date).AddYears(1)

# Exporter (nécessite OpenSSL pour conversion en PEM)
Export-Certificate -Cert $cert -FilePath "docker\nginx\ssl\cert.pem" -Type CERT
```

**Option B : Let's Encrypt avec Win-ACME** :
```powershell
# Télécharger Win-ACME
Invoke-WebRequest -Uri "https://github.com/win-acme/win-acme/releases/latest/download/win-acme.v2.2.5.1571.x64.pluggable.zip" -OutFile "win-acme.zip"
Expand-Archive -Path "win-acme.zip" -DestinationPath "C:\win-acme"

# Exécuter et suivre les instructions
C:\win-acme\wacs.exe
```

### 7. Créer les Dossiers

```powershell
# Créer tous les dossiers requis
New-Item -Path "certificates" -ItemType Directory -Force
New-Item -Path "documents" -ItemType Directory -Force
New-Item -Path "signatures" -ItemType Directory -Force
New-Item -Path "stamps" -ItemType Directory -Force
New-Item -Path "logs" -ItemType Directory -Force
New-Item -Path "backups" -ItemType Directory -Force
```

### 8. Déployer

```powershell
# Build et démarrage
docker-compose build --no-cache
docker-compose up -d

# Attendre 30 secondes
Start-Sleep -Seconds 30

# Vérifier
docker-compose ps

# Exécuter les migrations
docker-compose exec app flask db upgrade
```

### 9. Créer l'Utilisateur Admin

```powershell
# Accéder au shell Flask
docker-compose exec app flask shell
```

**Dans le shell Python** :
```python
from app import db
from app.models import User
from werkzeug.security import generate_password_hash

admin = User(
    email='admin@votre-entreprise.com',
    name='Administrateur',
    password=generate_password_hash('VotreMotDePasse123!')
)
db.session.add(admin)
db.session.commit()
exit()
```

### 10. Configurer le Pare-feu

```powershell
# Ouvrir les ports
New-NetFirewallRule -DisplayName "DkbSign HTTP" -Direction Inbound -LocalPort 80 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "DkbSign HTTPS" -Direction Inbound -LocalPort 443 -Protocol TCP -Action Allow

# Vérifier
Get-NetFirewallRule -DisplayName "DkbSign*"
```

### 11. Configurer le Démarrage Automatique

```powershell
# Créer le script de démarrage
@"
Set-Location C:\DkbSign
docker-compose up -d
"@ | Out-File -FilePath "C:\DkbSign\start-dkbsign.ps1" -Encoding UTF8

# Créer la tâche planifiée
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File C:\DkbSign\start-dkbsign.ps1"
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName "DkbSign Startup" -Action $action -Trigger $trigger -Principal $principal -Settings $settings
```

### 12. Vérifier

```powershell
# Test de santé
Invoke-WebRequest -Uri "http://localhost/health" -UseBasicParsing

# Ouvrir dans le navigateur
Start-Process "https://sign.votre-entreprise.com"
```

## 📊 Scripts Utiles Windows

### Script de Monitoring

```powershell
# Créer monitor-dkbsign.ps1
@"
Set-Location C:\DkbSign
Write-Host "=== DkbSign V3 - Monitoring ===" -ForegroundColor Green
Write-Host "Date: `$(Get-Date)" -ForegroundColor Yellow

# Statut des containers
docker-compose ps

# Health check
try {
    `$response = Invoke-WebRequest -Uri "http://localhost/health" -UseBasicParsing
    Write-Host "✅ Application healthy" -ForegroundColor Green
} catch {
    Write-Host "❌ Application unhealthy" -ForegroundColor Red
}

# Espace disque
Get-PSDrive C | Select-Object Used, Free
"@ | Out-File -FilePath "C:\DkbSign\monitor-dkbsign.ps1" -Encoding UTF8
```

### Script de Backup

```powershell
# Créer backup-dkbsign.ps1
@"
Set-Location C:\DkbSign
docker-compose run --rm backup
Write-Host "Backup terminé!" -ForegroundColor Green
"@ | Out-File -FilePath "C:\DkbSign\backup-dkbsign.ps1" -Encoding UTF8

# Tâche planifiée quotidienne (2h du matin)
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File C:\DkbSign\backup-dkbsign.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName "DkbSign Daily Backup" -Action $action -Trigger $trigger -Principal $principal
```

---

## 🔧 Commandes Utiles

### Linux
```bash
# Voir les logs
docker compose logs -f app

# Redémarrer
docker compose restart

# Arrêter
docker compose stop

# Backup
docker compose run --rm backup

# Mise à jour
git pull && docker compose build --no-cache && docker compose up -d
```

### Windows
```powershell
# Voir les logs
docker-compose logs -f app

# Redémarrer
docker-compose restart

# Arrêter
docker-compose stop

# Backup
docker-compose run --rm backup

# Mise à jour
git pull
docker-compose build --no-cache
docker-compose up -d

# Monitoring
.\monitor-dkbsign.ps1

# Espace disque
Get-PSDrive C
docker system df
```

---

## 📞 Support

**Email** : support@dkbsign.com  
**Documentation complète** : Voir DEPLOYMENT_GUIDE.md (Linux) et ce guide (Windows)

---

**Version** : 1.0.0 | **Date** : Décembre 2024
