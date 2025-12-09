# API Signature Upload Multiple - Documentation Complète

## Endpoint: `POST /v3/sign-upload-multiple`

Cette route permet de signer un ou plusieurs documents PDF uploadés avec des signataires externes (qui ne sont pas dans la base de données de l'api).

### Vue d'ensemble
- **URL**: `/v3/sign-upload-multiple`
- **Méthode**: POST
- **Type de contenu**: `multipart/form-data`
- **Authentification**: X-API-Key requise

### Limites de sécurité
- **Maximum de documents**: 100 documents par requête
- **Raison**: Limite de sécurité pour éviter les problèmes de performance, timeout HTTP, et surcharge mémoire
- **Alternative**: Pour traiter plus de 100 documents, divisez en plusieurs requêtes

### Authentification
- **Méthode**: Clé API
- **Headers acceptés**: 
  - `X-API-Key: votre_cle_app`
  - `Authorization: Bearer votre_cle_api`
- **Génération**: Utilisez l'endpoint `/auth/generate-app-key` avec authentification JWT

### Paramètres d'entrée

#### Fichiers (multipart/form-data)

##### `documents[]` (OBLIGATOIRE)
- **Type**: Fichier PDF
- **Format**: Tableau de fichiers
- **Description**: Documents PDF à signer
- **Limite**: Maximum 100 fichiers par requête
- **Formats acceptés**: PDF uniquement

##### `signature_image_X` (OPTIONNEL)
- **Type**: Fichier image
- **Format**: `signature_image_0`, `signature_image_1`, `signature_image_2`, etc.
- **Description**: Images de signature personnalisées pour chaque signataire externe
- **Index**: L'index X correspond à l'index du signataire dans `signers_data`
- **Formats acceptés**: PNG, JPG, JPEG, GIF
- **Comportement si absent**: 
  - Utilise l'image de signature par défaut de l'utilisateur authentifié
  - L'image par défaut peut être redimensionnée selon `signature_size`
  - Si aucune image par défaut n'existe, la signature sera appliquée sans image

#### Données JSON (form-data)

##### `signers_data` (OBLIGATOIRE)
- **Type**: JSON String
- **Description**: Informations des signataires externes
- **Données minimales requises**:
  - `name` (string): Nom de famille du signataire
  - `firstname` (string): Prénom du signataire  
  - `function` (string): Fonction/titre du signataire
- **Données optionnelles**:
  - `email` (string): Email du signataire (pour traçabilité)
  - `phone` (string): Téléphone du signataire (pour traçabilité)
  - `signature_image` (string): Nom du fichier d'image (non utilisé actuellement)

##### `signature_params` (OBLIGATOIRE)
- **Type**: JSON String
- **Description**: Paramètres de positionnement des signatures
- **Structure**: Tableau d'objets de paramètres

### Format des données

#### Taille personnalisée des signatures

Vous pouvez maintenant spécifier une taille personnalisée pour les images de signature en ajoutant le paramètre `signature_size` dans `signature_params`. Cette fonctionnalité permet de :

- **Redimensionner les images uploadées** : Les images de signature personnalisées seront automatiquement redimensionnées selon les dimensions spécifiées
- **Redimensionner l'image par défaut** : Si aucune image personnalisée n'est fournie, l'image de signature par défaut de l'utilisateur sera redimensionnée
- **Contrôler l'apparence** : Assurer une cohérence visuelle entre toutes les signatures du document

**Format du paramètre :**
```json
"signature_size": {
    "width": 150,   // Largeur en pixels
    "height": 50    // Hauteur en pixels
}
```

**Notes importantes :**
- Les dimensions sont en pixels
- Si `signature_size` n'est pas spécifié, l'image conserve sa taille originale
- L'algorithme de redimensionnement utilisé est LANCZOS pour une qualité optimale
- Les dimensions doivent être des nombres entiers positifs

### Formats détaillés des données

#### Format `signers_data`
```json
[
    {
        "name": "Dupont",                    // OBLIGATOIRE: Nom de famille
        "firstname": "Jean",               // OBLIGATOIRE: Prénom
        "function": "Directeur Général",    // OBLIGATOIRE: Fonction/titre
        "email": "jean.dupont@example.com", // OPTIONNEL: Email (traçabilité)
        "phone": "+33123456789"             // OPTIONNEL: Téléphone (traçabilité)
    },
    {
        "name": "Martin",
        "firstname": "Marie",
        "function": "Responsable RH",
        "email": "marie.martin@example.com"
        // phone est optionnel
    }
]
```

#### Format `signature_params`
```json
[
    {
        "document_index": 0,              // OBLIGATOIRE: Index du document (0-based)
        "signer_index": 0,               // OBLIGATOIRE: Index du signataire (0-based)
        
        // === OPTIONS DE POSITIONNEMENT ===
        "pages": [                       // OBLIGATOIRE (sauf si sign_on_last_page)
            {
                "page": 0,               // Numéro de page (0-based)
                "signatures": [          // Au moins 1 signature requise
                    {"x": 100, "y": 200}, // Position en millimètres
                    {"x": 300, "y": 200}  // Plusieurs signatures possibles par page
                ]
            },
            {
                "page": 2,               // Autre page
                "signatures": [
                    {"x": 150, "y": 400}
                ]
            }
        ],
        
        // === NOUVELLE OPTION: SIGNATURE SUR DERNIÈRE PAGE ===
        "sign_on_last_page": true,       // OPTIONNEL: Place automatiquement sur la dernière page
        "custom_x": 100,                 // OPTIONNEL: Position X personnalisée (avec sign_on_last_page)
        
        // === AFFICHAGE DES INFORMATIONS DU SIGNATAIRE ===
        "show_signer_info": true,        // OPTIONNEL: Affiche nom/fonction/email sous la signature
        
        // === TAILLE DE LA SIGNATURE ===
        "signature_size": {              // OPTIONNEL: Taille personnalisée
            "width": 150,               // Largeur en pixels
            "height": 50                // Hauteur en pixels
        },
        
        // === QR CODES ET CACHETS ===
        "qrcodes": [                     // OPTIONNEL: QR codes à ajouter
            {
                "page": 0,               // Page du QR code
                "x": 50, "y": 50,        // Position en millimètres
                "size": 30,              // Taille en millimètres
                "data": "https://verify.dkbsign.com/doc/12345",
                "fill_color": "blue",    // OPTIONNEL: Couleur (défaut: blue)
                "back_color": "white"    // OPTIONNEL: Fond (défaut: white)
            }
        ],
        "stamp_pages": [0, 2]            // OPTIONNEL: Pages pour paraphes/cachets
    }
]
```

### 🆕 Nouvelles fonctionnalités

#### 1. Affichage des informations du signataire (`show_signer_info`)

**Description** : Affiche automatiquement le nom, la fonction et l'email du signataire sous l'image de signature.

**Utilisation** :
```json
{
  "document_index": 0,
  "signer_index": 0,
  "pages": [{"page": 0, "signatures": [{"x": 100, "y": 200}]}],
  "show_signer_info": true
}
```

**Rendu dans le PDF** :
```
┌──────────────────────┐
│                      │
│  [Image signature]   │
│                      │
└──────────────────────┘
Jean Dupont
Directeur Général
jean.dupont@example.com
```

**Avantages** :
- ✅ Identification claire de chaque signataire
- ✅ Traçabilité améliorée
- ✅ Conformité juridique
- ✅ Rendu professionnel

**Notes importantes** :
- Le texte est ajouté **avant** la signature pour ne pas invalider le certificat
- Police : Helvetica 8pt, couleur gris foncé
- Espacement : 10 points entre chaque ligne
- Prévoir 40-50 points d'espace sous la signature

#### 2. Signature automatique sur dernière page (`sign_on_last_page`)

**Description** : Place automatiquement toutes les signatures sur la dernière page du document, quel que soit le nombre de pages.

**Utilisation simple** :
```json
{
  "document_index": 0,
  "signer_index": 0,
  "sign_on_last_page": true
}
```

**Utilisation avec positions personnalisées** :
```json
{
  "document_index": 0,
  "signer_index": 0,
  "sign_on_last_page": true,
  "pages": [{"page": 0, "signatures": [{"x": 150, "y": 220}]}]
  // Les positions X/Y sont respectées, seule la page est changée
}
```

**Utilisation avec custom_x** :
```json
{
  "document_index": 0,
  "signer_index": 0,
  "sign_on_last_page": true,
  "custom_x": 200  // Position X personnalisée, Y calculé automatiquement
}
```

**Positionnement automatique** :
- Signataire 0 : y = 250 (haut)
- Signataire 1 : y = 150 (milieu)
- Signataire 2 : y = 50 (bas)
- Espacement : 100 points entre chaque

**Avantages** :
- ✅ Fonctionne avec n'importe quel nombre de pages
- ✅ Pas besoin de connaître le nombre de pages à l'avance
- ✅ Positions calculées automatiquement
- ✅ Option par signataire (pas globale)

**Exemple avec 3 signataires** :
```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "sign_on_last_page": true,
    "show_signer_info": true
  },
  {
    "document_index": 0,
    "signer_index": 1,
    "sign_on_last_page": true,
    "show_signer_info": true
  },
  {
    "document_index": 0,
    "signer_index": 2,
    "sign_on_last_page": true,
    "show_signer_info": true
  }
]
```

**Notes importantes** :
- Quand `sign_on_last_page: true`, le champ `pages` peut contenir des positions personnalisées
- Les positions X/Y dans `pages` sont respectées
- L'option est **par signataire**, vous pouvez mélanger signataires avec et sans cette option

#### 3. Combinaison des fonctionnalités

**Exemple complet** : 3 signataires sur dernière page avec leurs informations
```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "sign_on_last_page": true,
    "show_signer_info": true,
    "signature_size": {"width": 180, "height": 60},
    "pages": [{"page": 0, "signatures": [{"x": 50, "y": 200}]}]
  },
  {
    "document_index": 0,
    "signer_index": 1,
    "sign_on_last_page": true,
    "show_signer_info": true,
    "signature_size": {"width": 180, "height": 60},
    "pages": [{"page": 0, "signatures": [{"x": 250, "y": 200}]}]
  },
  {
    "document_index": 0,
    "signer_index": 2,
    "sign_on_last_page": true,
    "show_signer_info": true,
    "signature_size": {"width": 180, "height": 60},
    "pages": [{"page": 0, "signatures": [{"x": 450, "y": 200}]}]
  }
]
```

**Résultat** : 3 signatures côte à côte sur la dernière page, chacune avec les informations du signataire affichées en dessous.

### Questions fréquentes sur les paramètres

#### Concernant `signature_image_X`
- **Cas d'usage**: Pour les signataires externes qui ont leur propre image de signature
- **Si absent**: L'image de signature par défaut de l'utilisateur authentifié est utilisée
- **Image par défaut**: Peut être redimensionnée selon `signature_size`
- **Aucune image**: Si ni image personnalisée ni image par défaut, signature sans image

#### Concernant `signers_data` - Données minimales
- **Obligatoires**: `name`, `firstname`, `function`
- **Optionnelles**: `email`, `phone` (améliorent la traçabilité)
- **Validation**: Les 3 champs obligatoires sont vérifiés, erreur 400 si manquants

#### Concernant `signature_params` - Logique des index
- **`document_index`**: Lie le paramètre au document correspondant (0 = premier document)
- **`signer_index`**: Lie le paramètre au signataire correspondant (0 = premier signataire)
- **Plusieurs signatures par page**: Oui, le tableau `signatures` permet plusieurs positions
- **Ciblage dernière page**: Non, pas de support pour `-1`. Utilisez l'index réel
- **`stamp_pages`**: Pages pour les paraphes/cachets (différent des signatures)
- **QR codes**: Un QR code par objet dans le tableau `qrcodes`

#### Concernant les coordonnées X/Y
- **Unité**: Millimètres (pas pixels)
- **Origine**: Coin inférieur gauche (0,0) - standard PDF
- **Valeurs typiques**: 0-210 (largeur) et 0-297 (hauteur) pour A4
- **Conversion**: 1mm ≈ 2.83 points PDF

#### Concernant `show_signer_info`
- **Activation**: Ajouter `"show_signer_info": true` dans `signature_params`
- **Données affichées**: Prénom Nom, Fonction, Email (si fournis dans `signers_data`)
- **Position**: Automatiquement placé sous l'image de signature
- **Espace requis**: Prévoir 40-50 points d'espace sous la signature
- **Certificat**: Le texte est ajouté AVANT la signature pour ne pas invalider le certificat

#### Concernant `sign_on_last_page`
- **Activation**: Ajouter `"sign_on_last_page": true` dans `signature_params`
- **Comportement**: Place la signature sur la dernière page du document
- **Positions personnalisées**: Les X/Y dans `pages` sont respectés si fournis
- **Position automatique**: Si pas de `pages`, utilise des positions calculées automatiquement
- **custom_x**: Permet de personnaliser seulement la position X
- **Par signataire**: Chaque signataire peut avoir son propre comportement
```

### Exemples d'utilisation

#### Exemple 1 : Simple avec curl

```bash
curl -X POST "https://dkbsignv3.com/apiDkbSignV3/v3/sign-upload-multiple" \
  -H "X-API-Key: your_app_key" \
  -F "documents[]=@document1.pdf" \
  -F "signature_image_0=@signature_jean.png" \
  -F 'signers_data=[
    {
      "name": "Dupont",
      "firstname": "Jean",
      "function": "Directeur Général",
      "email": "jean.dupont@example.com"
    }
  ]' \
  -F 'signature_params=[
    {
      "document_index": 0,
      "signer_index": 0,
      "pages": [{"page": 0, "signatures": [{"x": 100, "y": 200}]}]
    }
  ]'
