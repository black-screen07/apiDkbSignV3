# API de Gestion des Signatures Publiques Externes

## Vue d'ensemble

Cette API permet de gérer les images de signature pour les signataires externes. Les signatures sont stockées dans des dossiers organisés par email, permettant une réutilisation automatique lors de la signature de documents.

**Base URL:** `/v3`

**Authentification:** ⚠️ **Routes publiques sans authentification** - Ces endpoints sont accessibles sans clé API pour faciliter le stockage des signatures externes

---

## Endpoints

### 1. Upload d'une signature externe

**Endpoint:** `POST /v3/external-signatures/upload`

**Description:** Upload une image de signature pour un signataire externe identifié par son email.

**Paramètres (form-data):**
- `email` (string, obligatoire) : Email du signataire externe
- `signature_image` (file, obligatoire) : Fichier image de signature
- `overwrite` (boolean, optionnel) : Écraser l'image existante (défaut: false)

**Extensions autorisées:** png, jpg, jpeg, gif, bmp, webp

**Réponse succès (200):**
```json
{
  "success": true,
  "message": "Signature uploadée avec succès pour john.doe@example.com.",
  "email": "john.doe@example.com",
  "signature_path": "signatures/external_public/john_doe_at_example_com/signature.png",
  "overwritten": false
}
```

**Erreurs possibles:**
- `400` : Email manquant, format email invalide, fichier manquant, extension non autorisée
- `409` : Signature déjà existante (utiliser `overwrite=true`)
- `500` : Erreur serveur

**Exemple cURL:**
```bash
curl -X POST https://api.dkbsign.com/v3/external-signatures/upload \
  -F "email=john.doe@example.com" \
  -F "signature_image=@/path/to/signature.png" \
  -F "overwrite=false"
```

**Exemple Python:**
```python
import requests

url = "https://api.dkbsign.com/v3/external-signatures/upload"
files = {"signature_image": open("signature.png", "rb")}
data = {
    "email": "john.doe@example.com",
    "overwrite": "false"
}

response = requests.post(url, files=files, data=data)
print(response.json())
```

---

### 2. Récupération d'une signature externe

**Endpoint:** `GET /v3/external-signatures/get/<email>`

**Description:** Récupère l'image de signature pour un signataire externe.

**Paramètres URL:**
- `email` (string) : Email du signataire externe

**Réponse succès (200):**
Retourne le fichier image directement avec le mimetype approprié.

**Erreurs possibles:**
- `400` : Email invalide
- `404` : Aucune signature trouvée pour cet email
- `500` : Erreur serveur

**Exemple cURL:**
```bash
curl -X GET https://api.dkbsign.com/v3/external-signatures/get/john.doe@example.com \
  --output signature.png
```

**Exemple Python:**
```python
import requests

url = "https://api.dkbsign.com/v3/external-signatures/get/john.doe@example.com"

response = requests.get(url)
if response.status_code == 200:
    with open("signature.png", "wb") as f:
        f.write(response.content)
```

---

### 3. Vérification d'existence d'une signature

**Endpoint:** `GET /v3/external-signatures/check/<email>`

**Description:** Vérifie si une signature existe pour un signataire externe sans télécharger le fichier.

**Paramètres URL:**
- `email` (string) : Email du signataire externe

**Réponse succès (200):**
```json
{
  "exists": true,
  "email": "john.doe@example.com",
  "signature_path": "signatures/external_public/john_doe_at_example_com/signature.png"
}
```

**Si la signature n'existe pas:**
```json
{
  "exists": false,
  "email": "john.doe@example.com"
}
```

**Exemple cURL:**
```bash
curl -X GET https://api.dkbsign.com/v3/external-signatures/check/john.doe@example.com
```

---

### 4. Suppression d'une signature externe

**Endpoint:** `DELETE /v3/external-signatures/delete/<email>`

**Description:** Supprime l'image de signature pour un signataire externe.

**Paramètres URL:**
- `email` (string) : Email du signataire externe

**Réponse succès (200):**
```json
{
  "success": true,
  "message": "Signature supprimée avec succès pour john.doe@example.com."
}
```

**Erreurs possibles:**
- `400` : Email invalide
- `404` : Aucune signature trouvée pour cet email
- `500` : Erreur serveur

**Exemple cURL:**
```bash
curl -X DELETE https://api.dkbsign.com/v3/external-signatures/delete/john.doe@example.com
```

---

### 5. Liste de toutes les signatures externes

**Endpoint:** `GET /v3/external-signatures/list`

**Description:** Liste toutes les signatures externes stockées dans le système.

