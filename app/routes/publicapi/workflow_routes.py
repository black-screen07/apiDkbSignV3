from flask import Blueprint, jsonify, request, url_for, current_app
from app.utils.api_auth_utils import require_api_key, get_authenticated_user_by_api_key
from app.models import db, Workflow, WorkflowUser, User, Flow, LineFlow, Contact, Document, Company
from datetime import datetime
from app.services.email_service import send_email
from app import db
import uuid
from PyPDF2 import PdfReader
from PyPDF2.generic import NameObject, TextStringObject, NumberObject
import os
from decimal import Decimal
import logging
from pathlib import Path
from math import ceil

publicapi_workflow_bp = Blueprint('publicapi_workflow_bp', __name__)

# Liste des actions valides pour la documentation de l'API
VALID_ACTIONS_DOC = """
Actions valides :
- sign_doc : Signer le document
- add_paraph : Ajouter un paraphe
- add_qrcode : Ajouter un QR code
- add_stamp : Ajouter un tampon
- add_date : Ajouter la date
- add_custom_text : Ajouter un texte personnalisé
- read_only : approbation (toujours)
- upload_file : Télécharger un fichier
"""

DRAFT_FOLDER = Path("documents/drafts")

@publicapi_workflow_bp.route('/workflows', methods=['POST'])
@require_api_key
def create_workflow():
    """
    Créer un nouveau workflow avec ses utilisateurs associés.
    
    Les actions valides pour chaque utilisateur sont :
    {actions_doc}
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        data = request.get_json()
        
        # Validation des données
        if not data.get('name'):
            return jsonify({"error": "Le nom du workflow est obligatoire"}), 400
        
        # Vérifier si un workflow avec ce nom existe déjà
        if Workflow.query.filter_by(name=data['name']).first():
            return jsonify({"error": f"Un workflow avec le nom '{data['name']}' existe déjà"}), 400
        
        if not data.get('users') or not isinstance(data['users'], list):
            return jsonify({"error": "La liste des utilisateurs est obligatoire"}), 400

        # Créer le workflow
        workflow = Workflow(
            name=data['name'],
            user_id=user.id
        )
        db.session.add(workflow)
        db.session.flush()

        # Ajouter les utilisateurs au workflow
        for user_data in data['users']:
            if not all(k in user_data for k in ('user_id', 'priority', 'account_type')):
                return jsonify({"error": "user_id, priority et account_type sont requis pour chaque utilisateur"}), 400

            # Vérifier les actions
            actions = user_data.get('actions', [])
            if not isinstance(actions, list):
                return jsonify({"error": "Le champ 'actions' doit être une liste"}), 400

            # Vérifier que toutes les actions sont valides
            invalid_actions = [action for action in actions if action not in WorkflowUser.VALID_ACTIONS]
            if invalid_actions:
                return jsonify({
                    "error": f"Actions invalides : {', '.join(invalid_actions)}",
                    "valid_actions": WorkflowUser.VALID_ACTIONS
                }), 400

            # Vérifier si l'utilisateur existe selon son account_type
            if user_data['account_type'] in ['employee', 'individual']:
                user_check = User.query.get(user_data['user_id'])
                if not user_check:
                    return jsonify({"error": f"L'utilisateur avec l'ID {user_data['user_id']} n'existe pas"}), 404
                if user_check.account_type != user_data['account_type']:
                    return jsonify({"error": f"L'utilisateur avec l'ID {user_data['user_id']} n'est pas de type {user_data['account_type']}"}), 400
            elif user_data['account_type'] == 'external':
                if not Contact.query.get(user_data['user_id']):
                    return jsonify({"error": f"Le contact avec l'ID {user_data['user_id']} n'existe pas"}), 404
            else:
                return jsonify({"error": f"Type de compte invalide : {user_data['account_type']}. Valeurs acceptées : 'employee', 'individual' ou 'external'"}), 400

            try:
                workflow_user = WorkflowUser(
                    workflow_id=workflow.id,
                    user_id=user_data['user_id'],
                    priority=user_data['priority'],
                    account_type=user_data['account_type'],
                    actions=actions
                )
                db.session.add(workflow_user)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400

        db.session.commit()
        
        # Récupérer les utilisateurs du workflow pour la réponse
        workflow_users = WorkflowUser.query.filter_by(workflow_id=workflow.id).order_by(WorkflowUser.priority).all()
        
        response_data = {
            "message": "Workflow créé avec succès",
            "workflow": {
                "id": workflow.id,
                "name": workflow.name,
                "created_at": workflow.created_at.isoformat(),
                "creator_id": workflow.user_id,
                "users": [{
                    "user_id": wu.user_id,
                    "priority": wu.priority,
                    "account_type": wu.account_type,
                    "actions": wu.actions
                } for wu in workflow_users]
            }
        }
        
        return jsonify(response_data), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@publicapi_workflow_bp.route('/workflows', methods=['GET'])
@require_api_key
def get_workflows():
    """
    Récupérer tous les workflows créés par l'utilisateur connecté.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        # Récupération des paramètres de pagination
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))

        # Récupérer tous les workflows créés par l'utilisateur avec pagination
        query = Workflow.query.filter_by(user_id=user.id).order_by(Workflow.created_at.desc())
        total_workflows = query.count()
        workflows = query.paginate(page=page, per_page=per_page, error_out=False).items
        
        response_data = []
        for workflow in workflows:
            # Récupérer les utilisateurs du workflow
            workflow_users = WorkflowUser.query.filter_by(workflow_id=workflow.id).order_by(WorkflowUser.priority).all()
            
            # Préparer les données des utilisateurs avec leurs détails
            users_data = []
            for wu in workflow_users:
                user_details = {}
                if wu.account_type in ['employee', 'individual']:
                    # Récupérer les détails de l'utilisateur interne
                    user_info = User.query.get(wu.user_id)
                    if user_info:
                        user_details = {
                            "id": user_info.id,
                            "email": user_info.email,
                            "name": user_info.name,
                            "sub_name": user_info.sub_name,
                            "account_type": wu.account_type
                        }
                else:
                    # Récupérer les détails du contact externe
                    contact_info = Contact.query.get(wu.user_id)
                    if contact_info:
                        user_details = {
                            "id": contact_info.id,
                            "email": contact_info.email,
                            "name": contact_info.name,
                            "phone": contact_info.phone,
                            "account_type": "external"
                        }
                
                if user_details:
                    user_details.update({
                        "priority": wu.priority,
                        "actions": wu.actions
                    })
                    users_data.append(user_details)
            
            # Créer l'objet workflow avec les détails des utilisateurs
            workflow_data = {
                "id": workflow.id,
                "name": workflow.name,
                "created_at": workflow.created_at.isoformat(),
                "creator": {
                    "id": workflow.user.id,
                    "email": workflow.user.email,
                    "name": workflow.user.name,
                    "sub_name": workflow.user.sub_name
                },
                "users": users_data,
                "flows": [{
                    "id": flow.id,
                    "current_priority": flow.current_priority,
                    "action_done": flow.action_done,
                    "reference": flow.reference,
                    "deadline": flow.deadline.isoformat() if flow.deadline else None,
                    "created_at": flow.created_at.isoformat()
                } for flow in workflow.flows]
            }
            response_data.append(workflow_data)

        # Calcul des métadonnées de pagination
        total_pages = ceil(total_workflows / per_page)
        metadata = {
            "current_page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_items": total_workflows,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }

        return jsonify({
            "message": "Workflows récupérés avec succès",
            "workflows": response_data,
            "metadata": metadata
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@publicapi_workflow_bp.route('/workflows/<int:workflow_id>', methods=['GET'])
@require_api_key
def get_workflow(workflow_id):
    """
    Récupérer un workflow spécifique avec ses détails
    """
    try:
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        workflow = Workflow.query.get(workflow_id)
        if not workflow:
            return jsonify({"error": "Workflow non trouvé"}), 404

        # Vérifier si l'utilisateur a accès à ce workflow
        if workflow.user_id != user.id and not WorkflowUser.query.filter_by(
            workflow_id=workflow.id, user_id=user.id
        ).first():
            return jsonify({"error": "Accès non autorisé à ce workflow"}), 403

        # Récupérer les utilisateurs du workflow
        workflow_users = WorkflowUser.query.filter_by(workflow_id=workflow.id).order_by(WorkflowUser.priority).all()
        
        # Préparer les données des utilisateurs avec leurs détails
        users_data = []
        for wu in workflow_users:
            user_details = {}
            if wu.account_type in ['employee', 'individual']:
                # Récupérer les détails de l'utilisateur interne
                user_info = User.query.get(wu.user_id)
                if user_info:
                    user_details = {
                        "id": user_info.id,
                        "email": user_info.email,
                        "name": user_info.name,
                        "sub_name": user_info.sub_name,
                        "account_type": wu.account_type
                    }
            else:
                # Récupérer les détails du contact externe
                contact_info = Contact.query.get(wu.user_id)
                if contact_info:
                    user_details = {
                        "id": contact_info.id,
                        "email": contact_info.email,
                        "name": contact_info.name,
                        "phone": contact_info.phone,
                        "account_type": "external"
                    }
            
            if user_details:
                user_details.update({
                    "priority": wu.priority,
                    "actions": wu.actions
                })
                users_data.append(user_details)
        
        response_data = {
            "message": "Workflow récupéré avec succès",
            "workflow": {
                "id": workflow.id,
                "name": workflow.name,
                "created_at": workflow.created_at.isoformat(),
                "updated_at": workflow.updated_at.isoformat(),
                "creator": {
                    "id": workflow.user.id,
                    "email": workflow.user.email,
                    "name": workflow.user.name,
                    "sub_name": workflow.user.sub_name
                },
                "users": users_data,
                "flows": [{
                    "id": flow.id,
                    "current_priority": flow.current_priority,
                    "action_done": flow.action_done,
                    "reference": flow.reference,
                    "deadline": flow.deadline.isoformat() if flow.deadline else None,
                    "created_at": flow.created_at.isoformat()
                } for flow in workflow.flows]
            }
        }
        return jsonify(response_data), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@publicapi_workflow_bp.route('/workflow/<int:workflow_id>', methods=['PUT'])
@require_api_key
def update_workflow(workflow_id):
    """
    Mettre à jour un workflow existant
    """
    try:
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        workflow = Workflow.query.get(workflow_id)
        if not workflow:
            return jsonify({"error": "Workflow non trouvé"}), 404

        # Seul le créateur peut modifier le workflow
        if workflow.user_id != user.id:
            return jsonify({"error": "Seul le créateur peut modifier le workflow"}), 403

        data = request.get_json()
        
        # Mise à jour du nom si fourni
        if 'name' in data:
            # Vérifier si le nouveau nom existe déjà pour un autre workflow
            existing_workflow = Workflow.query.filter(
                Workflow.name == data['name'],
                Workflow.id != workflow_id
            ).first()
            if existing_workflow:
                return jsonify({"error": f"Un workflow avec le nom '{data['name']}' existe déjà"}), 400
            workflow.name = data['name']
        
        # Mise à jour des utilisateurs si fournis
        if 'users' in data and isinstance(data['users'], list):
            # Vérifier d'abord tous les utilisateurs
            for user_data in data['users']:
                if not all(k in user_data for k in ('user_id', 'priority', 'account_type')):
                    return jsonify({"error": "user_id, priority et account_type sont requis pour chaque utilisateur"}), 400

                # Vérifier les actions
                actions = user_data.get('actions', [])
                if not isinstance(actions, list):
                    return jsonify({"error": "Le champ 'actions' doit être une liste"}), 400

                # Vérifier que toutes les actions sont valides
                invalid_actions = [action for action in actions if action not in WorkflowUser.VALID_ACTIONS]
                if invalid_actions:
                    return jsonify({
                        "error": f"Actions invalides : {', '.join(invalid_actions)}",
                        "valid_actions": WorkflowUser.VALID_ACTIONS
                    }), 400

                # Vérifier si l'utilisateur existe selon son account_type
                if user_data['account_type'] in ['employee', 'individual']:
                    user_check = User.query.get(user_data['user_id'])
                    if not user_check:
                        return jsonify({"error": f"L'utilisateur avec l'ID {user_data['user_id']} n'existe pas"}), 404
                    if user_check.account_type != user_data['account_type']:
                        return jsonify({"error": f"L'utilisateur avec l'ID {user_data['user_id']} n'est pas de type {user_data['account_type']}"}), 400
                elif user_data['account_type'] == 'external':
                    if not Contact.query.get(user_data['user_id']):
                        return jsonify({"error": f"Le contact avec l'ID {user_data['user_id']} n'existe pas"}), 404
                else:
                    return jsonify({"error": f"Type de compte invalide : {user_data['account_type']}. Valeurs acceptées : 'employee', 'individual' ou 'external'"}), 400

            # Supprimer les anciens utilisateurs
            WorkflowUser.query.filter_by(workflow_id=workflow.id).delete()
            
            # Ajouter les nouveaux utilisateurs
            for user_data in data['users']:
                try:
                    workflow_user = WorkflowUser(
                        workflow_id=workflow.id,
                        user_id=user_data['user_id'],
                        priority=user_data['priority'],
                        account_type=user_data['account_type'],
                        actions=user_data.get('actions', [])
                    )
                    db.session.add(workflow_user)
                except ValueError as e:
                    db.session.rollback()
                    return jsonify({"error": str(e)}), 400

        workflow.updated_at = datetime.utcnow()
        db.session.commit()

        # Récupérer les utilisateurs mis à jour pour la réponse
        workflow_users = WorkflowUser.query.filter_by(workflow_id=workflow.id).order_by(WorkflowUser.priority).all()
        
        # Préparer les données des utilisateurs avec leurs détails
        users_data = []
        for wu in workflow_users:
            user_details = {}
            if wu.account_type in ['employee', 'individual']:
                # Récupérer les détails de l'utilisateur interne
                user_info = User.query.get(wu.user_id)
                if user_info:
                    user_details = {
                        "id": user_info.id,
                        "email": user_info.email,
                        "name": user_info.name,
                        "sub_name": user_info.sub_name,
                        "account_type": wu.account_type
                    }
            else:
                # Récupérer les détails du contact externe
                contact_info = Contact.query.get(wu.user_id)
                if contact_info:
                    user_details = {
                        "id": contact_info.id,
                        "email": contact_info.email,
                        "name": contact_info.name,
                        "phone": contact_info.phone,
                        "account_type": "external"
                    }
            
            if user_details:
                user_details.update({
                    "priority": wu.priority,
                    "actions": wu.actions
                })
                users_data.append(user_details)

        return jsonify({
            "message": "Workflow mis à jour avec succès",
            "workflow": {
                "id": workflow.id,
                "name": workflow.name,
                "created_at": workflow.created_at.isoformat(),
                "updated_at": workflow.updated_at.isoformat(),
                "creator": {
                    "id": workflow.user.id,
                    "email": workflow.user.email,
                    "name": workflow.user.name,
                    "sub_name": workflow.user.sub_name
                },
                "users": users_data
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@publicapi_workflow_bp.route('/workflow/<int:workflow_id>', methods=['DELETE'])
@require_api_key
def delete_workflow(workflow_id):
    """
    Supprimer un workflow et ses données associées
    """
    try:
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        workflow = Workflow.query.get(workflow_id)
        if not workflow:
            return jsonify({"error": "Workflow non trouvé"}), 404

        # Seul le créateur peut supprimer le workflow
        if workflow.user_id != user.id:
            return jsonify({"error": "Seul le créateur peut supprimer le workflow"}), 403

        # Supprimer les line_flows associés aux flows du workflow
        flows = Flow.query.filter_by(workflow_id=workflow.id).all()
        for flow in flows:
            LineFlow.query.filter_by(flow_id=flow.id).delete()
        
        # Supprimer les flows
        Flow.query.filter_by(workflow_id=workflow.id).delete()
        
        # Supprimer les utilisateurs du workflow
        WorkflowUser.query.filter_by(workflow_id=workflow.id).delete()
        
        # Supprimer le workflow
        db.session.delete(workflow)
        db.session.commit()

        return jsonify({
            "message": "Workflow et toutes ses données associées supprimés avec succès"
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@publicapi_workflow_bp.route('/user-workflows', methods=['GET'])
@require_api_key
def get_user_workflows():
    """
    Récupérer tous les workflows auxquels l'utilisateur participe.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        # Récupération des paramètres de pagination
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))

        # Récupérer tous les workflows uniques où l'utilisateur participe avec pagination
        query = (
            Workflow.query
            .join(WorkflowUser, Workflow.id == WorkflowUser.workflow_id)
            .filter(WorkflowUser.user_id == user.id)
            .distinct()
            .order_by(Workflow.created_at.desc())
        )
        total_workflows = query.count()
        workflows = query.paginate(page=page, per_page=per_page, error_out=False).items
        
        workflows_data = []
        for workflow in workflows:
            # Récupérer tous les participants du workflow
            participants = WorkflowUser.query.filter_by(workflow_id=workflow.id).order_by(WorkflowUser.priority).all()
            participants_data = []
            
            for participant in participants:
                participant_data = {
                    "id": participant.user_id,
                    "actions": participant.actions,
                    "priority": participant.priority,
                    "account_type": participant.account_type
                }
                
                # Récupérer les informations du participant selon son type de compte
                if participant.account_type in ['employee', 'individual']:
                    user_data = User.query.get(participant.user_id)
                    if user_data:
                        participant_data.update({
                            "email": user_data.email,
                            "name": user_data.name,
                            "sub_name": user_data.sub_name,
                            "phone": user_data.phone
                        })
                elif participant.account_type == 'external':
                    contact_data = Contact.query.get(participant.user_id)
                    if contact_data:
                        participant_data.update({
                            "email": contact_data.email,
                            "name": contact_data.name,
                            "phone": contact_data.phone,
                            "company_name": contact_data.company_name,
                            "address": contact_data.address
                        })
                
                participants_data.append(participant_data)

            workflows_data.append({
                "id": workflow.id,
                "name": workflow.name,
                "created_at": workflow.created_at.isoformat(),
                "creator": {
                    "id": workflow.user_id,
                    "email": workflow.user.email,
                    "name": workflow.user.name,
                    "sub_name": workflow.user.sub_name
                },
                "users": participants_data,
                "flows": [{
                    "id": flow.id,
                    "current_priority": flow.current_priority,
                    "action_done": flow.action_done,
                    "reference": flow.reference,
                    "deadline": flow.deadline.isoformat() if flow.deadline else None,
                    "created_at": flow.created_at.isoformat()
                } for flow in workflow.flows]
            })

        # Calcul des métadonnées de pagination
        total_pages = ceil(total_workflows / per_page)
        metadata = {
            "current_page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_items": total_workflows,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }

        return jsonify({
            "message": "Workflows récupérés avec succès",
            "workflows": workflows_data,
            "metadata": metadata
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@publicapi_workflow_bp.route('/workflows/<int:workflow_id>/launch', methods=['POST'])
@require_api_key
def launch_workflow(workflow_id):
    """
    Lance un workflow existant en créant un nouveau flux.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        # Récupérer le workflow
        workflow = Workflow.query.get(workflow_id)
        if not workflow:
            return jsonify({"error": "Workflow non trouvé"}), 404

        # Vérifier que l'utilisateur a accès au workflow
        workflow_user = WorkflowUser.query.filter_by(
            workflow_id=workflow_id,
            user_id=user.id
        ).first()
        if not workflow_user:
            return jsonify({"error": "Vous n'avez pas accès à ce workflow"}), 403

        # Récupérer le fichier
        file = request.files.get('file')
        if not file:
            return jsonify({"error": "Aucun fichier fourni"}), 400

        # Générer un nom de fichier unique
        unique_filename = f"{uuid.uuid4().hex}.pdf"

        # Déterminer le sous-dossier en fonction du type d'utilisateur
        if user.account_type == "individual":
            subfolder = f"users/{user.email.replace(' ', '_')}"
        elif user.account_type == "employee" and user.company_id:
            company = Company.query.get(user.company_id)
            if not company:
                return jsonify({"error": "Entreprise associée introuvable"}), 404
            subfolder = f"companies/{company.name.replace(' ', '_')}"
        else:
            return jsonify({"error": "Type d'utilisateur invalide"}), 400

        # Créer le dossier si nécessaire
        document_folder = DRAFT_FOLDER / subfolder
        document_folder.mkdir(parents=True, exist_ok=True)

        # Sauvegarder le fichier
        file_path = document_folder / unique_filename
        file.save(file_path)

        # Extraire les métadonnées du PDF
        metadata = extract_pdf_metadata(file_path)

        # Créer le document
        document = Document(
            name=request.form.get('name', f"Flow_{uuid.uuid4().hex[:8]}"),
            description=request.form.get('description', ''),
            file_path=str(file_path),
            status="pending",
            user_id=user.id,
            pdf_metadata=metadata,
            is_workflow=True
        )
        db.session.add(document)
        db.session.flush()

        # Créer le flow
        flow = Flow(
            workflow_id=workflow.id,
            document_id=document.id,
            current_priority=0,  # Initialiser avec la priorité de l'initiateur
            reference=f"FLOW-{uuid.uuid4().hex[:8].upper()}",
            deadline=datetime.strptime(request.form.get('deadline'), '%Y-%m-%d') if request.form.get('deadline') else None
        )
        db.session.add(flow)
        db.session.flush()

        # Récupérer les participants du workflow
        workflow_users = WorkflowUser.query.filter_by(workflow_id=workflow_id).order_by(WorkflowUser.priority).all()

        # Créer les line flows pour chaque participant
        for workflow_user in workflow_users:
            line_flow = LineFlow(
                flow_id=flow.id,
                user_id=workflow_user.user_id,
                priority=workflow_user.priority,
                account_type=workflow_user.account_type,
                actions=workflow_user.actions,
                sign_position=workflow_user.sign_position if hasattr(workflow_user, 'sign_position') else None,
                action_done=False
            )
            db.session.add(line_flow)

        db.session.commit()

        # Récupérer les informations complètes des participants
        participants_info = []
        for workflow_user in workflow_users:
            participant_data = {}
            if workflow_user.account_type == "contact":
                contact = Contact.query.get(workflow_user.user_id)
                if contact:
                    participant_data = {
                        "id": contact.id,
                        "email": contact.email,
                        "name": contact.name,
                        "phone": contact.phone,
                        "company_name": contact.company_name,
                        "address": contact.address,
                        "type": "contact"
                    }
            else:
                user = User.query.get(workflow_user.user_id)
                if user:
                    participant_data = {
                        "id": user.id,
                        "email": user.email,
                        "name": user.name,
                        "sub_name": user.sub_name,
                        "phone": user.phone,
                        "account_type": user.account_type,
                        "type": "user"
                    }
                    if user.company_id:
                        company = Company.query.get(user.company_id)
                        if company:
                            participant_data["company"] = {
                                "id": company.id,
                                "name": company.name
                            }
            
            if participant_data:
                participant_data.update({
                    "priority": workflow_user.priority,
                    "actions": workflow_user.actions,
                    "sign_position": workflow_user.sign_position if hasattr(workflow_user, 'sign_position') else None,
                    "action_done": False
                })
                participants_info.append(participant_data)

        # Générer le lien de téléchargement
        download_link = url_for(
            'document_bp.download_file',
            subfolder=subfolder,
            filename=unique_filename,
            _external=True
        )

        return jsonify({
            "message": "Workflow lancé avec succès",
            "workflow": {
                "id": workflow.id,
                "name": workflow.name,
                "created_at": workflow.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                "creator": {
                    "id": workflow.user_id,
                    "email": workflow.user.email,
                    "name": workflow.user.name
                }
            },
            "flow": {
                "id": flow.id,
                "reference": flow.reference,
                "created_at": flow.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                "deadline": flow.deadline.strftime('%Y-%m-%d') if flow.deadline else None,
                "document": {
                    "id": document.id,
                    "name": document.name,
                    "description": document.description,
                    "status": document.status,
                    "file_path": document.file_path,
                    "download_link": download_link,
                    "metadata": document.pdf_metadata,
                    "created_at": document.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    "updated_at": document.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                },
                "participants": participants_info
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors du lancement du workflow: {str(e)}")
        return jsonify({"error": f"Une erreur est survenue: {str(e)}"}), 500

def extract_pdf_metadata(file_path):
    """
    Extrait les métadonnées enrichies d'un fichier PDF.
    """
    try:
        reader = PdfReader(file_path)
        file_size = os.path.getsize(file_path)

        metadata = {
            "file_name": os.path.basename(file_path),
            "file_size_bytes": file_size,
            "file_size_human": human_readable_size(file_size),
            "pdf_version": reader.pdf_header,
            "page_count": len(reader.pages),
            "title": str(reader.metadata.get("/Title", "N/A")),
            "author": str(reader.metadata.get("/Author", "N/A")),
            "producer": str(reader.metadata.get("/Producer", "N/A")),
            "creation_date": str(reader.metadata.get("/CreationDate", "N/A")),
            "modification_date": str(reader.metadata.get("/ModDate", "N/A")),
            "font_info": set(),
            "outline": [],
            "dimensions": [],
            "orientations": [],
        }

        # Parcourir les pages pour extraire des informations
        for page in reader.pages:
            media_box = page.mediabox
            width = float(media_box[2] - media_box[0])
            height = float(media_box[3] - media_box[1])
            orientation = "Landscape" if width > height else "Portrait"

            metadata["dimensions"].append({"width": width, "height": height})
            metadata["orientations"].append(orientation)

            # Gestion sécurisée des polices
            try:
                resources = page.get("/Resources", {})
                if isinstance(resources, dict) and "/Font" in resources:
                    fonts = resources["/Font"]
                    if hasattr(fonts, "keys"):
                        metadata["font_info"].update(str(key) for key in fonts.keys())
            except Exception as font_error:
                logging.warning(f"Erreur lors de l'extraction des polices : {str(font_error)}")

        # Convertir font_info (set) en liste et autres conversions pour JSON
        metadata["font_info"] = list(metadata["font_info"])
        metadata = convert_to_json_compatible(metadata)

        return metadata
    except Exception as e:
        logging.error(f"Erreur lors de l'extraction des métadonnées : {str(e)}")
        return {"error": f"Impossible d'extraire les métadonnées : {str(e)}"}

def convert_to_json_compatible(data):
    """
    Convertit les objets incompatibles JSON en types compatibles (par exemple, Decimal en float, MetaData en dict).
    """
    if isinstance(data, Decimal):
        return float(data)
    elif isinstance(data, dict):
        return {key: convert_to_json_compatible(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_to_json_compatible(item) for item in data]
    elif isinstance(data, set):
        return list(data)  # Convertir un set en liste
    elif isinstance(data, NameObject) or isinstance(data, TextStringObject) or isinstance(data, NumberObject):
        return str(data)  # Convertir les objets spécifiques PyPDF2 en chaîne
    elif hasattr(data, "keys") and hasattr(data, "items"):  # MetaData ou objets similaires
        return {str(key): convert_to_json_compatible(value) for key, value in data.items()}
    return data

def human_readable_size(size):
    """
    Convertit la taille en octets en une taille lisible (Ko, Mo, Go).
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"