```

#### Exemple 2 : Avec nouvelles fonctionnalités

```bash
curl -X POST "https://dkbsignv3.com/apiDkbSignV3/v3/sign-upload-multiple" \
  -H "X-API-Key: your_app_key" \
  -F "documents[]=@contrat.pdf" \
  -F "signature_image_0=@signature_jean.png" \
  -F "signature_image_1=@signature_marie.png" \
  -F "signature_image_2=@signature_paul.png" \
  -F 'signers_data=[
    {
      "name": "Dupont",
      "firstname": "Jean",
      "function": "Directeur Général",
      "email": "jean.dupont@example.com"
    },
    {
      "name": "Martin",
      "firstname": "Marie",
      "function": "Directrice Financière",
      "email": "marie.martin@example.com"
    },
    {
      "name": "Dubois",
      "firstname": "Paul",
      "function": "Directeur Juridique",
      "email": "paul.dubois@example.com"
    }
  ]' \
  -F 'signature_params=[
    {
      "document_index": 0,
      "signer_index": 0,
      "sign_on_last_page": true,
      "show_signer_info": true,
      "signature_size": {"width": 180, "height": 60}
    },
    {
      "document_index": 0,
      "signer_index": 1,
      "sign_on_last_page": true,
      "show_signer_info": true,
      "signature_size": {"width": 180, "height": 60}
    },
    {
      "document_index": 0,
      "signer_index": 2,
      "sign_on_last_page": true,
      "show_signer_info": true,
      "signature_size": {"width": 180, "height": 60}
    }
  ]'
