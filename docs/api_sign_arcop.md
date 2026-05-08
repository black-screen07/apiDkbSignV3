# API Signature ARCOP — Guide d'intégration rapide

## Endpoint

```
POST /v3/sign-arcop
```

## Authentification

Header `X-API-Key` avec la clé API de l'administrateur ARCOP.

```
X-API-Key: votre_cle_api
```

## Paramètres (form-data)

| Paramètre     | Type   | Obligatoire | Description                          |
|---------------|--------|-------------|--------------------------------------|
| `file`        | File   | ✅ Oui      | Le fichier PDF à signer              |
| `signer_name` | String | ✅ Oui      | Nom complet du signataire (ex: "OUATTARA Oumar") |

> **Note :** Le champ fichier accepte aussi le nom `document`. Alternativement, vous pouvez passer `file_url` (string) avec l'URL du PDF au lieu d'uploader le fichier.

## Ce que l'API fait automatiquement

- Appose le **cachet/signature** de l'entreprise (image PNG depuis le serveur)
- Génère et place un **QR code** de vérification en bas à gauche
- Ajoute la **mention verticale ARTCI** sur le bord droit de chaque page
- Applique la **signature numérique** (certificat électronique) au document
- Décompte **1 signature** du volume de l'entreprise

## Réponse succès (200)

```json
{
    "message": "Document ARCOP signé avec succès.",
    "doc_signed": "https://api.example.com/v3/documents/doc_signed/ARCOP/abc123.pdf",
    "signer_name": "OUATTARA Oumar",
    "pages": 1
}
```

## Réponse erreur (400 / 500)

```json
{
    "error": "Le paramètre 'signer_name' est obligatoire."
}
```

## Exemples d'intégration

### cURL

```bash
curl -X POST https://votre-api.com/v3/sign-arcop \
  -H "X-API-Key: votre_cle_api" \
  -F "file=@quitus.pdf" \
  -F "signer_name=OUATTARA Oumar"
```

### Python (requests)

```python
import requests

url = "https://votre-api.com/v3/sign-arcop"
headers = {"X-API-Key": "votre_cle_api"}

with open("quitus.pdf", "rb") as f:
    response = requests.post(url, headers=headers, files={
        "file": ("quitus.pdf", f, "application/pdf")
    }, data={
        "signer_name": "OUATTARA Oumar"
    })

result = response.json()
print(result["doc_signed"])  # URL du PDF signé
```

### JavaScript (fetch)

```javascript
const form = new FormData();
form.append("file", pdfFile); // File object
form.append("signer_name", "OUATTARA Oumar");

const response = await fetch("https://votre-api.com/v3/sign-arcop", {
    method: "POST",
    headers: { "X-API-Key": "votre_cle_api" },
    body: form
});

const result = await response.json();
console.log(result.doc_signed); // URL du PDF signé
```

### PHP (cURL)

```php
$ch = curl_init("https://votre-api.com/v3/sign-arcop");
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_HTTPHEADER, ["X-API-Key: votre_cle_api"]);
curl_setopt($ch, CURLOPT_POSTFIELDS, [
    "file"        => new CURLFile("quitus.pdf", "application/pdf"),
    "signer_name" => "OUATTARA Oumar"
]);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);

$result = json_decode(curl_exec($ch), true);
echo $result["doc_signed"];
```
