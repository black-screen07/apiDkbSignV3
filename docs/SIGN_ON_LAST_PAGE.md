# 📄 Signature automatique sur la dernière page

## 🎯 Fonctionnalité

Cette option permet de placer **automatiquement toutes les signatures sur la dernière page** du document, quel que soit le nombre de pages du PDF.

## ✨ Avantages

- ✅ **Automatique** : Détecte automatiquement la dernière page
- ✅ **Flexible** : Fonctionne avec n'importe quel nombre de pages
- ✅ **Intelligent** : Calcule automatiquement les positions pour éviter les chevauchements
- ✅ **Simple** : Un seul paramètre à activer

## 🔧 Utilisation

### Paramètre à ajouter

Ajoutez `"sign_on_last_page": true` dans **chaque** objet de `signature_params` où vous voulez cette fonctionnalité :

```json
{
  "document_index": 0,
  "signer_index": 0,
  "sign_on_last_page": true,  // ← Active la signature sur dernière page
  "pages": []  // ← OPTIONNEL - Peut contenir des positions personnalisées
}
```

**Important** : 
- ✅ L'option est **par signataire**, pas globale
- ✅ Vous pouvez mélanger signataires avec et sans `sign_on_last_page`
- ✅ Les positions X/Y dans `pages` sont **respectées** si fournies

## 📐 Positionnement automatique

### Positions par défaut

Le système calcule automatiquement les positions verticales :

- **Signataire 1** : `y = 250` (haut de la page)
- **Signataire 2** : `y = 150` (milieu)
- **Signataire 3** : `y = 50` (bas)
- **Espacement** : 100 points entre chaque signature

### Positions personnalisées

Vous avez **3 façons** de personnaliser les positions :

#### Option 1 : Positions complètes dans `pages`

```json
{
  "document_index": 0,
  "signer_index": 0,
  "sign_on_last_page": true,
  "pages": [
    {
      "page": 0,  // ← Ignoré, remplacé par la dernière page
      "signatures": [
        {
          "x": 150,  // ← Position X personnalisée
          "y": 200   // ← Position Y personnalisée
        }
      ]
    }
  ]
}
```

#### Option 2 : Seulement `custom_x` (Y automatique)

```json
{
  "document_index": 0,
  "signer_index": 0,
  "sign_on_last_page": true,
  "custom_x": 200  // ← Position X personnalisée, Y calculé automatiquement
}
```

#### Option 3 : Tout automatique

```json
{
  "document_index": 0,
  "signer_index": 0,
  "sign_on_last_page": true  // ← X et Y calculés automatiquement
}
```

## 📝 Exemples

### Exemple 1 : Simple (1 signataire)

**signature_params :**
```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "sign_on_last_page": true
  }
]
```

**Résultat** : Signature placée sur la dernière page à la position (100, 250)

---

### Exemple 2 : 3 signataires sur dernière page

**signers_data :**
```json
[
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
]
```

**signature_params :**
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

**Résultat** :
- Toutes les signatures sur la dernière page
- Jean : position (100, 250)
- Marie : position (100, 150)
- Paul : position (100, 50)

---

### Exemple 3 : Positions personnalisées complètes

**signature_params :**
```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "sign_on_last_page": true,
    "pages": [
      {
        "page": 0,
        "signatures": [{"x": 50, "y": 220}]
      }
    ],
    "show_signer_info": true
  },
  {
    "document_index": 0,
    "signer_index": 1,
    "sign_on_last_page": true,
    "pages": [
      {
        "page": 0,
        "signatures": [{"x": 250, "y": 220}]
      }
    ],
    "show_signer_info": true
  },
  {
    "document_index": 0,
    "signer_index": 2,
    "sign_on_last_page": true,
    "pages": [
      {
        "page": 0,
        "signatures": [{"x": 450, "y": 220}]
      }
    ],
    "show_signer_info": true
  }
]
```

**Résultat** : 3 signatures côte à côte sur la dernière page à la même hauteur (y=220)

---

### Exemple 4 : Mélanger signataires (NOUVEAU)

**Cas d'usage** : Certains signataires sur des pages spécifiques, d'autres sur la dernière page

**signature_params :**
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

**Résultat** :
- Signataire 0 : Page 0 (position spécifiée)
- Signataire 1 : Dernière page (position automatique y=250)
- Signataire 2 : Dernière page (position automatique y=150)

---

### Exemple 5 : Combinaison avec autres options

**signature_params :**
```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "sign_on_last_page": true,
    "show_signer_info": true,
    "signature_size": {"width": 200, "height": 80},
    "custom_x": 100
  },
  {
    "document_index": 0,
    "signer_index": 1,
    "sign_on_last_page": true,
    "show_signer_info": true,
    "signature_size": {"width": 200, "height": 80},
    "custom_x": 100
  }
]
```

**Résultat** :
- Signatures sur dernière page
- Avec informations du signataire affichées
- Taille personnalisée 200x80

---

## 🎨 Disposition visuelle

### PDF de 5 pages avec 3 signataires

```
Page 1: [Contenu du document]
Page 2: [Contenu du document]
Page 3: [Contenu du document]
Page 4: [Contenu du document]
Page 5: [Signature Jean - y:250]
        [Signature Marie - y:150]
        [Signature Paul - y:50]
```

### Avec show_signer_info activé

```
Page 5 (dernière):
┌──────────────────────┐
│  [Signature Jean]    │  ← y: 250
└──────────────────────┘
Jean Dupont
Directeur Général
jean.dupont@example.com

┌──────────────────────┐
│  [Signature Marie]   │  ← y: 150
└──────────────────────┘
Marie Martin
Directrice Financière
marie.martin@example.com

┌──────────────────────┐
│  [Signature Paul]    │  ← y: 50
└──────────────────────┘
Paul Dubois
Directeur Juridique
paul.dubois@example.com
```