```

#### Exemple 3 : Python avec nouvelles fonctionnalités

```python
import requests
import json

url = "https://dkbsignv3.com/apiDkbSignV3/v3/sign-upload-multiple"
headers = {
    "X-API-Key": "your_app_key"
}

# Données des signataires avec email et téléphone
signers_data = [
    {
        "name": "Dupont",
        "firstname": "Jean",
        "function": "Directeur Général",
        "email": "jean.dupont@example.com",
        "phone": "+33612345678"
    },
    {
        "name": "Martin", 
        "firstname": "Marie",
        "function": "Directrice Financière",
        "email": "marie.martin@example.com",
        "phone": "+33687654321"
    },
    {
        "name": "Dubois",
        "firstname": "Paul",
        "function": "Directeur Juridique",
        "email": "paul.dubois@example.com"
    }
]

# Paramètres de signature avec nouvelles fonctionnalités
signature_params = [
    {
        "document_index": 0,
        "signer_index": 0,
        "sign_on_last_page": True,  # Signature sur dernière page
        "show_signer_info": True,   # Afficher les infos
        "signature_size": {"width": 180, "height": 60}
    },
    {
        "document_index": 0,
        "signer_index": 1,
        "sign_on_last_page": True,
        "show_signer_info": True,
        "signature_size": {"width": 180, "height": 60}
    },
    {
        "document_index": 0,
        "signer_index": 2,
        "sign_on_last_page": True,
        "show_signer_info": True,
        "signature_size": {"width": 180, "height": 60}
    }
]

