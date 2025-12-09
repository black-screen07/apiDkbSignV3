# 📋 Système de Logging pour Débogage en Production

## 🎯 Objectif

Système de logging complet et structuré pour déboguer les problèmes de signature en production, notamment les problèmes d'images de signature qui ne s'appliquent pas correctement.

## 📁 Fichiers créés

### 1. Module de logging (`app/utils/debug_logger.py`)

Module principal qui fournit :
- **3 loggers spécialisés** : signatures, API, erreurs
- **Rotation automatique** des fichiers (10 MB max, 5 versions)
- **Fonctions utilitaires** pour logger facilement
- **Format détaillé** avec timestamp, niveau, fonction, ligne

### 2. Fichiers de logs (`logs/`)

- `signature_debug.log` : Processus de signature détaillé
- `api_requests.log` : Requêtes API
- `errors.log` : Erreurs critiques avec traceback

### 3. Documentation

- `logs/README.md` : Guide complet d'utilisation des logs
- `logs/.gitignore` : Ignore les fichiers de logs dans Git
- `test_logging.py` : Script de test du système
- `LOGGING_SETUP.md` : Ce fichier

## 🚀 Installation

### 1. Tester le système de logging

```bash
python test_logging.py
```

Résultat attendu :
```
✅ TOUS LES TESTS RÉUSSIS!
Fichiers de logs créés dans: /path/to/logs
```

### 2. Vérifier les fichiers créés

```bash
ls -lh logs/
```

Vous devriez voir :
```
signature_debug.log
api_requests.log
errors.log
README.md
.gitignore
```

## 📊 Utilisation en production

### Surveiller les logs en temps réel

```bash
# Tous les logs de signature
tail -f logs/signature_debug.log

# Seulement les erreurs
tail -f logs/errors.log

# Filtrer par signataire
tail -f logs/signature_debug.log | grep "Signataire 0"
```

### Déboguer un problème d'image

```bash
# 1. Vérifier le chargement des images
grep "images chargées" logs/signature_debug.log

# 2. Tracer un signataire spécifique
grep "Signataire 0" logs/signature_debug.log

# 3. Vérifier avant PyHanko
grep "AVANT sign_pdf_pages" logs/signature_debug.log

# 4. Voir les erreurs
grep "ERROR" logs/signature_debug.log
```

### Analyser une session complète

Chaque requête crée une session avec un ID unique :

```bash
# Trouver les sessions
grep "NOUVELLE SESSION" logs/signature_debug.log

# Suivre une session spécifique
grep "20251009_015830_123456" logs/signature_debug.log
```

## 🔍 Fonctionnalités de logging

### 1. Sessions de log

Chaque requête `/v3/sign-upload-multiple` est tracée dans une session :

```
================================================================================
NOUVELLE SESSION: 20251009_015830_123456
================================================================================
[2025-10-09 01:58:30] INFO Utilisateur authentifié: user@example.com
[2025-10-09 01:58:30] INFO Fichiers uploadés: 2 document(s)
[2025-10-09 01:58:30] INFO Signataires: 2 signataire(s) externes
...
✅ SUCCÈS - Session 20251009_015830_123456: 2 documents signés avec succès
================================================================================
```

### 2. Logs d'images détaillés

Chaque image est tracée avec ses propriétés :

```
[Signataire 0] Chargée via clé 'signature_image_0' - signature.png
Image: {'type': "<class 'PIL.Image.Image'>", 'size': (150, 50), 'mode': 'RGB'}

[Signataire 0] Image trouvée dans dictionnaire
Image: {'type': "<class 'PIL.Image.Image'>", 'size': (150, 50), 'mode': 'RGB'}

[Signataire 0] Image ASSIGNÉE à signer_stamp
Image: {'type': "<class 'PIL.Image.Image'>", 'size': (150, 50), 'mode': 'RGB'}

[Signataire 0] AVANT sign_pdf_pages
Image: {'type': "<class 'PIL.Image.Image'>", 'size': (150, 50), 'mode': 'RGB'}
```

### 3. Logs d'erreurs avec traceback

Toutes les erreurs sont loggées avec le contexte complet :

```
[2025-10-09 01:58:30] ERROR Utilisation image signataire 0 - Error: cannot identify image file
Traceback:
  File "signature_routes.py", line 410, in sign_upload_multiple_documents
    sig_image_pil = Image.open(sig_file.stream)
  ...
```

## 🛠️ Intégration dans le code

### Fonctions disponibles

```python
from app.utils.debug_logger import (
    signature_logger,           # Logger principal
    log_signature_process,      # Logger une étape
    log_image_info,            # Logger une image PIL
    log_api_request,           # Logger une requête API
    log_error,                 # Logger une erreur
    create_session_log,        # Créer une session
    close_session_log          # Fermer une session
)
```

### Exemples d'utilisation

