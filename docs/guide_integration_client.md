# Guide d'intégration API DKB Sign V3 - Documentation Client

## 🔑 Accès et authentification

### Génération de clé API
1. **Endpoint de génération** : `POST /auth/generate-app-key`
2. **Authentification requise** : Token JWT (connexion utilisateur standard)
3. **Réponse** : Clé API de 64 caractères à conserver précieusement

```bash
# Exemple de génération de clé API
curl -X POST "https://dkbsignv3.com/apiDkbSignV3/auth/generate-app-key" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"
```

### Serveur de test
- **URL de test** : `https://staging.dkbsignv3.com/apiDkbSignV3`
- **URL de production** : `https://dkbsignv3.com/apiDkbSignV3`
- **Authentification** : Même système de clé API sur les deux environnements

## 📋 Documentation complète des paramètres

### Endpoint principal : `POST /v3/sign-upload-multiple`

#### Paramètres d'entrée obligatoires

##### `documents[]` (multipart/form-data)
- **Type** : Fichiers PDF
- **Limite** : Maximum 100 documents par requête
- **Format** : `documents[]=@fichier1.pdf`

##### `signers_data` (JSON string)
- **Données minimales obligatoires** :
  - `name` : Nom de famille du signataire
  - `firstname` : Prénom du signataire
  - `function` : Fonction/titre du signataire
- **Données optionnelles** :
  - `email` : Email (améliore la traçabilité)
  - `phone` : Téléphone (améliore la traçabilité)

```json
[
  {
    "name": "Dupont",
    "firstname": "Jean", 
    "function": "Directeur Général",
    "email": "jean.dupont@example.com",
    "phone": "+33123456789"
  }
]
```

##### `signature_params` (JSON string)
Structure détaillée des paramètres de positionnement :

```json
[
  {
    "document_index": 0,        // Index du document (0-based)
    "signer_index": 0,         // Index du signataire (0-based)
    "pages": [
      {
        "page": 0,             // Numéro de page (0-based)
        "signatures": [
          {"x": 100, "y": 200}, // Position en pixels
          {"x": 300, "y": 200}  // Plusieurs signatures possibles
        ]
      }
    ],
    "stamp_pages": [0, 1],     // Pages pour paraphes (optionnel)
    "qrcodes": [               // QR codes (optionnel)
      {
        "page": 0,
        "x": 50, "y": 50,
        "data": "Signé par Jean Dupont"
      }
    ],
    "signature_size": {        // Taille personnalisée (optionnel)
      "width": 150,
      "height": 50
    }
  }
]
```

#### Paramètres d'entrée optionnels

##### `signature_image_X` (multipart/form-data)
- **Format** : `signature_image_0`, `signature_image_1`, etc.
- **Cas d'usage** : Signataires externes avec leur propre image de signature
- **Si absent** : 
  1. Utilise l'image par défaut de l'utilisateur authentifié
  2. Si aucune image par défaut : crée automatiquement une image avec le nom du signataire
- **Formats acceptés** : PNG, JPG, JPEG, GIF

## ❓ Réponses aux questions spécifiques

### Concernant les entrées

#### `signature_image_X` - Signataires externes
- **Cas d'usage** : Quand vous avez des signataires qui ne sont pas dans votre base de données mais qui ont leur propre image de signature
- **Comportement si absent** :
  1. **Première option** : Utilise l'image de signature par défaut de l'utilisateur qui fait la requête
  2. **Deuxième option** : Si pas d'image par défaut, crée automatiquement une image rectangulaire avec le nom du signataire
  3. **Jamais d'échec** : Il y aura toujours une image de signature appliquée

#### `signers_data` - Données minimales
**Obligatoires (validation stricte)** :
- `name` : Nom de famille
- `firstname` : Prénom  
- `function` : Fonction/titre

**Optionnelles (recommandées)** :
- `email` : Améliore la traçabilité juridique
- `phone` : Améliore la traçabilité juridique

#### `signature_params` - Logique détaillée

