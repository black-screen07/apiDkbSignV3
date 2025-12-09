#!/usr/bin/env python3
"""
Script de test pour le système de logging.
Exécuter : python test_logging.py
"""

import sys
from pathlib import Path

# Ajouter le dossier parent au path
sys.path.insert(0, str(Path(__file__).parent))

from app.utils.debug_logger import (
    signature_logger,
    api_logger,
    error_logger,
    log_signature_process,
    log_image_info,
    log_api_request,
    log_error,
    create_session_log,
    close_session_log,
    LOGS_DIR,
    SIGNATURE_LOG_FILE,
    API_LOG_FILE,
    ERROR_LOG_FILE
)

from PIL import Image
import traceback

def test_logging_system():
    """Test complet du système de logging."""
    
    print("=" * 80)
    print("TEST DU SYSTÈME DE LOGGING - DkbSign V3")
    print("=" * 80)
    print()
    
    # 1. Vérifier que le dossier logs existe
    print(f"✓ Dossier logs: {LOGS_DIR.absolute()}")
    print(f"  - Existe: {LOGS_DIR.exists()}")
    print()
    
    # 2. Créer une session de test
    print("1. Test de session de log...")
    session_id = create_session_log("TEST_SESSION")
    print(f"   ✓ Session créée: {session_id}")
    print()
    
    # 3. Test des logs API
    print("2. Test des logs API...")
    log_api_request("/v3/sign-upload-multiple", "POST", "test@example.com", {"documents": 2})
    print("   ✓ Log API créé")
    print()
    
    # 4. Test des logs de signature
    print("3. Test des logs de signature...")
    log_signature_process(0, "Chargement de l'image", {"filename": "signature_0.png"})
    log_signature_process(1, "Chargement de l'image", {"filename": "signature_1.png"})
    print("   ✓ Logs de signature créés")
    print()
    
    # 5. Test des logs d'image
    print("4. Test des logs d'image PIL...")
    test_image = Image.new('RGB', (150, 50), color='white')
    log_image_info(0, test_image, "Test d'image")
    log_image_info(1, None, "Test image None")
    print("   ✓ Logs d'image créés")
    print()
    
    # 6. Test des logs de processus
    print("5. Test des logs de processus...")
    log_signature_process(0, "Application de la signature", level="DEBUG")
    log_signature_process(1, "Application de la signature", level="INFO")
    log_signature_process(2, "Avertissement", level="WARNING")
    print("   ✓ Logs de processus créés")
    print()
    
    # 7. Test des logs d'erreur
    print("6. Test des logs d'erreur...")
    try:
        raise ValueError("Erreur de test")
    except Exception as e:
        log_error(e, "Test d'erreur", traceback.format_exc())
    print("   ✓ Logs d'erreur créés")
    print()
    
    # 8. Fermer la session
    print("7. Fermeture de session...")
    close_session_log(session_id, success=True, message="Test terminé avec succès")
    print("   ✓ Session fermée")
    print()
    
    # 9. Vérifier les fichiers créés
    print("8. Vérification des fichiers de logs...")
    files_created = []
    
    if SIGNATURE_LOG_FILE.exists():
        size = SIGNATURE_LOG_FILE.stat().st_size
        files_created.append(f"   ✓ {SIGNATURE_LOG_FILE.name} ({size} bytes)")
    
    if API_LOG_FILE.exists():
        size = API_LOG_FILE.stat().st_size
        files_created.append(f"   ✓ {API_LOG_FILE.name} ({size} bytes)")
    
    if ERROR_LOG_FILE.exists():
        size = ERROR_LOG_FILE.stat().st_size
        files_created.append(f"   ✓ {ERROR_LOG_FILE.name} ({size} bytes)")
    
    for file_info in files_created:
        print(file_info)
    print()
    
    # 10. Afficher un extrait des logs
    print("9. Extrait des logs de signature (dernières 10 lignes)...")
    print("-" * 80)
    if SIGNATURE_LOG_FILE.exists():
        with open(SIGNATURE_LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[-10:]:
                print(f"   {line.rstrip()}")
    print("-" * 80)
    print()
    
    # Résumé
    print("=" * 80)
    print("✅ TOUS LES TESTS RÉUSSIS!")
    print("=" * 80)
    print()
    print("Fichiers de logs créés dans:", LOGS_DIR.absolute())
    print()
    print("Commandes utiles:")
    print(f"  - Voir les logs de signature: tail -f {SIGNATURE_LOG_FILE}")
    print(f"  - Voir les logs API: tail -f {API_LOG_FILE}")
    print(f"  - Voir les erreurs: tail -f {ERROR_LOG_FILE}")
    print()
    print("Pour nettoyer les logs de test:")
    print(f"  rm {LOGS_DIR}/*.log*")
    print()

if __name__ == "__main__":
    try:
        test_logging_system()
    except Exception as e:
        print(f"\n❌ ERREUR: {str(e)}")
        traceback.print_exc()
        sys.exit(1)
