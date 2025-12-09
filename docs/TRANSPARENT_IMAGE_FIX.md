# 🖼️ Correction : Transparence des images de signature

## 🐛 Problèmes identifiés

### Problème 1 : Fond noir (RÉSOLU ❌ puis ANNULÉ)

Les images de signature avec transparence (PNG avec canal alpha) affichaient un **fond noir** au lieu d'être transparentes.

**Cause** : Conversion directe `convert('RGB')` remplaçait la transparence par du noir.

### Problème 2 : Fond blanc cache le texte (PROBLÈME ACTUEL)

La première solution (fond blanc) cachait le texte du document PDF en dessous de la signature.

**Cause** : Le fond blanc opaque + `background_opacity=0.7` rendait le texte illisible.

## ✅ Solution finale : Garder RGBA pour transparence totale

### Pourquoi RGBA ?

PyHanko **supporte nativement les images RGBA** via `PdfImage`. Le paramètre `background_opacity=0.7` contrôle l'opacité de l'image entière, pas du fond.

**Avantage** : La transparence de l'image PNG est **préservée**, le texte du PDF reste visible sous la signature.

### Modes d'image concernés

| Mode | Description | Problème |
|------|-------------|----------|
| **RGBA** | RGB + canal Alpha (transparence) | ❌ Fond noir |
| **LA** | Niveaux de gris + Alpha | ❌ Fond noir |
| **P** | Palette avec transparence possible | ❌ Fond noir (si palette transparente) |
| **RGB** | RGB sans transparence | ✅ Pas de problème |
| **L** | Niveaux de gris | ✅ Pas de problème |

## ✅ Solution finale implémentée

### Nouvelle logique : Tout convertir en RGBA

```python
# ✅ CODE FINAL - Préserve la transparence
if img.mode == 'P':
    # Convertir les images avec palette en RGBA
    img = img.convert('RGBA')
elif img.mode in ('L', 'LA'):
    # Convertir niveaux de gris en RGBA
    img = img.convert('RGBA')
elif img.mode == 'RGB':
    # Ajouter un canal alpha aux images RGB (opaque)
    img = img.convert('RGBA')
# Si déjà RGBA, ne rien faire
```

### Explication technique

1. **Toutes les images → RGBA** : Format uniforme avec canal alpha
2. **Transparence préservée** : Les pixels transparents restent transparents
3. **PyHanko gère la transparence** : `PdfImage(img_rgba)` supporte RGBA nativement
4. **background_opacity=0.7** : Contrôle l'opacité globale de l'image
5. **Résultat** : Signature transparente, texte du PDF visible en dessous

### Avantages de cette approche

- ✅ **Transparence totale** : Le texte du PDF reste visible
- ✅ **Pas de fond noir** : Les pixels transparents restent transparents
- ✅ **Pas de fond blanc** : Pas de cache opaque
- ✅ **Compatible PyHanko** : PdfImage supporte RGBA
- ✅ **Qualité préservée** : Pas de perte de détails
- ✅ **Opacité contrôlable** : Via `background_opacity`

## 🔧 Fichiers modifiés

### 1. `/app/routes/publicapi/signature_routes.py`

**Lignes 323-334** : Chargement des images uploadées (méthode 1)
```python
# Convertir en RGBA pour garder la transparence (PyHanko supporte RGBA)
# Ne PAS convertir en RGB car ça cache le texte du PDF en dessous
if sig_image_pil.mode == 'P':
    sig_image_pil = sig_image_pil.convert('RGBA')
elif sig_image_pil.mode in ('L', 'LA'):
    sig_image_pil = sig_image_pil.convert('RGBA')
elif sig_image_pil.mode == 'RGB':
    sig_image_pil = sig_image_pil.convert('RGBA')
# Si déjà RGBA, ne rien faire
```

**Lignes 352-363** : Chargement des images uploadées (méthode 2 - fallback)
- Même logique appliquée pour préserver la transparence

### 2. `/app/utils/public_signature_utils.py`

**Fonction `load_signature_image()`** (lignes 238-270)
```python
def load_signature_image(user):
    """
    Charge l'image de signature en fonction de 'current_img_sign'.
    Convertit en RGBA pour préserver la transparence (PyHanko supporte RGBA).
    """
    # ... chargement de l'image ...
    
    # Convertir en RGBA pour garder la transparence
    if img.mode == 'P':
        img = img.convert('RGBA')
    elif img.mode in ('L', 'LA'):
        img = img.convert('RGBA')
    elif img.mode == 'RGB':
        img = img.convert('RGBA')
    # Si déjà RGBA, ne rien faire
    
    return img
```

### 3. `/app/utils/signature_utils.py`

**Fonction `load_signature_image()`** (lignes 238-270)
- Même correction pour les routes internes (non-API)
- Conversion systématique en RGBA pour préserver la transparence

## 🧪 Tests de vérification

### Test 1 : Image PNG avec transparence sur texte

**Problème initial (RGB)** :
```
Image RGBA → convert('RGB') → Fond NOIR ❌
Texte du PDF caché par le fond noir
```

**Solution intermédiaire (RGB + fond blanc)** :
```
Image RGBA → Fond blanc + composition → Fond BLANC ❌
Texte du PDF caché par le fond blanc opaque
```

**Solution finale (RGBA)** :
```
Image RGBA → Reste RGBA → PdfImage(RGBA) ✅
Texte du PDF VISIBLE à travers la transparence
```

### Test 2 : Image PNG avec palette

**Avant** :
```
Image P → convert('RGB') → Fond NOIR ❌
```