##### Index et liaisons
- **`document_index`** : Lie le paramètre au document correspondant (0 = premier document uploadé)
- **`signer_index`** : Lie le paramètre au signataire correspondant (0 = premier signataire dans `signers_data`)

##### Signatures multiples par page
**Oui, c'est possible** : Le tableau `signatures` permet plusieurs positions sur une même page
```json
"signatures": [
  {"x": 100, "y": 200},  // Première signature
  {"x": 300, "y": 200},  // Deuxième signature sur la même page
  {"x": 150, "y": 400}   // Troisième signature sur la même page
]
```

##### Ciblage de la dernière page
**Non supporté** : Pas de support pour `-1`. Vous devez connaître le nombre de pages et utiliser l'index réel (ex: page 4 pour un document de 5 pages)

##### `stamp_pages` (paraphes)
- **Définition** : Pages où appliquer des paraphes/cachets (différent des signatures)
- **Usage** : Marquer des pages sans signature complète
- **Format** : `[0, 2, 4]` pour parapher les pages 1, 3 et 5

##### QR codes
- **Un QR code par objet** : Chaque objet dans le tableau `qrcodes` génère un QR code
- **Pas lié aux signatures** : Indépendant des positions de signature
- **Données personnalisables** : Le champ `data` peut contenir n'importe quel texte

##### Coordonnées X/Y
- **Unité** : **Pixels** (pas millimètres)
- **Origine** : Coin supérieur gauche (0,0)
- **Valeurs typiques pour A4** :
  - Largeur : 0-595 pixels (72 DPI)
  - Hauteur : 0-842 pixels (72 DPI)
- **Valeurs 300+** : Normales pour :
  - Documents haute résolution (150+ DPI)
  - Formats plus grands que A4
  - Documents scannés

### Concernant les retours

#### Structure de réponse de succès
```json
{
  "message": "2 document(s) signé(s) avec succès avec signataires externes.",
  "signed_documents": [
    {
      "document_name": "document1.pdf",
      "signed_pdf_url": "https://dkbsignv3.com/apiDkbSignV3/v3/documents/doc_signed/users/user_uuid/signed_document_uuid.pdf",
      "signers": [
        {
          "name": "Dupont",
          "firstname": "Jean",
          "function": "Directeur Général"
        }
      ]
    }
  ],
  "total_signatures": 2  // Nombre de DOCUMENTS signés (facturation)
}
```

#### Explication du comptage
- **`total_signatures`** = Nombre de **documents** traités (pas le nombre de signatures individuelles)
- **Logique de facturation** : 1 document = 1 signature comptabilisée, peu importe le nombre de signataires
- **Exemple** : 2 documents avec 3 signataires chacun = 2 signatures comptabilisées

#### Structure des erreurs
Toutes les erreurs suivent le même format :
```json
{
  "error": "Message d'erreur exploitable"
}
```

**Messages exploitables pour l'utilisateur** :
- `"Champ 'name' manquant pour le signataire 0."` → Indiquer à l'utilisateur de remplir le nom
- `"Nombre maximum de documents dépassé. Limite: 100 documents par requête."` → Diviser en plusieurs requêtes
- `"Format JSON invalide pour signers_data."` → Vérifier la syntaxe JSON
- `"Volume de signatures insuffisant."` → Contacter l'administrateur pour recharger le compte

### Récupération des documents signés

#### URL de téléchargement
- **Format** : `https://dkbsignv3.com/apiDkbSignV3/v3/documents/doc_signed/users/[user_uuid]/[filename_uuid].pdf`
- **Exemple** : `https://dkbsignv3.com/apiDkbSignV3/v3/documents/doc_signed/users/123e4567-e89b-12d3-a456-426614174000/signed_doc_987fcdeb-51a2-4567-8901-234567890abc.pdf`

#### Protection et sécurité
- **Authentification** : **AUCUNE authentification requise** pour le téléchargement
- **Protection par obscurité** : 
  - UUID utilisateur unique (impossible à deviner)
  - UUID document unique (impossible à deviner)
  - Pas d'énumération possible
- **Sécurité** : L'URL complète agit comme un "token" d'accès

