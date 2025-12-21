"""
Script de test rapide pour l'API de gestion des signatures externes
Routes publiques sans authentification
"""

import requests
import json
from pathlib import Path

# Configuration
API_BASE_URL = "http://localhost:5000/v3"  # Ajuster selon votre configuration

def test_external_signatures_api():
    """Test des endpoints de signatures externes (routes publiques)"""
    
    print("="*70)
    print("TEST DE L'API DE GESTION DES SIGNATURES EXTERNES")
    print("(Routes publiques sans authentification)")
    print("="*70)
    
    headers = {}  # Pas d'authentification nécessaire
    
    # Test 1: Liste des signatures (devrait être vide au début)
    print("\n1️⃣ Test: Liste des signatures")
    print("-"*70)
    response = requests.get(f"{API_BASE_URL}/external-signatures/list", headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Nombre de signatures: {data.get('total', 0)}")
        print(json.dumps(data, indent=2))
    else:
        print(f"❌ Erreur: {response.text}")
    
    # Test 2: Vérification d'une signature inexistante
    print("\n2️⃣ Test: Vérification d'une signature inexistante")
    print("-"*70)
    test_email = "test.user@example.com"
    response = requests.get(f"{API_BASE_URL}/external-signatures/check/{test_email}", headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Existe: {data.get('exists')}")
        print(json.dumps(data, indent=2))
    else:
        print(f"❌ Erreur: {response.text}")
    
    # Test 3: Upload d'une signature (simulé avec une image test)
    print("\n3️⃣ Test: Upload d'une signature")
    print("-"*70)
    print("ℹ️ Pour ce test, créez une image test ou utilisez une image existante")
    print("   Exemple: python -c \"from PIL import Image; Image.new('RGB', (200, 100), 'white').save('test_signature.png')\"")
    
    # Créer une image test si PIL est disponible
    try:
        from PIL import Image, ImageDraw
        
        # Créer une image de signature test
        img = Image.new('RGBA', (200, 100), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 190, 90], outline='black', width=2)
        draw.text((50, 40), "Test Signature", fill='black')
        
        test_image_path = "test_signature.png"
        img.save(test_image_path)
        print(f"✅ Image test créée: {test_image_path}")
        
        # Upload de la signature
        with open(test_image_path, 'rb') as f:
            files = {'signature_image': f}
            data = {'email': test_email, 'overwrite': 'false'}
            response = requests.post(
                f"{API_BASE_URL}/external-signatures/upload",
                headers=headers,
                files=files,
                data=data
            )
        
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Upload réussi")
            print(json.dumps(response.json(), indent=2))
        else:
            print(f"❌ Erreur: {response.text}")
        
        # Test 4: Vérification après upload
        print("\n4️⃣ Test: Vérification après upload")
        print("-"*70)
        response = requests.get(f"{API_BASE_URL}/external-signatures/check/{test_email}", headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Existe: {data.get('exists')}")
            print(json.dumps(data, indent=2))
        
        # Test 5: Téléchargement de la signature
        print("\n5️⃣ Test: Téléchargement de la signature")
        print("-"*70)
        response = requests.get(f"{API_BASE_URL}/external-signatures/get/{test_email}", headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            download_path = "downloaded_signature.png"
            with open(download_path, 'wb') as f:
                f.write(response.content)
            print(f"✅ Signature téléchargée: {download_path}")
        else:
            print(f"❌ Erreur: {response.text}")
        
        # Test 6: Liste après upload
        print("\n6️⃣ Test: Liste après upload")
        print("-"*70)
        response = requests.get(f"{API_BASE_URL}/external-signatures/list", headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Nombre de signatures: {data.get('total', 0)}")
            for sig in data.get('signatures', []):
                print(f"  - {sig['email']} ({sig['file_size']} bytes)")
        
        # Test 7: Suppression de la signature
        print("\n7️⃣ Test: Suppression de la signature")
        print("-"*70)
        response = requests.delete(f"{API_BASE_URL}/external-signatures/delete/{test_email}", headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Suppression réussie")
            print(json.dumps(response.json(), indent=2))
        else:
            print(f"❌ Erreur: {response.text}")
        
        # Test 8: Vérification après suppression
        print("\n8️⃣ Test: Vérification après suppression")
        print("-"*70)
        response = requests.get(f"{API_BASE_URL}/external-signatures/check/{test_email}", headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Existe: {data.get('exists')}")
            if not data.get('exists'):
                print("✅ Signature correctement supprimée")
        
        # Nettoyage
        try:
            Path(test_image_path).unlink()
            Path(download_path).unlink()
            print("\n🧹 Fichiers de test nettoyés")
        except:
            pass
        
    except ImportError:
        print("⚠️ PIL/Pillow non installé. Installez-le avec: pip install Pillow")
        print("   Ou créez manuellement une image test et modifiez le script")
    except Exception as e:
        print(f"❌ Erreur lors du test: {str(e)}")
    
    print("\n" + "="*70)
    print("TESTS TERMINÉS")
    print("="*70)


def test_sign_with_stored_signature():
    """Test de signature avec une signature stockée"""
    
    print("\n" + "="*70)
    print("TEST DE SIGNATURE AVEC SIGNATURE STOCKÉE")
    print("="*70)
    
    print("""
    Pour tester la signature avec une signature stockée:
    
    1. Assurez-vous d'avoir uploadé une signature pour un email
    2. Préparez un PDF à signer
    3. Utilisez le format suivant dans signers_data:
    
    {
        "name": "Doe",
        "firstname": "John",
        "function": "Directeur",
        "email": "john.doe@example.com",
        "use_stored_signature": true  ← Active la récupération automatique
    }
    
    4. Appelez /v3/sign-upload-multiple sans uploader de fichier signature_image_X
    
    L'API ira automatiquement chercher l'image dans:
    signatures/external_public/<email_sanitized>/signature.png
    """)


if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════════════════════════╗
    ║  DKB Sign - Test de l'API de signatures externes                  ║
    ║  Routes publiques sans authentification                            ║
    ╚════════════════════════════════════════════════════════════════════╝
    
    Configuration requise:
    1. Serveur DKB Sign en cours d'exécution
    2. PIL/Pillow installé (pip install Pillow)
    
    Note: Ces routes sont publiques et ne nécessitent pas de clé API
    
    """)
    
    try:
        # Tester les endpoints
        test_external_signatures_api()
        
        # Afficher les instructions pour le test de signature
        test_sign_with_stored_signature()
        
    except requests.exceptions.ConnectionError:
        print("\n❌ ERREUR: Impossible de se connecter au serveur")
        print(f"   Vérifiez que le serveur est en cours d'exécution sur {API_BASE_URL}")
    except Exception as e:
        print(f"\n❌ ERREUR: {str(e)}")
        import traceback
        traceback.print_exc()
