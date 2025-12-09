# 🪟 DkbSign V3 - Déploiement Rapide Windows

## 📋 Guide Simplifié pour Windows Server

**Temps estimé** : 30-40 minutes

---

## ✅ Prérequis

- Windows Server 2019+ ou Windows 10/11 Pro
- 8 GB RAM minimum
- 50 GB d'espace disque
- Accès administrateur

---

## 🚀 Étapes de Déploiement

### 1️⃣ Activer Hyper-V (5 min)

Ouvrir **PowerShell en Administrateur** :

```powershell
# Activer Hyper-V
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All

# Redémarrer
Restart-Computer
```

---

### 2️⃣ Installer Docker Desktop (10 min)

Après le redémarrage :

```powershell
# Télécharger Docker Desktop
Invoke-WebRequest -Uri "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe" -OutFile "DockerDesktopInstaller.exe"

# Installer
Start-Process -Wait -FilePath ".\DockerDesktopInstaller.exe" -ArgumentList "install"

# Redémarrer
Restart-Computer
```

**Vérifier l'installation** :
```powershell
docker --version
docker compose version
```

---

### 3️⃣ Préparer l'Application (5 min)

```powershell
# Créer le dossier
New-Item -Path "C:\DkbSign" -ItemType Directory -Force
Set-Location "C:\DkbSign"

# Copier vos fichiers ici ou télécharger
# Si vous avez une archive :
Expand-Archive -Path "dkbsign-v3.zip" -DestinationPath "."

# Si vous avez Git :
git clone <votre-repo> .
```

---

### 4️⃣ Configurer l'Application (10 min)

```powershell
# Copier la configuration
Copy-Item ".env.example" -Destination ".env"

# Générer les clés secrètes
@"
function Generate-Key { 
    `$bytes = New-Object byte[] 32
    [Security.Cryptography.RNGCryptoServiceProvider]::Create().GetBytes(`$bytes)
    [Convert]::ToBase64String(`$bytes)
}
Write-Host "SECRET_KEY=" -NoNewline; Generate-Key
Write-Host "JWT_SECRET_KEY=" -NoNewline; Generate-Key
Write-Host "DB_ROOT_PASSWORD=" -NoNewline; Generate-Key
Write-Host "DB_PASSWORD=" -NoNewline; Generate-Key
Write-Host "REDIS_PASSWORD=" -NoNewline; Generate-Key
"@ | Out-File "generate-keys.ps1"

# Exécuter
powershell -ExecutionPolicy Bypass -File .\generate-keys.ps1
```

**Éditer le fichier .env** :
```powershell
notepad .env
```

**Copier les clés générées et configurer** :
```bash
# Coller les clés générées
SECRET_KEY=votre-cle-generee
JWT_SECRET_KEY=votre-jwt-generee
DB_ROOT_PASSWORD=votre-db-root-password
DB_PASSWORD=votre-db-password
REDIS_PASSWORD=votre-redis-password

# Email (exemple)
MAIL_SERVER=smtp.office365.com
MAIL_PORT=587
MAIL_USERNAME=no-reply@votre-entreprise.com
MAIL_PASSWORD=votre-mot-de-passe
MAIL_USE_TLS=True
MAIL_USE_SSL=False

# Application
APP_URL=https://votre-domaine.com
FLASK_ENV=production
DEBUG=False
```

**Adapter docker-compose.yml** :
```powershell
notepad docker-compose.yml
```

Modifier les chemins des volumes :
```yaml
volumes:
  - C:/DkbSign/certificates:/app/certificates
  - C:/DkbSign/documents:/app/documents
  - C:/DkbSign/signatures:/app/signatures
  - C:/DkbSign/stamps:/app/stamps
  - C:/DkbSign/logs:/app/logs
```

---

### 5️⃣ Créer les Dossiers (2 min)

```powershell
# Créer tous les dossiers nécessaires
New-Item -Path "certificates" -ItemType Directory -Force
New-Item -Path "documents" -ItemType Directory -Force
New-Item -Path "signatures" -ItemType Directory -Force
New-Item -Path "stamps" -ItemType Directory -Force
New-Item -Path "logs" -ItemType Directory -Force
New-Item -Path "backups" -ItemType Directory -Force
New-Item -Path "docker\nginx\ssl" -ItemType Directory -Force
```

---

### 6️⃣ Configurer SSL (5 min)

**Option Simple - Certificat Auto-signé** :
```powershell
# Générer un certificat de test
$cert = New-SelfSignedCertificate -DnsName "localhost" -CertStoreLocation "Cert:\LocalMachine\My" -NotAfter (Get-Date).AddYears(1)