# Fichiers à envoyer
files = {
    'documents': ('contrat.pdf', open('contrat.pdf', 'rb')),
    'signature_image_0': ('signature_jean.png', open('signature_jean.png', 'rb')),
    'signature_image_1': ('signature_marie.png', open('signature_marie.png', 'rb')),
    'signature_image_2': ('signature_paul.png', open('signature_paul.png', 'rb'))
}

# Données du formulaire
data = {
    'signers_data': json.dumps(signers_data),
    'signature_params': json.dumps(signature_params)
}

response = requests.post(url, headers=headers, files=files, data=data)
result = response.json()

if response.status_code == 200:
    print(f"✅ Succès: {result['message']}")
    print(f"Documents signés: {len(result['signed_documents'])}")
    for doc in result['signed_documents']:
        print(f"  - {doc['document_name']}: {doc['signed_pdf_url']}")
else:
    print(f"❌ Erreur: {result.get('error', 'Erreur inconnue')}")
```

### Réponses de l'API

#### Réponse de succès (200)
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
                },
                {
                    "name": "Martin",
                    "firstname": "Marie", 
                    "function": "Responsable RH"
                }
            ]
        },
        {
            "document_name": "document2.pdf",
            "signed_pdf_url": "https://dkbsignv3.com/apiDkbSignV3/v3/documents/doc_signed/users/user_uuid/signed_document2_uuid.pdf",
            "signers": [
                {
                    "name": "Dupont",
                    "firstname": "Jean",
                    "function": "Directeur Général"
                }
            ]
        }
    ],
    "total_signatures": 2  // Nombre de documents signés (pas de signatures individuelles)
}
```

