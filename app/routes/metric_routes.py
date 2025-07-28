from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from app.models import User, Company, Document, Signature, Draft, Contact
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
import datetime

metric_bp = Blueprint('metric_bp', __name__)


@metric_bp.route('/metrics', methods=['GET'])
@jwt_required()
def get_advanced_dashboard_metrics():
    """
    Endpoint pour récupérer les métriques avancées du tableau de bord de l'API de signature électronique.
    Inclut :
    - Nombre total d'utilisateurs (individuels et employés)
    - Nombre total de compagnies
    - Utilisateurs actifs et compagnies actives
    - Documents (signés, en attente)
    - Brouillons
    - Volume total de signatures électroniques utilisées
    - Top 5 des utilisateurs les plus actifs (par volume de signatures)
    - Volume total et utilisé des compagnies
    - Ratio des signatures effectuées par type de certificat
    """
    try:
        # Métriques sur les utilisateurs
        total_users = User.query.count()
        active_users = User.query.filter(User.archived == False).count()
        individual_users = User.query.filter(User.account_type == "individual").count()
        employee_users = User.query.filter(User.account_type == "employee").count()

        # Métriques sur les compagnies
        total_companies = Company.query.count()
        active_companies = Company.query.filter(Company.archived == False).count()

        # Métriques sur les documents
        total_documents = Document.query.count()
        signed_documents = Document.query.filter(Document.status == "signed").count()
        pending_documents = Document.query.filter(Document.status == "pending").count()

        # Métriques sur les brouillons
        total_drafts = Draft.query.count()

        # Métriques sur les signatures électroniques
        total_signatures = Signature.query.count()

        # Volume total de signatures électroniques utilisées par toutes les compagnies
        total_signature_volume_used = db.session.query(db.func.sum(Company.signature_volume_used)).scalar() or 0

        # Top 5 des utilisateurs les plus actifs par volume de signatures utilisées
        top_active_users = (
            db.session.query(User.name, User.email, db.func.sum(User.signature_volume_used).label("total_used"))
            .filter(User.archived == False)
            .group_by(User.id)
            .order_by(db.desc("total_used"))
            .limit(5)
            .all()
        )

        # Volume de signatures par compagnie
        company_signature_volumes = (
            db.session.query(
                Company.name,
                db.func.sum(Company.signature_volume_used).label("used_volume"),
                db.func.sum(Company.signature_volume).label("total_volume")
            )
            .group_by(Company.id)
            .all()
        )

        # Ratio des signatures par type de certificat
        cert_type_ratios = (
            db.session.query(
                Company.cert_type,
                db.func.count(Company.cert_type).label("count")
            )
            .group_by(Company.cert_type)
            .all()
        )
        cert_type_data = {cert_type: count for cert_type, count in cert_type_ratios}

        # Construire les données des métriques
        metrics = {
            "users": {
                "total": total_users,
                "active": active_users,
                "individual": individual_users,
                "employee": employee_users,
                "top_active": [
                    {"name": user[0], "email": user[1], "total_used": user[2]} for user in top_active_users
                ]
            },
            "companies": {
                "total": total_companies,
                "active": active_companies,
                "signature_volumes": [
                    {
                        "name": company[0],
                        "used_volume": company[1],
                        "total_volume": company[2]
                    } for company in company_signature_volumes
                ],
                "cert_type_distribution": cert_type_data
            },
            "documents": {
                "total": total_documents,
                "signed": signed_documents,
                "pending": pending_documents
            },
            "drafts": {
                "total": total_drafts
            },
            "signatures": {
                "total": total_signatures,
                "volume_used": total_signature_volume_used
            }
        }

        return jsonify({
            "message": "Métriques du tableau de bord récupérées avec succès.",
            "metrics": metrics
        }), 200

    except Exception as e:
        return jsonify({"error": f"Erreur lors de la récupération des métriques : {str(e)}"}), 500


