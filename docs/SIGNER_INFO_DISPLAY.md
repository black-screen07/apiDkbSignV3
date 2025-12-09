# 📝 Affichage des informations du signataire sous la signature

## 🎯 Fonctionnalité

Cette option permet d'afficher automatiquement les informations du signataire (nom, prénom, fonction, email) **juste en dessous** de l'image de signature dans le PDF.

## ✨ Avantages

- ✅ **Identification claire** : Chaque signature est accompagnée des informations du signataire
- ✅ **Professionnel** : Rendu propre et formaté
- ✅ **Traçabilité** : Facilite l'identification des signataires
- ✅ **Optionnel** : Activable/désactivable par signature

## 📋 Utilisation

### Paramètre à ajouter dans `signature_params`

Ajoutez simplement `"show_signer_info": true` dans chaque objet de signature :

```json
{
  "document_index": 0,
  "signer_index": 0,
  "pages": [...],
  "show_signer_info": true  // ← Nouvelle option
}
```

## 🎨 Rendu visuel

Avec `show_signer_info: true`, le PDF affichera :

```
┌─────────────────────┐
│                     │
│  [Image signature]  │
│                     │
└─────────────────────┘
Jean Dupont
Directeur Général
jean.dupont@example.com
```

Sans l'option (par défaut) :

```
┌─────────────────────┐
│                     │
│  [Image signature]  │
│                     │
└─────────────────────┘
```

## 📝 Exemples complets

### Exemple 1 : 1 signataire avec infos affichées

**signers_data :**
```json
[
  {
    "name": "Dupont",
    "firstname": "Jean",
    "function": "Directeur Général",
    "email": "jean.dupont@example.com"
  }
]
```

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
  }
]
```

### Exemple 2 : 3 signataires, seulement 2 avec infos

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
    "pages": [{"page": 0, "signatures": [{"x": 50, "y": 200}]}],
    "show_signer_info": true,
    "signature_size": {"width": 150, "height": 50}
  },
  {
    "document_index": 0,
    "signer_index": 1,
    "pages": [{"page": 0, "signatures": [{"x": 220, "y": 200}]}],
    "show_signer_info": false,
    "signature_size": {"width": 150, "height": 50}
  },
  {
    "document_index": 0,
    "signer_index": 2,
    "pages": [{"page": 0, "signatures": [{"x": 390, "y": 200}]}],
    "show_signer_info": true,
    "signature_size": {"width": 150, "height": 50}
  }
]
```

**Résultat :** Jean et Paul auront leurs infos affichées, mais pas Marie.

### Exemple 3 : Tous les signataires avec infos (recommandé)

**signature_params :**
```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "pages": [{"page": 0, "signatures": [{"x": 100, "y": 250}]}],
    "show_signer_info": true,
    "signature_size": {"width": 180, "height": 60}
  },
  {
    "document_index": 0,
    "signer_index": 1,
    "pages": [{"page": 0, "signatures": [{"x": 100, "y": 150}]}],
    "show_signer_info": true,
    "signature_size": {"width": 180, "height": 60}
  },
  {
    "document_index": 0,
    "signer_index": 2,
    "pages": [{"page": 0, "signatures": [{"x": 100, "y": 50}]}],
    "show_signer_info": true,
    "signature_size": {"width": 180, "height": 60}
  }
]
```

## 📐 Recommandations de positionnement

### Pour éviter les chevauchements

Quand `show_signer_info: true`, prévoyez **environ 40-50 points d'espace supplémentaire** sous chaque signature pour le texte (3 lignes).

**Disposition verticale recommandée :**
```json
// Signataire 1 (haut)
{"x": 100, "y": 250}  // Signature à 250

// Signataire 2 (milieu)  
{"x": 100, "y": 150}  // Signature à 150 (100 points d'écart)

// Signataire 3 (bas)
{"x": 100, "y": 50}   // Signature à 50 (100 points d'écart)
```

**Disposition horizontale :**
```json
// Signataires côte à côte
{"x": 50, "y": 100}   // Signataire 1
{"x": 220, "y": 100}  // Signataire 2  
{"x": 390, "y": 100}  // Signataire 3
```

## 🎨 Format du texte

Le texte affiché suit ce format :

```
[Prénom] [Nom]
[Fonction]
[Email]
```

**Caractéristiques :**
- Police : Helvetica
- Taille : 8pt
- Couleur : Gris foncé (RGB: 0.2, 0.2, 0.2)
- Espacement : 10 points entre chaque ligne
- Position : 5 points sous l'image de signature

## 🔧 Personnalisation

### Champs affichés

Le système affiche automatiquement les champs disponibles dans `signers_data` :

| Champ | Affiché si présent |
|-------|-------------------|
| `firstname` + `name` | ✅ Ligne 1 |
| `function` | ✅ Ligne 2 |
| `email` | ✅ Ligne 3 |
| `phone` | ❌ Non affiché (peut être ajouté si besoin) |

### Si un champ est manquant

Le système saute simplement la ligne. Exemple :

**Avec tous les champs :**
```
Jean Dupont
Directeur Général
jean.dupont@example.com
```

**Sans fonction :**
```
Jean Dupont
jean.dupont@example.com
```

**Sans email :**
```
Jean Dupont
Directeur Général
```

## 🧪 Test avec Postman

### Configuration complète

**Form-data :**

| Key | Type | Value |
|-----|------|-------|
| `documents` | File | contrat.pdf |
| `signature_image_0` | File | signature_jean.png |
| `signature_image_1` | File | signature_marie.png |
| `signers_data` | Text | (JSON ci-dessous) |
| `signature_params` | Text | (JSON ci-dessous) |

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
  }
]
```

**signature_params :**
```json
[
  {
    "document_index": 0,
    "signer_index": 0,
    "pages": [{"page": 0, "signatures": [{"x": 100, "y": 200}]}],
    "show_signer_info": true,
    "signature_size": {"width": 180, "height": 60}
  },
  {
    "document_index": 0,
    "signer_index": 1,
    "pages": [{"page": 0, "signatures": [{"x": 100, "y": 100}]}],
    "show_signer_info": true,
    "signature_size": {"width": 180, "height": 60}
  }
]
```

## ⚠️ Notes importantes

1. **Espace requis** : Assurez-vous d'avoir au moins 40-50 points d'espace sous chaque signature
2. **Valeur par défaut** : Si `show_signer_info` n'est pas spécifié, la valeur par défaut est `false`
3. **Performance** : L'ajout du texte est rapide et n'impacte pas significativement les performances
4. **Compatibilité** : Le texte est ajouté au PDF de manière standard et visible dans tous les lecteurs PDF

## 🐛 Dépannage

### Le texte ne s'affiche pas

- ✅ Vérifiez que `show_signer_info: true` est bien dans `signature_params`
- ✅ Vérifiez que les champs `name`, `firstname`, `function`, `email` sont dans `signers_data`
- ✅ Consultez les logs : `tail -f logs/signature_debug.log`

### Le texte est coupé

- ✅ Augmentez la valeur `y` de la signature pour laisser plus d'espace en bas
- ✅ Réduisez le nombre de signataires par page

### Le texte chevauche la signature suivante

- ✅ Augmentez l'espacement vertical entre les signatures (minimum 100 points)

## 📚 Ressources

- Documentation API : `/docs/api_signature_upload_multiple.md`
- Exemples JSON : Ce fichier
- Logs de débogage : `logs/signature_debug.log`

---

**Version** : 1.0  
**Date** : 2025-10-09  
**Feature** : Affichage des informations du signataire
