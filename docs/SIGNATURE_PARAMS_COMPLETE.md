# 📋 Guide complet des paramètres de signature

## 🎯 Vue d'ensemble

Ce document regroupe **toutes les options disponibles** pour `signature_params` dans l'API `/v3/sign-upload-multiple`.

## 📝 Structure complète

```json
[
  {
    "document_index": 0,              // OBLIGATOIRE - Index du document
    "signer_index": 0,                // OBLIGATOIRE - Index du signataire
    
    // === OPTIONS DE POSITIONNEMENT ===
    "pages": [                        // OBLIGATOIRE (sauf si sign_on_last_page)
      {
        "page": 0,                    // Numéro de page (0 = première)
        "signatures": [               // Au moins 1 signature
          {
            "x": 100,                 // Position X en mm
            "y": 200                  // Position Y en mm
          }
        ]
      }
    ],
    
    // === NOUVELLE OPTION: DERNIÈRE PAGE ===
    "sign_on_last_page": true,        // OPTIONNEL - Signe sur dernière page
    "custom_x": 100,                  // OPTIONNEL - Position X personnalisée
    
    // === AFFICHAGE DES INFORMATIONS ===
    "show_signer_info": true,         // OPTIONNEL - Affiche nom/fonction/email
    
    // === TAILLE DE LA SIGNATURE ===
    "signature_size": {               // OPTIONNEL
      "width": 180,                   // Largeur en pixels
      "height": 60                    // Hauteur en pixels
    },
    
    // === QR CODES ===
    "qrcodes": [                      // OPTIONNEL
      {
        "page": 0,                    // Page du QR code
        "x": 450,                     // Position X en mm
        "y": 50,                      // Position Y en mm
        "size": 30,                   // Taille en mm
        "data": "URL ou texte",       // Données du QR code
        "fill_color": "blue",         // Couleur (défaut: blue)
        "back_color": "white"         // Fond (défaut: white)
      }
    ],
    
    // === CACHETS ===
    "stamp_pages": [0, 1, 2]          // OPTIONNEL - Pages pour le cachet
  }
]
```

## 🎨 Exemples par cas d'usage

### 1️⃣ Cas simple : 1 signataire, 1 page

```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "pages": [
      {
        "page": 0,
        "signatures": [{"x": 100, "y": 200}]
      }
    ]
  }
]
```

### 2️⃣ Avec affichage des informations

```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "pages": [
      {
        "page": 0,
        "signatures": [{"x": 100, "y": 200}]
      }
    ],
    "show_signer_info": true,
    "signature_size": {"width": 180, "height": 60}
  }
]
```

### 3️⃣ Signature sur dernière page (NOUVEAU)

```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "sign_on_last_page": true,
    "show_signer_info": true
  }
]
```

### 4️⃣ Trois signataires sur dernière page

```json
[
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
]
```

### 5️⃣ Signatures côte à côte sur dernière page

```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "sign_on_last_page": true,
    "custom_x": 50,
    "show_signer_info": true
  },
  {
    "document_index": 0,
    "signer_index": 1,
    "sign_on_last_page": true,
    "custom_x": 250,
    "show_signer_info": true
  },
  {
    "document_index": 0,
    "signer_index": 2,
    "sign_on_last_page": true,
    "custom_x": 450,
    "show_signer_info": true
  }
]
```

### 6️⃣ Avec QR codes et cachets

```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "pages": [
      {
        "page": 0,
        "signatures": [{"x": 100, "y": 200}]
      }
    ],
    "show_signer_info": true,
    "qrcodes": [
      {
        "page": 0,
        "x": 450,
        "y": 50,
        "size": 30,
        "data": "https://verify.dkbsign.com/doc/12345"
      }
    ],
    "stamp_pages": [0, 1]
  }
]
```

### 7️⃣ Signatures multiples sur plusieurs pages

```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "pages": [
      {
        "page": 0,
        "signatures": [
          {"x": 100, "y": 200},
          {"x": 400, "y": 200}
        ]
      },
      {
        "page": 2,
        "signatures": [{"x": 100, "y": 150}]
      }
    ],
    "show_signer_info": true
  }
]
```

## 📊 Tableau récapitulatif des paramètres

