# 📋 Système de Logging - DkbSign V3

## 📁 Fichiers de logs

Ce dossier contient les fichiers de logs pour le débogage et le monitoring de l'application.

### Fichiers principaux

- **`signature_debug.log`** : Logs détaillés du processus de signature
  - Chargement des images de signature
  - Traitement de chaque signataire
  - Étapes de la signature PDF
  - Informations sur les images PIL (taille, mode, type)

- **`api_requests.log`** : Logs des requêtes API
  - Endpoints appelés
  - Utilisateurs authentifiés
  - Paramètres des requêtes

- **`errors.log`** : Logs des erreurs critiques
  - Exceptions avec traceback complet
  - Contexte de l'erreur
  - Timestamp précis

### Rotation des fichiers

- **Taille maximale** : 10 MB par fichier
- **Fichiers conservés** : 5 versions (`.log`, `.log.1`, `.log.2`, etc.)
- **Rotation automatique** : Quand un fichier atteint 10 MB

## 🔍 Comment lire les logs

### Format des logs

```
[2025-10-09 01:58:30] INFO [signature_debug.sign_upload_multiple_documents:255] Utilisateur authentifié: user@example.com (Type: individual)
```

- **Timestamp** : `[2025-10-09 01:58:30]`
- **Niveau** : `INFO`, `DEBUG`, `WARNING`, `ERROR`, `CRITICAL`
- **Module.Fonction:Ligne** : `[signature_debug.sign_upload_multiple_documents:255]`
- **Message** : Le contenu du log

### Sessions de log

Chaque requête `/v3/sign-upload-multiple` crée une session avec :

```
================================================================================
NOUVELLE SESSION: 20251009_015830_123456
================================================================================
... logs de la session ...
✅ SUCCÈS - Session 20251009_015830_123456: 2 documents signés avec succès
================================================================================
```

### Logs d'images

Les images de signature sont tracées avec des informations détaillées :

```
[Signataire 0] Chargée via clé 'signature_image_0' - signature.png - Image: {'type': "<class 'PIL.Image.Image'>", 'size': (150, 50), 'mode': 'RGB', 'format': 'PNG'}
```

## 🛠️ Débogage en production

### 1. Vérifier les images chargées

```bash
grep "images chargées" logs/signature_debug.log
```

Résultat attendu :
```
📊 RÉSUMÉ: 2 images chargées sur 2 signataires
```

### 2. Tracer un signataire spécifique

```bash
grep "Signataire 0" logs/signature_debug.log
```

### 3. Identifier les erreurs

```bash
grep "ERROR" logs/signature_debug.log
# ou
tail -f logs/errors.log
```

### 4. Suivre une session complète

```bash
grep "20251009_015830_123456" logs/signature_debug.log
```

### 5. Vérifier les images avant PyHanko

```bash
grep "AVANT sign_pdf_pages" logs/signature_debug.log
```

## 📊 Commandes utiles

### Surveiller en temps réel

```bash
# Tous les logs de signature
tail -f logs/signature_debug.log

# Seulement les erreurs
tail -f logs/errors.log

# Filtrer par niveau
tail -f logs/signature_debug.log | grep "ERROR"
```

### Analyser les performances

```bash
# Compter les sessions réussies
grep "✅ SUCCÈS" logs/signature_debug.log | wc -l

# Compter les échecs
grep "❌ ÉCHEC" logs/signature_debug.log | wc -l

# Dernières erreurs
tail -20 logs/errors.log
```

### Nettoyer les vieux logs

```bash
# Supprimer les logs de plus de 30 jours
find logs/ -name "*.log*" -mtime +30 -delete
```

Ou utiliser la fonction Python :

```python
from app.utils.debug_logger import cleanup_old_logs
cleanup_old_logs(days=30)
```

## 🐛 Scénarios de débogage

### Problème : Images de signature non visibles

1. Vérifier le chargement :
```bash
grep "Image chargée pour signataire" logs/signature_debug.log
```

2. Vérifier l'assignation :
```bash
grep "Image ASSIGNÉE à signer_stamp" logs/signature_debug.log
```

3. Vérifier avant PyHanko :
```bash
grep "AVANT sign_pdf_pages" logs/signature_debug.log
```

4. Vérifier dans la fonction :
```bash
grep "🎯 sign_pdf_pages appelée" logs/signature_debug.log
```

### Problème : Erreur lors de la signature

1. Consulter le traceback complet :
```bash
tail -50 logs/errors.log
```

2. Identifier l'étape qui échoue :
```bash
grep "ERROR" logs/signature_debug.log | tail -10
```

### Problème : Volume de signatures

```bash
grep "Volumes validés" logs/signature_debug.log
grep "Décompte de" logs/signature_debug.log
```

## 📈 Monitoring

### Statistiques quotidiennes

```bash
# Nombre de requêtes aujourd'hui
grep "$(date +%Y-%m-%d)" logs/api_requests.log | wc -l

# Nombre de documents signés aujourd'hui
grep "$(date +%Y-%m-%d)" logs/signature_debug.log | grep "documents signés avec succès" | wc -l

# Taux d'erreur
TOTAL=$(grep "NOUVELLE SESSION" logs/signature_debug.log | wc -l)
ERRORS=$(grep "❌ ÉCHEC" logs/signature_debug.log | wc -l)
echo "Taux d'erreur: $(($ERRORS * 100 / $TOTAL))%"
```

## 🔒 Sécurité

- Les logs ne contiennent **pas** de mots de passe ou clés API
- Les emails et noms d'utilisateurs sont loggés pour le débogage
- Les logs sont en **UTF-8** pour supporter tous les caractères
- Rotation automatique pour éviter les fichiers trop volumineux

## 📝 Notes

- Les logs sont créés automatiquement au premier appel
- Le dossier `logs/` doit être writable par l'application
- En production, configurer un système de monitoring (ex: ELK, Grafana)
- Sauvegarder régulièrement les logs importants