**Explication du comptage**:
- `total_signatures` = nombre de documents traités
- Chaque document compte pour 1, peu importe le nombre de signataires
- Dans l'exemple: 2 documents = 2 signatures comptabilisées

### ⚠️ Notes importantes sur les certificats

#### Validité des certificats avec plusieurs signataires

Quand vous utilisez `show_signer_info: true` avec plusieurs signataires, l'API applique une logique en **deux passes** pour garantir que **tous les certificats restent valides** :

**Première passe** : Ajout de tous les textes d'informations
- Tous les textes de tous les signataires sont ajoutés au PDF

**Deuxième passe** : Application de toutes les signatures
- Toutes les signatures sont appliquées sur le PDF préparé

**Résultat** : Tous les certificats sont valides ✅

**Vérification** :
1. Ouvrez le PDF signé dans Adobe Reader
2. Cliquez sur chaque signature
3. Toutes doivent afficher "Signature valide"

**Documentation technique** :
- `/docs/CERTIFICATE_VALIDITY_FIX.md` : Correction pour 1 signataire
- `/docs/CERTIFICATE_VALIDITY_MULTIPLE_SIGNERS.md` : Correction pour plusieurs signataires

```

#### Réponses d'erreur

##### Erreur 400 - Paramètres invalides
```json
{
    "error": "Champ 'name' manquant pour le signataire 0."
}
```

##### Erreur 400 - Limite dépassée
```json
{
    "error": "Nombre maximum de documents dépassé. Limite: 100 documents par requête."
}
```

##### Erreur 400 - JSON invalide
```json
{
    "error": "Format JSON invalide pour signers_data."
}
```

##### Erreur 401 - Authentification
```json
{
    "error": "Clé API manquante ou invalide."
}
```

##### Erreur 403 - Volume insuffisant
```json
{
    "error": "Volume de signatures insuffisant."
}
```

##### Erreur 500 - Erreur serveur
```json
{
    "error": "Erreur lors de la signature : [détail de l'erreur]"
}
```

### Exemples de cas d'usage

**Cas 1 : Contrat simple avec 1 signataire**
```json
{
  "sign_on_last_page": true,
  "show_signer_info": true
}
```

**Cas 2 : Document avec 3 signataires sur dernière page**
```json
[
  {"signer_index": 0, "sign_on_last_page": true, "show_signer_info": true},
  {"signer_index": 1, "sign_on_last_page": true, "show_signer_info": true},
  {"signer_index": 2, "sign_on_last_page": true, "show_signer_info": true}
]
```

**Cas 3 : Paraphe sur chaque page + signature finale**
```json
[
  {
    "signer_index": 0,
    "pages": [
      {"page": 0, "signatures": [{"x": 500, "y": 20}]},
      {"page": 1, "signatures": [{"x": 500, "y": 20}]},
      {"page": 2, "signatures": [{"x": 500, "y": 20}]}
    ],
    "signature_size": {"width": 50, "height": 30}
  },
  {
    "signer_index": 0,
    "sign_on_last_page": true,
    "show_signer_info": true,
    "signature_size": {"width": 180, "height": 60}
  }
]
```

**Cas 4 : Signatures côte à côte sur dernière page**
```json
[
  {
    "signer_index": 0,
    "sign_on_last_page": true,
    "pages": [{"page": 0, "signatures": [{"x": 50, "y": 200}]}],
    "show_signer_info": true
  },
  {
    "signer_index": 1,
    "sign_on_last_page": true,
    "pages": [{"page": 0, "signatures": [{"x": 250, "y": 200}]}],
    "show_signer_info": true
  },
  {
    "signer_index": 2,
    "sign_on_last_page": true,
    "pages": [{"page": 0, "signatures": [{"x": 450, "y": 200}]}],
    "show_signer_info": true
  }
]
```

### Changelog

#### Version 2.2 - 2025-10-09
- ✅ Ajout de `show_signer_info` : Affichage des informations du signataire
- ✅ Ajout de `sign_on_last_page` : Signature automatique sur dernière page
- ✅ Ajout de `custom_x` : Position X personnalisée avec sign_on_last_page
- ✅ Correction critique : Validité des certificats avec plusieurs signataires
- ✅ Amélioration : Respect des positions X/Y avec sign_on_last_page
- ✅ Documentation : Guides complets pour chaque fonctionnalité

#### Version 2.1 - 2025-10-08
- Ajout de `signature_size` : Taille personnalisée des signatures
- Amélioration des métadonnées de signature pour Adobe Reader
- Ajout de l'email et du téléphone dans les métadonnées

#### Version 2.0 - 2025-10-07
- Support des signataires externes
- Upload d'images de signature personnalisées
- Limite de sécurité : 100 documents maximum

---

**Dernière mise à jour** : 2025-10-09  
**Version API** : v3  
**Endpoint** : `/v3/sign-upload-multiple`
