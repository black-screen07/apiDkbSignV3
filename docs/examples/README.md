# Exemples d'utilisation de l'API DKB Sign

Ce dossier contient des exemples pratiques d'utilisation de l'API DKB Sign V3.

## Fichiers disponibles

### `external_signatures_example.py`

Script Python complet démontrant l'utilisation de l'API de gestion des signatures publiques externes.

**Fonctionnalités démontrées :**
- Upload de signatures pour signataires externes
- Vérification d'existence de signatures
- Téléchargement de signatures stockées
- Suppression de signatures
- Listage de toutes les signatures
- Signature de documents avec signatures stockées
- Mélange de signatures stockées et uploadées
- Mise à jour de signatures existantes
- Workflow complet de gestion

**Prérequis :**
```bash
pip install requests
```

**Configuration :**
1. Ouvrir le fichier `external_signatures_example.py`
2. Remplacer `API_KEY = "votre_cle_api_ici"` par votre clé API
3. Ajuster les chemins des fichiers selon votre structure
4. Décommenter l'exemple que vous voulez exécuter

**Exécution :**
```bash
python external_signatures_example.py
```

## Exemples disponibles

### Exemple 1 : Upload de signatures
Upload de signatures pour plusieurs signataires externes.

### Exemple 2 : Vérification et listage
Vérification de l'existence de signatures et listage complet.

### Exemple 3 : Signature avec signatures stockées
Signature de documents en utilisant uniquement des signatures pré-stockées.

### Exemple 4 : Signatures mixtes
Mélange de signatures stockées et signatures uploadées avec la requête.

### Exemple 5 : Mise à jour de signature
Mise à jour d'une signature existante avec backup de l'ancienne.

### Exemple 6 : Nettoyage
Suppression de signatures non utilisées.

### Workflow complet
Workflow complet : Setup → Sign → Cleanup

## Documentation complète

Pour la documentation complète de l'API, consultez :
- `/docs/api_external_signatures.md` - Documentation des endpoints de signatures externes
- `/docs/api_signature_upload_multiple.md` - Documentation de la route de signature multiple

## Support

Pour toute question ou problème, contactez le support technique DKB Sign.