**Réponse succès (200):**
```json
{
  "signatures": [
    {
      "email": "john.doe@example.com",
      "signature_path": "signatures/external_public/john_doe_at_example_com/signature.png",
      "file_size": 15234,
      "extension": "png"
    },
    {
      "email": "jane.smith@example.com",
      "signature_path": "signatures/external_public/jane_smith_at_example_com/signature.jpg",
      "file_size": 23456,
      "extension": "jpg"
    }
  ],
  "total": 2
}
```

**Exemple cURL:**
```bash
curl -X GET https://api.dkbsign.com/v3/external-signatures/list
```

---

## Utilisation avec /v3/sign-upload-multiple

### Scénario 1 : Upload d'image à chaque signature (comportement actuel)

```json
{
  "signers_data": [
    {
      "name": "Doe",
      "firstname": "John",
      "function": "Directeur",
      "email": "john.doe@example.com"
    }
  ]
}
```

Avec fichier `signature_image_0` dans la requête multipart.

---

### Scénario 2 : Utilisation d'une signature stockée (NOUVEAU)

**Étape 1 : Stocker la signature une fois (sans authentification)**
```bash
curl -X POST https://api.dkbsign.com/v3/external-signatures/upload \
  -F "email=john.doe@example.com" \
  -F "signature_image=@john_signature.png"
```

**Étape 2 : Utiliser la signature stockée lors de la signature**
```json
{
  "signers_data": [
    {
      "name": "Doe",
      "firstname": "John",
      "function": "Directeur",
      "email": "john.doe@example.com",
      "use_stored_signature": true
    }
  ]
}
```

**Avantages:**
- ✅ Pas besoin d'uploader l'image à chaque signature
- ✅ Réduction de la taille des requêtes
- ✅ Cohérence des signatures pour un même signataire
- ✅ Gestion centralisée des signatures

---

## Ordre de priorité pour le chargement des signatures

Lors de l'appel à `/v3/sign-upload-multiple`, l'API cherche les images de signature dans cet ordre :

1. **Signature stockée** (si `use_stored_signature: true` et `email` fourni)
   - Cherche dans `signatures/external_public/<email_sanitized>/signature.*`

2. **Upload par index** (si `signature_image_0`, `signature_image_1`, etc. dans la requête)
   - Fichiers uploadés avec la requête

3. **Upload par nom de fichier** (fallback)
   - Recherche par correspondance de nom de fichier

4. **Image par défaut de l'utilisateur** (si aucune image trouvée)
   - Utilise l'image de signature de l'utilisateur authentifié

5. **Image générée automatiquement** (dernier recours)
   - Crée une image simple avec le nom du signataire

---

## Bonnes pratiques

### Gestion des signatures

1. **Stocker les signatures fréquemment utilisées**
   ```bash
   # Pour chaque signataire récurrent
   curl -X POST /v3/external-signatures/upload \
     -F "email=signer@company.com" \
     -F "signature_image=@signature.png"
   ```

2. **Vérifier l'existence avant d'uploader**
   ```bash
   # Éviter les doublons
   curl -X GET /v3/external-signatures/check/signer@company.com
   ```

3. **Mettre à jour les signatures obsolètes**
   ```bash
   # Utiliser overwrite=true
   curl -X POST /v3/external-signatures/upload \
     -F "email=signer@company.com" \
     -F "signature_image=@new_signature.png" \
     -F "overwrite=true"
   ```

### Format des images

- **Formats recommandés:** PNG (avec transparence), JPG
- **Résolution:** 150-300 DPI pour une bonne qualité
- **Dimensions:** 400x150 pixels recommandé
- **Taille fichier:** < 500 KB recommandé
- **Fond:** Transparent (PNG) ou blanc pour meilleure intégration

### Sécurité

- ✅ Toujours utiliser HTTPS
- ✅ Valider les emails avant upload
- ✅ Limiter les tailles de fichiers
- ✅ Nettoyer régulièrement les signatures non utilisées
- ⚠️ **Note:** Ces routes sont publiques sans authentification pour faciliter l'intégration. Assurez-vous de mettre en place des mesures de sécurité au niveau du serveur (rate limiting, firewall, etc.)

---

## Codes d'erreur

| Code | Description |
|------|-------------|
| 200  | Succès |
| 400  | Requête invalide (paramètres manquants ou invalides) |
| 404  | Signature non trouvée |
| 409  | Conflit (signature déjà existante) |
| 500  | Erreur serveur |

---

## Limites

- **Taille maximale de fichier:** Définie par la configuration du serveur
- **Extensions autorisées:** png, jpg, jpeg, gif, bmp, webp
- **Nombre de signatures:** Illimité (limité par l'espace disque)
- **Authentification:** Aucune - Routes publiques pour faciliter l'intégration

---

## Support

Pour toute question ou problème, contactez le support technique DKB Sign.

**Documentation mise à jour:** Décembre 2024
