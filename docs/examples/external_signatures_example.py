"""
Exemple d'utilisation de l'API de gestion des signatures publiques externes
avec la route /v3/sign-upload-multiple

Ce script démontre comment :
1. Uploader des signatures pour des signataires externes
2. Vérifier l'existence de signatures stockées
3. Signer des documents en utilisant les signatures stockées
"""

import requests
import json
from pathlib import Path

# Configuration
API_BASE_URL = "https://api.dkbsign.com/v3"
API_KEY = "votre_cle_api_ici"  # Nécessaire uniquement pour /v3/sign-upload-multiple

# Note: Les routes de gestion des signatures externes sont publiques (pas d'authentification)


class ExternalSignatureManager:
    """Gestionnaire de signatures externes pour DKB Sign API (routes publiques)"""
    
    def __init__(self, api_key=None, base_url=API_BASE_URL):
        self.api_key = api_key  # Optionnel pour les routes de signatures externes
        self.base_url = base_url
        self.headers = {"X-API-Key": api_key} if api_key else {}  # Headers vides pour routes publiques
    
    def upload_signature(self, email, signature_file_path, overwrite=False):
        """
        Upload une signature pour un signataire externe.
        
        Args:
            email (str): Email du signataire
            signature_file_path (str): Chemin vers le fichier image
            overwrite (bool): Écraser si existe déjà
        
        Returns:
            dict: Réponse de l'API
        """
        url = f"{self.base_url}/external-signatures/upload"
        
        with open(signature_file_path, 'rb') as f:
            files = {'signature_image': f}
            data = {
                'email': email,
                'overwrite': str(overwrite).lower()
            }
            
            # Pas besoin d'authentification pour cette route publique
            response = requests.post(url, files=files, data=data)
            
        if response.status_code == 200:
            print(f"✅ Signature uploadée pour {email}")
        elif response.status_code == 409:
            print(f"⚠️ Signature déjà existante pour {email}")
        else:
            print(f"❌ Erreur upload: {response.text}")
        
        return response.json()
    
    def check_signature_exists(self, email):
        """
        Vérifie si une signature existe pour un email.
        Route publique sans authentification.
        
        Args:
            email (str): Email du signataire
        
        Returns:
            bool: True si la signature existe
        """
        url = f"{self.base_url}/external-signatures/check/{email}"
        response = requests.get(url)  # Pas d'authentification nécessaire
        
        if response.status_code == 200:
            data = response.json()
            exists = data.get('exists', False)
            if exists:
                print(f"✅ Signature trouvée pour {email}")
            else:
                print(f"❌ Aucune signature pour {email}")
            return exists
        
        return False
    
    def download_signature(self, email, output_path):
        """
        Télécharge une signature stockée.
        Route publique sans authentification.
        
        Args:
            email (str): Email du signataire
            output_path (str): Chemin de sauvegarde
        
        Returns:
            bool: True si succès
        """
        url = f"{self.base_url}/external-signatures/get/{email}"
        response = requests.get(url)  # Pas d'authentification nécessaire
        
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            print(f"✅ Signature téléchargée: {output_path}")
            return True
        else:
            print(f"❌ Erreur téléchargement: {response.text}")
            return False
    
    def delete_signature(self, email):
        """
        Supprime une signature stockée.
        Route publique sans authentification.
        
        Args:
            email (str): Email du signataire
        
        Returns:
            dict: Réponse de l'API
        """
        url = f"{self.base_url}/external-signatures/delete/{email}"
        response = requests.delete(url)  # Pas d'authentification nécessaire
        
        if response.status_code == 200:
            print(f"✅ Signature supprimée pour {email}")
        else:
            print(f"❌ Erreur suppression: {response.text}")
        
        return response.json()
    
    def list_all_signatures(self):
        """
        Liste toutes les signatures stockées.
        Route publique sans authentification.
        
        Returns:
            list: Liste des signatures
        """
        url = f"{self.base_url}/external-signatures/list"
        response = requests.get(url)  # Pas d'authentification nécessaire
        
        if response.status_code == 200:
            data = response.json()
            signatures = data.get('signatures', [])
            print(f"📋 {len(signatures)} signature(s) stockée(s)")
            for sig in signatures:
                print(f"  - {sig['email']} ({sig['file_size']} bytes)")
            return signatures
        
        return []
    
    def sign_documents_with_stored_signatures(self, documents, signers_data, signature_params):
        """
        Signe des documents en utilisant des signatures stockées.
        Note: Cette route nécessite une clé API (contrairement aux routes de gestion des signatures).
        
        Args:
            documents (list): Liste de chemins vers les PDFs
            signers_data (list): Données des signataires
            signature_params (list): Paramètres de signature
        
        Returns:
            dict: Réponse de l'API
        """
        url = f"{self.base_url}/sign-upload-multiple"
        
        # Cette route nécessite une authentification par clé API
        if not self.api_key:
            print("❌ Erreur: Clé API requise pour la signature de documents")
            return {"error": "API key required for signing documents"}
        
        # Préparer les fichiers
        files = []
        for i, doc_path in enumerate(documents):
            files.append(('documents', open(doc_path, 'rb')))
        
        # Préparer les données
        data = {
            'signers_data': json.dumps(signers_data),
            'signature_params': json.dumps(signature_params)
        }
        
        try:
            response = requests.post(url, headers=self.headers, files=files, data=data)
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ {result.get('message')}")
                for doc in result.get('signed_documents', []):
                    print(f"  📄 {doc['document_name']}: {doc['signed_pdf_url']}")
                return result
            else:
                print(f"❌ Erreur signature: {response.text}")
                return response.json()
        
        finally:
            # Fermer tous les fichiers
            for _, file_obj in files:
                file_obj.close()