---

## 🔄 Comparaison : Avec vs Sans

### ❌ Sans sign_on_last_page (méthode manuelle)

```json
{
  "document_index": 0,
  "signer_index": 0,
  "pages": [
    {
      "page": 4,  // ← Vous devez connaître le numéro de la dernière page
      "signatures": [{"x": 100, "y": 250}]
    }
  ]
}
```

**Problèmes** :
- Vous devez connaître le nombre de pages à l'avance
- Si le document change, les signatures peuvent être mal placées
- Répétitif pour plusieurs signataires

### ✅ Avec sign_on_last_page (automatique)

```json
{
  "document_index": 0,
  "signer_index": 0,
  "sign_on_last_page": true
}
```

**Avantages** :
- Fonctionne avec n'importe quel nombre de pages
- Positions calculées automatiquement
- Simple et concis

---

## ⚙️ Configuration avancée

### Paramètres disponibles

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `sign_on_last_page` | boolean | `false` | Active la signature sur dernière page |
| `custom_x` | number | `100` | Position X personnalisée (en mm) |
| `show_signer_info` | boolean | `false` | Affiche les infos sous la signature |
| `signature_size` | object | `{width:150, height:50}` | Taille de la signature |

### Calcul automatique des positions

```python
# Position Y pour chaque signataire
base_y = 250
spacing = 100
y_position = base_y - (index * spacing)

# Signataire 0: y = 250 - (0 * 100) = 250
# Signataire 1: y = 250 - (1 * 100) = 150
# Signataire 2: y = 250 - (2 * 100) = 50
```

---

## 🧪 Test avec Postman

### Configuration complète

**Form-data :**

| Key | Type | Value |
|-----|------|-------|
| `documents` | File | contrat.pdf (n'importe quel nombre de pages) |
| `signature_image_0` | File | signature_jean.png |
| `signature_image_1` | File | signature_marie.png |
| `signature_image_2` | File | signature_paul.png |
| `signers_data` | Text | (JSON ci-dessous) |
| `signature_params` | Text | (JSON ci-dessous) |

**signers_data :**
```json
[
  {"name":"Dupont","firstname":"Jean","function":"Directeur Général","email":"jean.dupont@example.com"},
  {"name":"Martin","firstname":"Marie","function":"Directrice Financière","email":"marie.martin@example.com"},
  {"name":"Dubois","firstname":"Paul","function":"Directeur Juridique","email":"paul.dubois@example.com"}
]
```

**signature_params (version simple) :**
```json
[
  {"document_index":0,"signer_index":0,"sign_on_last_page":true,"show_signer_info":true},
  {"document_index":0,"signer_index":1,"sign_on_last_page":true,"show_signer_info":true},
  {"document_index":0,"signer_index":2,"sign_on_last_page":true,"show_signer_info":true}
]
```

**signature_params (version complète) :**
```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "sign_on_last_page": true,
    "show_signer_info": true,
    "signature_size": {"width": 180, "height": 60},
    "custom_x": 100
  },
  {
    "document_index": 0,
    "signer_index": 1,
    "sign_on_last_page": true,
    "show_signer_info": true,
    "signature_size": {"width": 180, "height": 60},
    "custom_x": 100
  },
  {
    "document_index": 0,
    "signer_index": 2,
    "sign_on_last_page": true,
    "show_signer_info": true,
    "signature_size": {"width": 180, "height": 60},
    "custom_x": 100
  }
]
```

---

## 📊 Logs de débogage

Consultez les logs pour voir le traitement :

```bash
tail -f logs/signature_debug.log
```

Vous verrez :
```
Document 0: 5 page(s), dernière page: 4
📄 Option 'sign_on_last_page' activée - Toutes les signatures seront sur la page 4
  - Signataire 0: position (x=100, y=250)
  - Signataire 1: position (x=100, y=150)
  - Signataire 2: position (x=100, y=50)
```

---

## ⚠️ Notes importantes

1. **Détection automatique** : Le système détecte automatiquement le nombre de pages du PDF
2. **Espacement** : 100 points entre chaque signature (ajustable dans le code)
3. **Maximum de signataires** : Environ 3-4 signataires par page (selon la taille)
4. **Compatibilité** : Fonctionne avec toutes les autres options (`show_signer_info`, `signature_size`, etc.)
5. **Pages ignorées** : Quand `sign_on_last_page: true`, le champ `pages` est complètement ignoré

---

## 🐛 Dépannage

### Les signatures ne sont pas sur la dernière page

- ✅ Vérifiez que `"sign_on_last_page": true` est bien dans `signature_params`
- ✅ Consultez les logs : `grep "sign_on_last_page" logs/signature_debug.log`

### Les signatures se chevauchent

- ✅ Réduisez le nombre de signataires par page (max 3-4)
- ✅ Utilisez `custom_x` pour les placer côte à côte au lieu de verticalement

### Le document a trop de signataires

- ✅ Utilisez `custom_x` pour créer plusieurs colonnes
- ✅ Exemple : Signataires 0-2 à `x=50`, signataires 3-5 à `x=300`

---

## 📚 Ressources

- Documentation complète : `/docs/api_signature_upload_multiple.md`
- Affichage infos signataire : `/docs/SIGNER_INFO_DISPLAY.md`
- Logs : `logs/signature_debug.log`

---

**Version** : 1.0  
**Date** : 2025-10-09  
**Feature** : Signature automatique sur dernière page