#### Format de réponse
- **Content-Type** : `application/pdf`
- **Format** : Fichier PDF binaire
- **Paramètres** : Aucun paramètre supplémentaire requis
- **Méthode** : GET simple

#### Durée de rétention
- **Durée** : **Indéfinie** - Les documents sont conservés en permanence
- **Expiration** : Les URLs ne expirent **jamais** automatiquement
- **Suppression** : Possible uniquement via :
  - Interface d'administration DKB Sign
  - API de gestion des documents (si disponible)
- **Recommandation** : Stockez les URLs de manière sécurisée côté client

## 🧪 Exemples de test complets

### Test avec image personnalisée
```bash
curl -X POST "https://staging.dkbsignv3.com/apiDkbSignV3/v3/sign-upload-multiple" \
  -H "X-API-Key: your_app_key" \
  -F "documents[]=@contrat.pdf" \
  -F "signature_image_0=@signature_directeur.png" \
  -F 'signers_data=[{"name":"Dupont","firstname":"Jean","function":"Directeur Général","email":"jean.dupont@entreprise.com"}]' \
  -F 'signature_params=[{"document_index":0,"signer_index":0,"pages":[{"page":0,"signatures":[{"x":100,"y":200}]}],"signature_size":{"width":150,"height":50}}]'
```

### Test sans image (image par défaut)
```bash
curl -X POST "https://staging.dkbsignv3.com/apiDkbSignV3/v3/sign-upload-multiple" \
  -H "X-API-Key: your_app_key" \
  -F "documents[]=@contrat.pdf" \
  -F 'signers_data=[{"name":"Martin","firstname":"Marie","function":"Responsable RH"}]' \
  -F 'signature_params=[{"document_index":0,"signer_index":0,"pages":[{"page":0,"signatures":[{"x":300,"y":400}]}]}]'
```

### Test avec QR codes et paraphes
```bash
curl -X POST "https://staging.dkbsignv3.com/apiDkbSignV3/v3/sign-upload-multiple" \
  -H "X-API-Key: your_app_key" \
  -F "documents[]=@contrat.pdf" \
  -F 'signers_data=[{"name":"Durand","firstname":"Pierre","function":"Directeur Technique"}]' \
  -F 'signature_params=[{"document_index":0,"signer_index":0,"pages":[{"page":0,"signatures":[{"x":100,"y":200}]}],"stamp_pages":[1,2],"qrcodes":[{"page":0,"x":50,"y":50,"data":"Signé par Pierre Durand le 22/09/2025"}]}]'
```

## 🔍 Codes de statut et gestion d'erreurs

### Codes de succès
- **200** : Documents signés avec succès

### Codes d'erreur
- **400** : Erreur client (paramètres invalides, limite dépassée, JSON malformé)
- **401** : Clé API manquante ou invalide
- **403** : Volume de signatures insuffisant ou permissions insuffisantes
- **404** : Endpoint inexistant
- **500** : Erreur serveur interne

### Gestion recommandée des erreurs
```python
response = requests.post(url, headers=headers, files=files, data=data)

if response.status_code == 200:
    result = response.json()
    print(f"Succès: {result['message']}")
    for doc in result['signed_documents']:
        print(f"Document signé: {doc['signed_pdf_url']}")
        
elif response.status_code == 400:
    error = response.json()
    print(f"Erreur de paramètres: {error['error']}")
    # Afficher le message à l'utilisateur pour correction
    
elif response.status_code == 401:
    print("Clé API invalide - vérifier l'authentification")
    
elif response.status_code == 403:
    print("Volume de signatures insuffisant - contacter l'administrateur")
    
else:
    print(f"Erreur inattendue: {response.status_code}")
```

## 📞 Support et contact

Pour toute question technique ou problème d'intégration :
- **Documentation** : Ce guide et le fichier OpenAPI fourni
- **Logs** : Vérifier les logs de votre application pour les messages détaillés
- **Tests** : Utiliser l'environnement de staging pour vos tests
- **Contact** : Support technique DKB Solutions