# ============================================================================
# EXEMPLES D'UTILISATION
# ============================================================================

def example_1_upload_signatures():
    """Exemple 1: Upload de signatures pour plusieurs signataires"""
    print("\n" + "="*60)
    print("EXEMPLE 1: Upload de signatures externes")
    print("="*60)
    
    manager = ExternalSignatureManager(API_KEY)
    
    # Liste des signataires avec leurs fichiers de signature
    signers = [
        {
            "email": "john.doe@example.com",
            "signature_file": "signatures/john_doe_signature.png"
        },
        {
            "email": "jane.smith@example.com",
            "signature_file": "signatures/jane_smith_signature.png"
        },
        {
            "email": "bob.wilson@example.com",
            "signature_file": "signatures/bob_wilson_signature.png"
        }
    ]
    
    # Upload de chaque signature
    for signer in signers:
        manager.upload_signature(
            email=signer["email"],
            signature_file_path=signer["signature_file"],
            overwrite=False
        )


def example_2_check_and_list():
    """Exemple 2: Vérification et listage des signatures"""
    print("\n" + "="*60)
    print("EXEMPLE 2: Vérification et listage")
    print("="*60)
    
    manager = ExternalSignatureManager(API_KEY)
    
    # Vérifier des signatures spécifiques
    emails_to_check = [
        "john.doe@example.com",
        "jane.smith@example.com",
        "unknown@example.com"
    ]
    
    print("\n📋 Vérification des signatures:")
    for email in emails_to_check:
        manager.check_signature_exists(email)
    
    # Lister toutes les signatures
    print("\n📋 Liste complète:")
    manager.list_all_signatures()