```python
# Créer une session
session_id = create_session_log()

# Logger une requête API
log_api_request("/v3/sign-upload-multiple", "POST", user.email)

# Logger une étape
log_signature_process(0, "Chargement de l'image", {"filename": "sig.png"})

# Logger une image PIL
log_image_info(0, pil_image, "Après chargement")

# Logger une erreur
try:
    # code...
except Exception as e:
    log_error(e, "Contexte", traceback.format_exc())

# Fermer la session
close_session_log(session_id, success=True, message="Succès")
```

## 📈 Monitoring et statistiques

### Statistiques quotidiennes

```bash
# Nombre de requêtes
grep "$(date +%Y-%m-%d)" logs/api_requests.log | wc -l

# Nombre de documents signés
grep "documents signés avec succès" logs/signature_debug.log | wc -l

# Taux d'erreur
TOTAL=$(grep "NOUVELLE SESSION" logs/signature_debug.log | wc -l)
ERRORS=$(grep "❌ ÉCHEC" logs/signature_debug.log | wc -l)
echo "Taux d'erreur: $(($ERRORS * 100 / $TOTAL))%"
```

### Nettoyage automatique

```python
from app.utils.debug_logger import cleanup_old_logs

# Supprimer les logs de plus de 30 jours
cleanup_old_logs(days=30)
```

Ou en ligne de commande :

```bash
find logs/ -name "*.log*" -mtime +30 -delete
```

## 🐛 Scénarios de débogage

### Problème : Images non visibles dans le PDF

**Étapes de débogage :**

1. **Vérifier le chargement initial**
```bash
grep "📊 RÉSUMÉ" logs/signature_debug.log
```
Attendu : `📊 RÉSUMÉ: 2 images chargées sur 2 signataires`

2. **Vérifier l'assignation pour chaque signataire**
```bash
grep "Image ASSIGNÉE" logs/signature_debug.log
```
Attendu : Une ligne par signataire

3. **Vérifier avant l'appel à PyHanko**
```bash
grep "AVANT sign_pdf_pages" logs/signature_debug.log
```
Attendu : Image valide avec taille et mode

4. **Vérifier dans la fonction sign_pdf_pages**
```bash
grep "🎯 sign_pdf_pages appelée" logs/signature_debug.log
```
Attendu : Image reçue correctement

5. **Chercher les erreurs**
```bash
grep "ERROR" logs/signature_debug.log
tail -20 logs/errors.log
```

### Problème : Première image OK, deuxième KO

**Analyse :**

```bash
# Comparer les logs des deux signataires
grep "Signataire 0" logs/signature_debug.log > sig0.log
grep "Signataire 1" logs/signature_debug.log > sig1.log
diff sig0.log sig1.log
```

Chercher les différences dans :
- Le chargement de l'image
- L'assignation à `signer_stamp`
- Les appels à `sign_pdf_pages`

## 🔒 Sécurité et bonnes pratiques

### ✅ Ce qui est loggé

- Emails des utilisateurs (pour le débogage)
- Noms de fichiers
- Tailles et propriétés des images
- Étapes du processus
- Erreurs avec traceback

### ❌ Ce qui N'est PAS loggé

- Mots de passe
- Clés API complètes
- Contenu des documents
- Données sensibles

### Bonnes pratiques

1. **Rotation automatique** : Les fichiers sont limités à 10 MB
2. **Nettoyage régulier** : Supprimer les logs de plus de 30 jours
3. **Monitoring** : Surveiller le taux d'erreur quotidiennement
4. **Backup** : Sauvegarder les logs importants avant nettoyage

## 📝 Maintenance

### Vérifier l'espace disque

```bash
du -sh logs/
```

### Compresser les vieux logs

```bash
gzip logs/*.log.1 logs/*.log.2 logs/*.log.3
```

### Archiver les logs

```bash
tar -czf logs_backup_$(date +%Y%m%d).tar.gz logs/*.log*
```

## 🎓 Formation de l'équipe

### Pour les développeurs

- Lire `logs/README.md` pour comprendre le système
- Exécuter `python test_logging.py` pour tester
- Utiliser `tail -f` pour surveiller en temps réel

### Pour les ops

- Configurer un système de monitoring (ELK, Grafana)
- Mettre en place des alertes sur les erreurs
- Automatiser le nettoyage des vieux logs

## 🆘 Support

En cas de problème avec le système de logging :

1. Vérifier les permissions du dossier `logs/`
2. Vérifier l'espace disque disponible
3. Tester avec `python test_logging.py`
4. Consulter les logs d'erreur de l'application

## 📚 Ressources

- Documentation Python logging : https://docs.python.org/3/library/logging.html
- RotatingFileHandler : https://docs.python.org/3/library/logging.handlers.html
- PIL/Pillow : https://pillow.readthedocs.io/

---

**Version** : 1.0  
**Date** : 2025-10-09  
**Auteur** : Système de logging DkbSign V3
