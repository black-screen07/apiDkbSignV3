from flask import Blueprint, jsonify, url_for, request
from app.utils.api_auth_utils import require_api_key, get_authenticated_user_by_api_key
from app.models import db, Flow, LineFlow, User, Contact, Company, Document, Workflow
from datetime import datetime
import os
from sqlalchemy import or_, desc, asc

publicapi_flow_bp = Blueprint('publicapi_flow_bp', __name__)

@publicapi_flow_bp.route('/flows/<int:flow_id>', methods=['GET'])
@require_api_key
def get_flow(flow_id):
    """
    Récupère les détails complets d'un flow avec ses participants et le document associé.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        # Récupérer le flow avec ses relations
        flow = Flow.query.get(flow_id)
        if not flow:
            return jsonify({"error": "Flow non trouvé"}), 404

        # Récupérer le workflow associé
        workflow = Workflow.query.get(flow.workflow_id)
        if not workflow:
            return jsonify({"error": "Workflow associé non trouvé"}), 404

        # Récupérer le document associé au flow
        document = Document.query.filter_by(id=flow.document_id).first()
        if not document:
            return jsonify({"error": "Document associé non trouvé"}), 404

        # Récupérer les line flows et les informations des participants
        line_flows = LineFlow.query.filter_by(flow_id=flow_id).order_by(LineFlow.priority).all()
        participants_info = []

        for line_flow in line_flows:
            participant_data = {}
            if line_flow.account_type == "contact":
                contact = Contact.query.get(line_flow.user_id)
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
                participant = User.query.get(line_flow.user_id)
                if participant:
                    participant_data = {
                        "id": participant.id,
                        "email": participant.email,
                        "name": participant.name,
                        "sub_name": participant.sub_name,
                        "phone": participant.phone,
                        "account_type": participant.account_type,
                        "type": "user"
                    }
                    if participant.company_id:
                        company = Company.query.get(participant.company_id)
                        if company:
                            participant_data["company"] = {
                                "id": company.id,
                                "name": company.name
                            }
            
            if participant_data:
                participant_data.update({
                    "priority": line_flow.priority,
                    "actions": line_flow.actions,
                    "sign_position": line_flow.sign_position,
                    "action_done": line_flow.action_done,
                    "status": line_flow.status,
                    "denial_reason": line_flow.denial_reason,
                    "denial_date": line_flow.denial_date.strftime('%Y-%m-%d %H:%M:%S') if line_flow.denial_date else None
                })
                participants_info.append(participant_data)

        # Déterminer le sous-dossier pour le lien de téléchargement
        if document.user.account_type == "individual":
            subfolder = f"users/{document.user.email.replace(' ', '_')}"
        else:
            company = Company.query.get(document.user.company_id)
            if company:
                subfolder = f"companies/{company.name.replace(' ', '_')}"
            else:
                subfolder = "unknown"

        # Vérifier si au moins une action est terminée
        has_signed_actions = any(lf.action_done for lf in line_flows)
        
        # Générer le lien de téléchargement
        filename = os.path.basename(document.file_path)
        download_link = url_for(
            'flow_signature_bp.download_file' if has_signed_actions else 'document_bp.download_file',
            subfolder=subfolder,
            filename=filename,
            _external=True
        )

        return jsonify({
            "workflow": {
                "id": workflow.id,
                "name": workflow.name,
                "created_at": workflow.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                "updated_at": workflow.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                "creator": {
                    "id": workflow.user_id,
                    "email": workflow.user.email,
                    "name": workflow.user.name
                }
            },
            "flow": {
                "id": flow.id,
                "reference": flow.reference,
                "status": flow.status,
                "current_priority": flow.current_priority,
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
        }), 200

    except Exception as e:
        return jsonify({"error": f"Une erreur est survenue: {str(e)}"}), 500

@publicapi_flow_bp.route('/flows', methods=['GET'])
@require_api_key
def get_participant_flows():
    """
    Liste tous les flows où l'utilisateur connecté est participant.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_authenticated_user_by_api_key().email
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404

        # Paramètres de pagination et de tri
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc')
        search_query = request.args.get('search', '')

        # Construire la requête de base
        query = LineFlow.query.filter_by(user_id=user.id)

        # Appliquer la recherche si un terme est fourni
        if search_query:
            query = query.join(Flow).join(Document).filter(
                or_(
                    Document.name.ilike(f'%{search_query}%'),
                    Flow.reference.ilike(f'%{search_query}%')
                )
            )

        # Appliquer le tri
        if sort_by == 'created_at':
            sort_column = Flow.created_at
        elif sort_by == 'deadline':
            sort_column = Flow.deadline
        elif sort_by == 'document_name':
            sort_column = Document.name
        else:
            sort_column = Flow.created_at

        if sort_order == 'desc':
            query = query.join(Flow).order_by(desc(sort_column))
        else:
            query = query.join(Flow).order_by(asc(sort_column))

        # Exécuter la requête avec pagination
        paginated_line_flows = query.paginate(page=page, per_page=per_page, error_out=False)
        total_items = paginated_line_flows.total

        flows_data = []
        for line_flow in paginated_line_flows.items:
            flow = Flow.query.get(line_flow.flow_id)
            if not flow:
                continue

            # Récupérer le document associé
            document = Document.query.get(flow.document_id)
            if not document:
                continue

            # Récupérer le workflow associé
            workflow = Workflow.query.get(flow.workflow_id)
            if not workflow:
                continue

            # Récupérer l'initiateur du flow (priority=0)
            initiator_line = LineFlow.query.filter_by(flow_id=flow.id, priority=0).first()
            initiator = None
            if initiator_line:
                initiator = User.query.get(initiator_line.user_id)

            # Déterminer le sous-dossier pour le lien de téléchargement
            if initiator and initiator.account_type == "employee" and initiator.company_id:
                company = Company.query.get(initiator.company_id)
                subfolder = f"companies/{company.name.replace(' ', '_')}" if company else "unknown"
            else:
                subfolder = f"users/{initiator.email}" if initiator else "unknown"

            # Vérifier si au moins une action est terminée
            all_line_flows = LineFlow.query.filter_by(flow_id=flow.id).all()
            has_signed_actions = any(lf.action_done for lf in all_line_flows)

            # Générer le lien de téléchargement
            filename = os.path.basename(document.file_path)
            download_link = url_for(
                'flow_signature_bp.download_file' if has_signed_actions else 'document_bp.download_file',
                subfolder=subfolder,
                filename=filename,
                _external=True
            )

            # Récupérer tous les participants du flow
            all_line_flows = LineFlow.query.filter_by(flow_id=flow.id).order_by(LineFlow.priority).all()
            participants_info = []

            for participant_line in all_line_flows:
                participant_data = {}
                if participant_line.account_type == "contact":
                    contact = Contact.query.get(participant_line.user_id)
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
                    participant = User.query.get(participant_line.user_id)
                    if participant:
                        participant_data = {
                            "id": participant.id,
                            "email": participant.email,
                            "name": participant.name,
                            "sub_name": participant.sub_name,
                            "phone": participant.phone,
                            "account_type": participant.account_type,
                            "type": "user"
                        }
                        if participant.company_id:
                            company = Company.query.get(participant.company_id)
                            if company:
                                participant_data["company"] = {
                                    "id": company.id,
                                    "name": company.name
                                }
                
                if participant_data:
                    participant_data.update({
                        "priority": participant_line.priority,
                        "actions": participant_line.actions,
                        "sign_position": participant_line.sign_position,
                        "action_done": participant_line.action_done,
                        "verified_read_aprob": participant_line.verified_read_aprob,
                        "status": participant_line.status,
                        "denial_reason": participant_line.denial_reason,
                        "denial_date": participant_line.denial_date.strftime('%Y-%m-%d %H:%M:%S') if participant_line.denial_date else None
                    })
                    participants_info.append(participant_data)

            # Construire les données du flow
            flow_data = {
                "id": flow.id,
                "reference": flow.reference,
                "status": flow.status,
                "action_done": flow.action_done,
                "current_priority": flow.current_priority,
                "deadline": flow.deadline.strftime('%Y-%m-%d') if flow.deadline else None,
                "created_at": flow.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                "workflow": {
                    "id": workflow.id,
                    "name": workflow.name,
                    "created_at": workflow.created_at.strftime('%Y-%m-%d %H:%M:%S')
                },
                "document": {
                    "id": document.id,
                    "name": document.name,
                    "description": document.description,
                    "status": document.status,
                    "download_link": download_link,
                    "created_at": document.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    "updated_at": document.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                },
                "initiator": {
                    "id": initiator.id,
                    "email": initiator.email,
                    "name": initiator.name,
                    "account_type": initiator.account_type
                } if initiator else None,
                "current_participant_info": {
                    "priority": line_flow.priority,
                    "actions": line_flow.actions,
                    "sign_position": line_flow.sign_position,
                    "action_done": line_flow.action_done,
                    "verified_read_aprob": line_flow.verified_read_aprob
                },
                "participants": participants_info
            }

            flows_data.append(flow_data)

        # Calculer les métadonnées de pagination
        total_pages = (total_items + per_page - 1) // per_page
        has_next = page < total_pages
        has_prev = page > 1

        metadata = {
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "per_page": per_page,
            "has_next": has_next,
            "has_prev": has_prev,
            "next_page": page + 1 if has_next else None,
            "prev_page": page - 1 if has_prev else None
        }

        return jsonify({
            "metadata": metadata,
            "flows": flows_data
        }), 200

    except Exception as e:
        return jsonify({"error": f"Une erreur est survenue: {str(e)}"}), 500