def example_3_sign_with_stored_signatures():
    """Exemple 3: Signature de documents avec signatures stockées"""
    print("\n" + "="*60)
    print("EXEMPLE 3: Signature avec signatures stockées")
    print("="*60)
    
    manager = ExternalSignatureManager(API_KEY)
    
    # Documents à signer
    documents = [
        "documents/contract_001.pdf",
        "documents/contract_002.pdf"
    ]
    
    # Données des signataires (avec use_stored_signature: true)
    signers_data = [
        {
            "name": "Doe",
            "firstname": "John",
            "function": "Directeur Général",
            "email": "john.doe@example.com",
            "phone": "+33612345678",
            "use_stored_signature": True  # ← Utilise la signature stockée
        },
        {
            "name": "Smith",
            "firstname": "Jane",
            "function": "Directrice Financière",
            "email": "jane.smith@example.com",
            "phone": "+33698765432",
            "use_stored_signature": True  # ← Utilise la signature stockée
        }
    ]
    
    # Paramètres de signature
    signature_params = [
        # Document 0, Signataire 0 (John)
        {
            "document_index": 0,
            "signer_index": 0,
            "pages": [
                {
                    "page": 0,
                    "signatures": [{"x": 100, "y": 200}]
                }
            ],
            "signature_size": {"width": 150, "height": 50},
            "show_signer_info": True
        },
        # Document 0, Signataire 1 (Jane)
        {
            "document_index": 0,
            "signer_index": 1,
            "pages": [
                {
                    "page": 0,
                    "signatures": [{"x": 100, "y": 300}]
                }
            ],
            "signature_size": {"width": 150, "height": 50},
            "show_signer_info": True
        },
        # Document 1, Signataire 0 (John)
        {
            "document_index": 1,
            "signer_index": 0,
            "sign_on_last_page": True,
            "signature_size": {"width": 150, "height": 50}
        }
    ]
    
    # Signer les documents
    result = manager.sign_documents_with_stored_signatures(
        documents=documents,
        signers_data=signers_data,
        signature_params=signature_params
    )


def example_4_mixed_signatures():
    """Exemple 4: Mélange de signatures stockées et uploadées"""
    print("\n" + "="*60)
    print("EXEMPLE 4: Signatures mixtes (stockées + uploadées)")
    print("="*60)
    
    manager = ExternalSignatureManager(API_KEY)
    
    # Document à signer
    documents = ["documents/contract_003.pdf"]
    
    # Signataires mixtes
    signers_data = [
        {
            "name": "Doe",
            "firstname": "John",
            "function": "Directeur",
            "email": "john.doe@example.com",
            "use_stored_signature": True  # ← Signature stockée
        },
        {
            "name": "New",
            "firstname": "Signer",
            "function": "Consultant",
            "email": "new.signer@example.com",
            "use_stored_signature": False  # ← Signature uploadée avec la requête
        }
    ]
    
    signature_params = [
        {
            "document_index": 0,
            "signer_index": 0,
            "pages": [{"page": 0, "signatures": [{"x": 100, "y": 200}]}]
        },
        {
            "document_index": 0,
            "signer_index": 1,
            "pages": [{"page": 0, "signatures": [{"x": 100, "y": 300}]}]
        }
    ]
    
    # Préparer la requête avec upload d'image pour le signataire 1
    url = f"{manager.base_url}/sign-upload-multiple"
    
    files = [
        ('documents', open(documents[0], 'rb')),
        ('signature_image_1', open('signatures/new_signer.png', 'rb'))  # Pour signataire 1
    ]
    
    data = {
        'signers_data': json.dumps(signers_data),
        'signature_params': json.dumps(signature_params)
    }
    
    response = requests.post(url, headers=manager.headers, files=files, data=data)
    
    # Fermer les fichiers
    for _, f in files:
        f.close()
    
    if response.status_code == 200:
        print("✅ Documents signés avec signatures mixtes")
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"❌ Erreur: {response.text}")


