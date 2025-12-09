"""
Health check endpoint for Docker and monitoring
"""
from flask import Blueprint, jsonify
from app import db
import time

health_bp = Blueprint('health', __name__)

@health_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for Docker health checks and monitoring
    Returns 200 if application is healthy, 503 if not
    """
    try:
        # Check database connection
        start_time = time.time()
        db.session.execute('SELECT 1')
        db_response_time = (time.time() - start_time) * 1000  # Convert to ms
        
        return jsonify({
            'status': 'healthy',
            'service': 'DkbSign V3 API',
            'database': 'connected',
            'db_response_time_ms': round(db_response_time, 2),
            'timestamp': time.time()
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'service': 'DkbSign V3 API',
            'database': 'disconnected',
            'error': str(e),
            'timestamp': time.time()
        }), 503

@health_bp.route('/ready', methods=['GET'])
def readiness_check():
    """
    Readiness check - indicates if the application is ready to serve traffic
    """
    try:
        # More thorough checks for readiness
        db.session.execute('SELECT 1')
        
        return jsonify({
            'status': 'ready',
            'service': 'DkbSign V3 API',
            'timestamp': time.time()
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'not_ready',
            'service': 'DkbSign V3 API',
            'error': str(e),
            'timestamp': time.time()
        }), 503

@health_bp.route('/live', methods=['GET'])
def liveness_check():
    """
    Liveness check - indicates if the application is alive
    """
    return jsonify({
        'status': 'alive',
        'service': 'DkbSign V3 API',
        'timestamp': time.time()
    }), 200