**Après** :
```
Image P → convert('RGBA') → Transparence préservée ✅
```

### Test 3 : Image RGB normale

**Après** :
```
Image RGB → convert('RGBA') avec alpha opaque → OK ✅
```

## 📊 Comparaison visuelle

### Problème 1 : Fond noir (convert RGB)

```
┌─────────────────────┐
│  [Signature]        │
│  ████████████       │  ← Fond noir cache le texte
│  ████████████       │
└─────────────────────┘
Texte du PDF: ████████  ← Invisible
```

### Problème 2 : Fond blanc opaque

```
┌─────────────────────┐
│  [Signature]        │
│  ░░░░░░░░░░░░       │  ← Fond blanc cache le texte
│  ░░░░░░░░░░░░       │
└─────────────────────┘
Texte du PDF: ░░░░░░░░  ← Illisible
```

### Solution finale : RGBA transparent

```
┌─────────────────────┐
│  [Signature]        │
│                     │  ← Transparent
│                     │
└─────────────────────┘
Texte du PDF: Contrat  ← VISIBLE ✅
```

## 🎯 Impact

### Routes affectées

- ✅ `/v3/sign-upload-multiple` : Images uploadées par les signataires externes
- ✅ `/v3/sign-pdf` : Image par défaut de l'utilisateur
- ✅ `/v3/sign-pdfs` : Image par défaut de l'utilisateur
- ✅ Toutes les routes de signature utilisant `load_signature_image()`

### Types d'images supportés

- ✅ PNG avec transparence (RGBA) → **Transparence préservée**
- ✅ PNG avec palette transparente (P) → **Converti en RGBA**
- ✅ Images en niveaux de gris avec alpha (LA) → **Converti en RGBA**
- ✅ Images RGB → **Converti en RGBA opaque**
- ✅ Tous les formats supportés par PIL/Pillow

## 💡 Bonnes pratiques

### Pour les utilisateurs de l'API

1. **Format recommandé** : PNG avec transparence (RGBA)
2. **Fond** : Peut être transparent, la transparence sera **préservée**
3. **Qualité** : Aucune perte de qualité lors de la conversion
4. **Taille** : Utiliser `signature_size` pour contrôler les dimensions
5. **Opacité** : Contrôlée par PyHanko via `background_opacity=0.7`

### Pour les développeurs

1. **Toujours convertir en RGBA** : Format uniforme pour PyHanko
2. **Ne PAS convertir en RGB** : Ça détruit la transparence
3. **Laisser PyHanko gérer** : PdfImage supporte RGBA nativement
4. **Tester sur texte** : Vérifier que le texte du PDF reste visible

## 🔄 Migration

### Images existantes

Les images déjà stockées en RGB avec fond noir/blanc ne nécessitent **PAS** de migration.

**Pourquoi ?** La conversion se fait **à la volée** lors du chargement de l'image, pas lors du stockage.

### Comportement

1. **Images stockées** : Restent dans leur format original (PNG, RGBA, RGB, etc.)
2. **Chargement** : Conversion automatique en RGBA lors de `load_signature_image()`
3. **Utilisation** : PyHanko reçoit toujours une image RGBA avec transparence préservée

### Pas de script nécessaire

Aucun script de migration n'est nécessaire car :
- ✅ La conversion est faite à la volée
- ✅ Les fichiers originaux ne sont pas modifiés
- ✅ Toutes les images bénéficient automatiquement de la correction

## 📚 Ressources techniques

### Documentation PIL/Pillow

- [Image Modes](https://pillow.readthedocs.io/en/stable/handbook/concepts.html#modes)
- [Image.convert()](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.convert)
- [Image.paste()](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.paste)

### Modes d'image PIL

- **RGB** : 3 canaux (Rouge, Vert, Bleu)
- **RGBA** : 4 canaux (RGB + Alpha pour transparence)
- **L** : 1 canal (Niveaux de gris)
- **LA** : 2 canaux (Gris + Alpha)
- **P** : Palette de couleurs (peut inclure transparence)

### Documentation PyHanko

- [PdfImage](https://pyhanko.readthedocs.io/) : Support natif des images RGBA
- [StaticStampStyle](https://pyhanko.readthedocs.io/) : Paramètre `background_opacity`

## ✅ Résultat final

Après cette correction :

- ✅ **Transparence totale préservée** : Le texte du PDF reste visible
- ✅ **Pas de fond noir** : Les pixels transparents restent transparents
- ✅ **Pas de fond blanc opaque** : Pas de cache sur le texte
- ✅ **Compatibilité PyHanko** : PdfImage supporte RGBA nativement
- ✅ **Compatibilité totale** avec tous les formats PNG
- ✅ **Pas de régression** sur les images existantes
- ✅ **Qualité préservée** lors de la conversion
- ✅ **Opacité contrôlable** via `background_opacity=0.7`

## 🎬 Résumé de l'évolution

### Problème 1 : Fond noir
```python
convert('RGB')  # ❌ Transparence → Noir
```

### Tentative 1 : Fond blanc
```python
background = Image.new('RGB', size, (255, 255, 255))
background.paste(img, mask=alpha)  # ❌ Cache le texte
```

### Solution finale : RGBA
```python
img.convert('RGBA')  # ✅ Transparence préservée
PdfImage(img_rgba)   # ✅ PyHanko gère la transparence
```

---

**Date de correction** : 2025-10-09  
**Version** : 2.4 (finale)  
**Priorité** : 🔴 HAUTE (Lisibilité des documents)  
**Impact** : Toutes les routes de signature