def example_5_update_signature():
    """Exemple 5: Mise à jour d'une signature existante"""
    print("\n" + "="*60)
    print("EXEMPLE 5: Mise à jour d'une signature")
    print("="*60)
    
    manager = ExternalSignatureManager(API_KEY)
    
    email = "john.doe@example.com"
    
    # Vérifier si existe
    if manager.check_signature_exists(email):
        # Télécharger l'ancienne (backup)
        manager.download_signature(email, f"backup_{email.replace('@', '_')}.png")
        
        # Uploader la nouvelle (avec overwrite)
        manager.upload_signature(
            email=email,
            signature_file_path="signatures/john_doe_new_signature.png",
            overwrite=True
        )
        
        print(f"✅ Signature mise à jour pour {email}")


def example_6_cleanup():
    """Exemple 6: Nettoyage des signatures non utilisées"""
    print("\n" + "="*60)
    print("EXEMPLE 6: Nettoyage des signatures")
    print("="*60)
    
    manager = ExternalSignatureManager(API_KEY)
    
    # Emails à supprimer
    emails_to_delete = [
        "old.signer@example.com",
        "inactive.user@example.com"
    ]
    
    for email in emails_to_delete:
        if manager.check_signature_exists(email):
            manager.delete_signature(email)


# ============================================================================
# WORKFLOW COMPLET
# ============================================================================

def complete_workflow():
    """Workflow complet: Setup → Sign → Cleanup"""
    print("\n" + "="*80)
    print("WORKFLOW COMPLET: Gestion des signatures externes")
    print("="*80)
    
    manager = ExternalSignatureManager(API_KEY)
    
    # ÉTAPE 1: Setup initial - Upload des signatures
    print("\n📤 ÉTAPE 1: Upload des signatures")
    print("-" * 80)
    signers = [
        {"email": "ceo@company.com", "file": "signatures/ceo.png"},
        {"email": "cfo@company.com", "file": "signatures/cfo.png"},
        {"email": "legal@company.com", "file": "signatures/legal.png"}
    ]
    
    for signer in signers:
        manager.upload_signature(signer["email"], signer["file"])
    
    # ÉTAPE 2: Vérification
    print("\n🔍 ÉTAPE 2: Vérification des signatures")
    print("-" * 80)
    manager.list_all_signatures()
    
    # ÉTAPE 3: Signature de documents
    print("\n✍️ ÉTAPE 3: Signature de documents")
    print("-" * 80)
    
    documents = ["contract.pdf"]
    signers_data = [
        {
            "name": "CEO",
            "firstname": "Company",
            "function": "Chief Executive Officer",
            "email": "ceo@company.com",
            "use_stored_signature": True
        },
        {
            "name": "CFO",
            "firstname": "Company",
            "function": "Chief Financial Officer",
            "email": "cfo@company.com",
            "use_stored_signature": True
        }
    ]
    
    signature_params = [
        {
            "document_index": 0,
            "signer_index": 0,
            "pages": [{"page": 0, "signatures": [{"x": 100, "y": 200}]}]
        },
        {
            "document_index": 0,
            "signer_index": 1,
            "pages": [{"page": 0, "signatures": [{"x": 100, "y": 300}]}]
        }
    ]
    
    manager.sign_documents_with_stored_signatures(
        documents, signers_data, signature_params
    )
    
    print("\n✅ Workflow terminé avec succès!")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════════════════════════╗
    ║  DKB Sign - Exemples d'utilisation des signatures externes        ║
    ╚════════════════════════════════════════════════════════════════════╝
    """)
    
    # Décommenter l'exemple que vous voulez exécuter
    
    # example_1_upload_signatures()
    # example_2_check_and_list()
    # example_3_sign_with_stored_signatures()
    # example_4_mixed_signatures()
    # example_5_update_signature()
    # example_6_cleanup()
    
    # Ou exécuter le workflow complet
    # complete_workflow()
    
    print("\n" + "="*80)
    print("Pour utiliser ces exemples:")
    print("1. Remplacez API_KEY par votre clé API")
    print("2. Ajustez les chemins des fichiers selon votre structure")
    print("3. Décommentez l'exemple que vous voulez exécuter")
    print("="*80)