@metric_bp.route('/user-metrics', methods=['GET'])
@jwt_required()
def get_user_metrics():
    """
    Endpoint pour récupérer les métriques spécifiques à un utilisateur.
    Inclut :
    - Documents récents (5 derniers)
    - Statistiques des documents (graphique circulaire et courbe)
    - Métriques globales (cartes)
    """
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Récupérer les signatures associées à l'utilisateur
        user_signatures = Signature.query.filter_by(signer_id=user.id).all()

        # 1. Documents récents (5 derniers)
        recent_documents = (
            Document.query
            .filter_by(user_id=user.id)  # Utilisation de user_id pour filtrer
            .order_by(Document.created_at.desc())
            .limit(5)
            .all()
        )

        recent_docs_data = [{
            "name": doc.name,
            "size": len(doc.file_path) if doc.file_path else 0,  
            "status": doc.status,
            "created_at": doc.created_at.strftime("%d/%m/%Y"),
            "signatories": [
                {
                    "name": signature.user.name,
                    "email": signature.user.email,
                    "status": signature.status
                }
                for signature in doc.signatures
            ] if hasattr(doc, 'signatures') else []
        } for doc in recent_documents]

        # 2. Statistiques des documents
        # Total par statut pour le graphique circulaire
        status_counts = (
            db.session.query(
                Document.status,
                db.func.count(Document.id).label('count')
            )
            .filter_by(user_id=user.id)
            .group_by(Document.status)
            .all()
        )

        # Évolution mensuelle par statut
        monthly_stats = (
            db.session.query(
                db.func.DATE_FORMAT(Document.created_at, '%Y-%m-01').label('month'),
                Document.status,
                db.func.count(Document.id).label('count')
            )
            .filter_by(user_id=user.id)
            .group_by(db.func.DATE_FORMAT(Document.created_at, '%Y-%m-01'), Document.status)
            .order_by(db.func.DATE_FORMAT(Document.created_at, '%Y-%m-01'))
            .all()
        )

        # Formater les données mensuelles
        monthly_data = {}
        for stat in monthly_stats:
            month = datetime.datetime.strptime(stat[0], '%Y-%m-%d').strftime("%b")  
            if month not in monthly_data:
                monthly_data[month] = {"signés": 0, "refusés": 0, "enAttentes": 0}
            status_map = {
                "signed": "signés",
                "rejected": "refusés",
                "pending": "enAttentes"
            }
            monthly_data[month][status_map.get(stat[1].lower(), stat[1].lower())] = stat[2]

        # 3. Métriques globales
        total_documents = Document.query.filter_by(user_id=user.id).count()
        signed_documents = Document.query.filter_by(user_id=user.id, status='Signed').count()
        
        # Calcul des signatures restantes selon le type de compte
        if user.account_type == 'individual':
            remaining_signatures = user.signature_volume - user.signature_volume_used
        else:
            company = Company.query.get(user.company_id)
            remaining_signatures = (company.signature_volume - company.signature_volume_used) if company else 0

        # Total des contacts
        if user.account_type == 'employee':
            # Pour un employé, on compte les contacts de sa compagnie
            total_contacts = Contact.query.filter_by(company_id=user.company_id).count()
        else:
            # Pour un compte individuel, on compte ses contacts personnels
            total_contacts = Contact.query.filter_by(user_id=user.id).count()

        metrics = {
            "recent_documents": recent_docs_data,
            "document_stats": {
                "total": total_documents,
                "by_status": {
                    status: count for status, count in status_counts
                },
                "monthly_evolution": monthly_data
            },
            "global_metrics": {
                "total_documents": total_documents,
                "signed_documents": signed_documents,
                "remaining_signatures": remaining_signatures,
                "total_contacts": total_contacts
            }
        }

        return jsonify({
            "message": "Métriques utilisateur récupérées avec succès",
            "metrics": metrics
        }), 200

    except Exception as e:
        return jsonify({"error": f"Erreur lors de la récupération des métriques utilisateur : {str(e)}"}), 500