# Exporter (nécessite conversion manuelle en PEM)
# Pour production, utilisez un vrai certificat SSL
```

**Pour Production** : Placez vos certificats SSL dans `docker\nginx\ssl\` :
- `cert.pem` : Votre certificat
- `key.pem` : Votre clé privée

---

### 7️⃣ Déployer l'Application (5 min)

```powershell
# Build et démarrage
docker-compose build --no-cache
docker-compose up -d

# Attendre 30 secondes
Start-Sleep -Seconds 30

# Vérifier le statut
docker-compose ps
```

**Résultat attendu** :
```
NAME              STATUS
dkbsign_app       Up (healthy)
dkbsign_db        Up (healthy)
dkbsign_redis     Up (healthy)
dkbsign_nginx     Up (healthy)
```

---

### 8️⃣ Initialiser la Base de Données (2 min)

```powershell
# Exécuter les migrations
docker-compose exec app flask db upgrade
```

---

### 9️⃣ Créer l'Utilisateur Admin (3 min)

```powershell
# Accéder au shell Flask
docker-compose exec app flask shell
```

**Dans le shell Python, copier-coller** :
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
print("✅ Admin créé avec succès!")
exit()
```

---

### 🔟 Ouvrir le Pare-feu (2 min)

```powershell
# Autoriser HTTP et HTTPS
New-NetFirewallRule -DisplayName "DkbSign HTTP" -Direction Inbound -LocalPort 80 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "DkbSign HTTPS" -Direction Inbound -LocalPort 443 -Protocol TCP -Action Allow
```

---

### 1️⃣1️⃣ Tester l'Application (1 min)

```powershell
# Test de santé
Invoke-WebRequest -Uri "http://localhost/health" -UseBasicParsing

# Ouvrir dans le navigateur
Start-Process "http://localhost"
```

---

## ✅ Déploiement Terminé !

Votre application est maintenant accessible à :
- **Local** : http://localhost
- **Réseau** : http://votre-ip-serveur

---

## 🔧 Commandes Utiles

### Voir les Logs
```powershell
docker-compose logs -f app
```

### Redémarrer
```powershell
docker-compose restart
```

### Arrêter
```powershell
docker-compose stop
```

### Démarrer
```powershell
docker-compose start
```

### Backup Manuel
```powershell
docker-compose run --rm backup
```

### Mise à Jour
```powershell
# Télécharger la nouvelle version
git pull

# Rebuild et redémarrer
docker-compose build --no-cache
docker-compose up -d
```

---

## 🔄 Démarrage Automatique

Pour que l'application démarre automatiquement au démarrage de Windows :

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

---

## 📊 Backup Automatique

Pour configurer un backup quotidien à 2h du matin :

```powershell
# Créer le script de backup
@"
Set-Location C:\DkbSign
docker-compose run --rm backup
"@ | Out-File -FilePath "C:\DkbSign\backup-dkbsign.ps1" -Encoding UTF8

# Créer la tâche planifiée
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File C:\DkbSign\backup-dkbsign.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName "DkbSign Daily Backup" -Action $action -Trigger $trigger -Principal $principal
```

---

## ❓ Problèmes Courants

### Docker ne démarre pas
```powershell
# Vérifier Hyper-V
Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V

# Redémarrer le service Docker
Restart-Service Docker
```

### Les containers ne démarrent pas
```powershell
# Voir les logs
docker-compose logs

# Reconstruire
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Port 80 déjà utilisé (IIS)
```powershell
# Arrêter IIS
Stop-Service W3SVC
Set-Service W3SVC -StartupType Disabled
```

### Erreur de permissions
```powershell
# Donner les permissions
icacls "C:\DkbSign" /grant Everyone:F /T
```

---

## 📞 Support

**Email** : support@dkbsign.com  
**Documentation complète** : Voir CLIENT_DEPLOYMENT_GUIDE.md

---

## 📝 Checklist de Déploiement

- [ ] Hyper-V activé
- [ ] Docker Desktop installé
- [ ] Application téléchargée dans C:\DkbSign
- [ ] Fichier .env configuré avec les clés générées
- [ ] Chemins Windows adaptés dans docker-compose.yml
- [ ] Dossiers créés
- [ ] Certificats SSL en place
- [ ] Application déployée (docker-compose up -d)
- [ ] Migrations exécutées
- [ ] Utilisateur admin créé
- [ ] Pare-feu configuré
- [ ] Test de santé OK
- [ ] Démarrage automatique configuré
- [ ] Backup automatique configuré

---

**Version** : 1.0.0  
**Date** : Décembre 2024  
**DkbSign V3** - Déploiement Simplifié Windows