| Paramètre | Type | Obligatoire | Défaut | Description |
|-----------|------|-------------|--------|-------------|
| `document_index` | number | ✅ Oui | - | Index du document (0, 1, 2...) |
| `signer_index` | number | ✅ Oui | - | Index du signataire (0, 1, 2...) |
| `pages` | array | ⚠️ Conditionnel | - | Pages et positions (obligatoire sauf si `sign_on_last_page`) |
| `sign_on_last_page` | boolean | ❌ Non | `false` | Place toutes les signatures sur la dernière page |
| `custom_x` | number | ❌ Non | `100` | Position X personnalisée (avec `sign_on_last_page`) |
| `show_signer_info` | boolean | ❌ Non | `false` | Affiche nom/fonction/email sous la signature |
| `signature_size` | object | ❌ Non | `{width:150, height:50}` | Taille de la signature en pixels |
| `qrcodes` | array | ❌ Non | `[]` | QR codes à ajouter |
| `stamp_pages` | array | ❌ Non | `[]` | Pages où appliquer le cachet |

## 🎯 Scénarios recommandés

### Scénario A : Document simple avec validation

**Besoin** : 1 document, 3 signataires, tous sur la dernière page avec leurs infos

**Solution** :
```json
[
  {"document_index":0,"signer_index":0,"sign_on_last_page":true,"show_signer_info":true},
  {"document_index":0,"signer_index":1,"sign_on_last_page":true,"show_signer_info":true},
  {"document_index":0,"signer_index":2,"sign_on_last_page":true,"show_signer_info":true}
]
```

### Scénario B : Contrat avec paraphe

**Besoin** : Paraphe sur chaque page, signature finale sur dernière page

**Solution** :
```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "pages": [
      {"page": 0, "signatures": [{"x": 500, "y": 20}]},
      {"page": 1, "signatures": [{"x": 500, "y": 20}]},
      {"page": 2, "signatures": [{"x": 500, "y": 20}]}
    ],
    "signature_size": {"width": 50, "height": 30}
  },
  {
    "document_index": 0,
    "signer_index": 0,
    "sign_on_last_page": true,
    "show_signer_info": true,
    "signature_size": {"width": 180, "height": 60}
  }
]
```

### Scénario C : Document avec QR code de vérification

**Besoin** : Signatures sur dernière page + QR code de vérification

**Solution** :
```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "sign_on_last_page": true,
    "show_signer_info": true,
    "qrcodes": [
      {
        "page": 0,
        "x": 450,
        "y": 50,
        "size": 30,
        "data": "https://verify.dkbsign.com/doc/12345"
      }
    ]
  }
]
```

## 🔗 Liens vers la documentation détaillée

- **Affichage des infos signataire** : `/docs/SIGNER_INFO_DISPLAY.md`
- **Signature sur dernière page** : `/docs/SIGN_ON_LAST_PAGE.md`
- **API complète** : `/docs/api_signature_upload_multiple.md`

## 💡 Bonnes pratiques

1. **Utilisez `sign_on_last_page`** pour les documents de longueur variable
2. **Activez `show_signer_info`** pour une meilleure traçabilité
3. **Personnalisez `signature_size`** selon vos besoins visuels
4. **Ajoutez des QR codes** pour la vérification en ligne
5. **Testez avec différents nombres de pages** pour valider le comportement

## 🧪 Template de test Postman

```json
{
  "documents": ["contrat.pdf"],
  "signature_image_0": "signature1.png",
  "signature_image_1": "signature2.png",
  "signature_image_2": "signature3.png",
  "signers_data": [
    {"name":"Dupont","firstname":"Jean","function":"Directeur Général","email":"jean@example.com"},
    {"name":"Martin","firstname":"Marie","function":"Directrice Financière","email":"marie@example.com"},
    {"name":"Dubois","firstname":"Paul","function":"Directeur Juridique","email":"paul@example.com"}
  ],
  "signature_params": [
    {"document_index":0,"signer_index":0,"sign_on_last_page":true,"show_signer_info":true,"signature_size":{"width":180,"height":60}},
    {"document_index":0,"signer_index":1,"sign_on_last_page":true,"show_signer_info":true,"signature_size":{"width":180,"height":60}},
    {"document_index":0,"signer_index":2,"sign_on_last_page":true,"show_signer_info":true,"signature_size":{"width":180,"height":60}}
  ]
}
```

---

**Dernière mise à jour** : 2025-10-09  
**Version API** : v3
