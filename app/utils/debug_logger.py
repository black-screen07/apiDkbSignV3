"""
Module de logging dédié pour le débogage en production.
Crée des fichiers de logs séparés avec rotation automatique.
"""

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from datetime import datetime

# Créer le dossier de logs s'il n'existe pas
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Fichiers de logs spécifiques
SIGNATURE_LOG_FILE = LOGS_DIR / "signature_debug.log"
API_LOG_FILE = LOGS_DIR / "api_requests.log"
ERROR_LOG_FILE = LOGS_DIR / "errors.log"


def setup_debug_logger(name="signature_debug", log_file=None, level=logging.DEBUG):
    """
    Configure un logger dédié avec rotation de fichiers.
    
    Args:
        name: Nom du logger
        log_file: Chemin du fichier de log (optionnel)
        level: Niveau de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        Logger configuré
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Éviter les doublons de handlers
    if logger.handlers:
        return logger
    
    # Format détaillé pour le débogage
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler pour fichier avec rotation (max 10MB, garde 5 fichiers)
    if log_file is None:
        log_file = SIGNATURE_LOG_FILE
    
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Handler pour console (optionnel, utile en développement)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


def setup_api_logger():
    """Logger spécifique pour les requêtes API."""
    return setup_debug_logger("api_requests", API_LOG_FILE, logging.INFO)


def setup_error_logger():
    """Logger spécifique pour les erreurs critiques."""
    return setup_debug_logger("error_logger", ERROR_LOG_FILE, logging.ERROR)


# Loggers préconfigurés
signature_logger = setup_debug_logger("signature_debug", SIGNATURE_LOG_FILE)
api_logger = setup_api_logger()
error_logger = setup_error_logger()


def log_signature_process(signer_index, step, data=None, level="INFO"):
    """
    Log une étape du processus de signature.
    
    Args:
        signer_index: Index du signataire
        step: Description de l'étape
        data: Données additionnelles (dict)
        level: Niveau de log (INFO, DEBUG, WARNING, ERROR)
    """
    message = f"[Signataire {signer_index}] {step}"
    if data:
        message += f" | Data: {data}"
    
    log_method = getattr(signature_logger, level.lower(), signature_logger.info)
    log_method(message)


def log_image_info(signer_index, image, context=""):
    """
    Log les informations détaillées d'une image PIL.
    
    Args:
        signer_index: Index du signataire
        image: Objet PIL Image
        context: Contexte de l'image (ex: "chargement", "avant signature")
    """
    if image is None:
        signature_logger.warning(f"[Signataire {signer_index}] {context} - Image est None!")
        return
    
    try:
        info = {
            "type": str(type(image)),
            "size": image.size if hasattr(image, 'size') else "N/A",
            "mode": image.mode if hasattr(image, 'mode') else "N/A",
            "format": image.format if hasattr(image, 'format') else "N/A"
        }
        signature_logger.info(f"[Signataire {signer_index}] {context} - Image: {info}")
    except Exception as e:
        signature_logger.error(f"[Signataire {signer_index}] Erreur lors du log de l'image: {str(e)}")


def log_api_request(endpoint, method, user_email=None, params=None):
    """
    Log une requête API.
    
    Args:
        endpoint: URL de l'endpoint
        method: Méthode HTTP (GET, POST, etc.)
        user_email: Email de l'utilisateur authentifié
        params: Paramètres de la requête
    """
    message = f"{method} {endpoint}"
    if user_email:
        message += f" | User: {user_email}"
    if params:
        message += f" | Params: {params}"
    
    api_logger.info(message)


def log_error(error, context="", traceback_str=None):
    """
    Log une erreur avec contexte et traceback.
    
    Args:
        error: Exception ou message d'erreur
        context: Contexte de l'erreur
        traceback_str: Traceback formaté (optionnel)
    """
    message = f"{context} - Error: {str(error)}"
    error_logger.error(message)
    
    if traceback_str:
        error_logger.error(f"Traceback:\n{traceback_str}")


def create_session_log(session_id=None):
    """
    Crée un log de session pour tracer une requête complète.
    
    Args:
        session_id: ID de session (généré automatiquement si None)
    
    Returns:
        session_id pour référence
    """
    if session_id is None:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    
    signature_logger.info(f"{'='*80}")
    signature_logger.info(f"NOUVELLE SESSION: {session_id}")
    signature_logger.info(f"{'='*80}")
    
    return session_id


def close_session_log(session_id, success=True, message=""):
    """
    Ferme un log de session.
    
    Args:
        session_id: ID de la session
        success: Succès ou échec de la session
        message: Message de fin
    """
    status = "✅ SUCCÈS" if success else "❌ ÉCHEC"
    signature_logger.info(f"{status} - Session {session_id}: {message}")
    signature_logger.info(f"{'='*80}\n")


# Fonction utilitaire pour nettoyer les vieux logs
def cleanup_old_logs(days=30):
    """
    Supprime les fichiers de logs plus vieux que X jours.
    
    Args:
        days: Nombre de jours à conserver
    """
    import time
    
    current_time = time.time()
    max_age = days * 24 * 60 * 60  # Convertir en secondes
    
    for log_file in LOGS_DIR.glob("*.log*"):
        file_age = current_time - log_file.stat().st_mtime
        if file_age > max_age:
            try:
                log_file.unlink()
                signature_logger.info(f"Ancien fichier de log supprimé: {log_file.name}")
            except Exception as e:
                signature_logger.error(f"Erreur lors de la suppression de {log_file.name}: {str(e)}")


if __name__ == "__main__":
    # Test du système de logging
    print("Test du système de logging...")
    
    session_id = create_session_log()
    
    log_api_request("/v3/sign-upload-multiple", "POST", "test@example.com", {"documents": 2})
    
    log_signature_process(0, "Chargement de l'image", {"filename": "signature_0.png"})
    log_signature_process(1, "Chargement de l'image", {"filename": "signature_1.png"})
    
    # Simuler une image PIL
    from PIL import Image
    test_image = Image.new('RGB', (150, 50), color='white')
    log_image_info(0, test_image, "Test d'image")
    
    log_signature_process(0, "Application de la signature", level="DEBUG")
    log_signature_process(1, "Application de la signature", level="DEBUG")
    
    close_session_log(session_id, success=True, message="2 documents signés avec succès")
    
    print(f"\nLogs créés dans le dossier: {LOGS_DIR.absolute()}")
    print(f"- Signatures: {SIGNATURE_LOG_FILE}")
    print(f"- API: {API_LOG_FILE}")
    print(f"- Erreurs: {ERROR_LOG_FILE}")
