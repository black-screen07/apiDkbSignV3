from flask import Blueprint, request, jsonify, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_sqlalchemy import SQLAlchemy
import logging
from datetime import datetime
from pathlib import Path
from app.models import db, User, Company, Contact
from werkzeug.utils import secure_filename
from sqlalchemy import or_

contact_bp = Blueprint('contact_bp', __name__)


@contact_bp.route('/contacts', methods=['POST'])
@jwt_required()
def create_contact():
    """
    Crée un nouveau contact pour l'utilisateur connecté.
    Si l'utilisateur est un employé, le contact est synchronisé avec l'entreprise.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Récupérer les données de la requête
        data = request.json
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        address = data.get('address')
        company_name = data.get('company_name')
        notes = data.get('notes')

        if not name or not email:
            return jsonify({"error": "Les champs 'name' et 'email' sont obligatoires."}), 400

        # Vérifier si c'est un employé ou un compte individuel
        company_id = None
        if user.account_type == 'employee':
            if not user.company_id:
                return jsonify({"error": "Aucune entreprise associée à cet employé."}), 400
            company_id = user.company_id

        # Vérifier si l'email existe déjà POUR CE CONTEXTE SPÉCIFIQUE
        # Un même email peut exister pour différents utilisateurs/entreprises
        if company_id:
            # Pour un employé : vérifier uniquement dans les contacts de l'entreprise
            existing_contact = Contact.query.filter(
                Contact.email == email,
                Contact.company_id == company_id
            ).first()
        else:
            # Pour un utilisateur individuel : vérifier uniquement dans ses contacts personnels
            existing_contact = Contact.query.filter(
                Contact.email == email,
                Contact.user_id == user.id
            ).first()

        if existing_contact:
            return jsonify({"error": "Ce contact existe déjà dans votre liste."}), 400

        # Créer le contact avec account_type 'external' car c'est un contact simple
        new_contact = Contact(
            user_id=user.id if not company_id else None,
            company_id=company_id,
            name=name,
            email=email,
            phone=phone,
            address=address,
            company_name=company_name,
            notes=notes,
            account_type='external'  # Contact simple sans compte sur l'application
        )
        db.session.add(new_contact)
        db.session.commit()

        return jsonify({
            "message": "Contact créé avec succès.",
            "contact": {
                "id": new_contact.id,
                "user_id": new_contact.user_id,
                "company_id": new_contact.company_id,
                "name": new_contact.name,
                "email": new_contact.email,
                "phone": new_contact.phone,
                "address": new_contact.address,
                "company_name": new_contact.company_name,
                "notes": new_contact.notes,
                "account_type": new_contact.account_type,
                "created_at": new_contact.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        }), 201

    except Exception as e:
        logging.error(f"Erreur lors de la création du contact : {str(e)}")
        return jsonify({"error": f"Erreur lors de la création du contact : {str(e)}"}), 500


@contact_bp.route('/contacts', methods=['GET'])
@jwt_required()
def get_contacts():
    """
    Récupère tous les contacts pour l'utilisateur connecté avec recherche et pagination.
    Inclut les contacts synchronisés avec l'entreprise pour les employés.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Paramètres de recherche et de pagination
        search_query = request.args.get('search', '').strip()  # Recherche globale (nom, email, téléphone)
        page = int(request.args.get('page', 1))  # Numéro de la page
        per_page = int(request.args.get('per_page', 10))  # Nombre de contacts par page

        # Construction de la requête de base pour les contacts
        base_query = Contact.query.filter(
            or_(
                Contact.user_id == user.id,  # Contacts personnels
                (user.account_type == 'employee' and Contact.company_id == user.company_id)  # Contacts d'entreprise
            )
        )

        # Liste pour stocker tous les contacts (incluant les contacts virtuels)
        all_contacts = list(base_query.all())

        # Si l'utilisateur est un employé, ajouter ses collègues à la liste des contacts
        if user.account_type == 'employee' and user.company_id:
            colleagues = User.query.filter(
                User.company_id == user.company_id,
                User.id != user.id,
                User.account_type == 'employee'
            ).all()

            # Ajouter les collègues comme contacts virtuels
            for colleague in colleagues:
                virtual_contact = Contact(
                    id=colleague.id,  # Utiliser l'ID du collègue
                    user_id=None,
                    company_id=user.company_id,
                    name=f"{colleague.name} {colleague.sub_name}",
                    email=colleague.email,
                    phone=colleague.phone,
                    address=colleague.address,
                    company_name=user.company.name if user.company else None,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                # Stocker l'account_type du collègue et son ID utilisateur
                setattr(virtual_contact, 'account_type', colleague.account_type)
                setattr(virtual_contact, 'is_from_user', True)  # Marquer comme provenant de la table User
                setattr(virtual_contact, 'user_account_id', colleague.id)  # Ajouter l'ID du compte utilisateur
                all_contacts.append(virtual_contact)

        # Filtrer les contacts si une recherche est demandée
        if search_query:
            all_contacts = [
                contact for contact in all_contacts
                if search_query.lower() in contact.name.lower() or
                   search_query.lower() in contact.email.lower() or
                   (contact.phone and search_query.lower() in contact.phone.lower())
            ]

        # Pagination manuelle
        total_contacts = len(all_contacts)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_contacts = all_contacts[start_idx:end_idx]

        # Construction de la réponse
        contacts_data = [
            {
                "id": contact.id if hasattr(contact, 'id') else None,
                #"user_id": contact.user_id,
                "company_id": contact.company_id,
                "name": contact.name,
                "email": contact.email,
                "phone": contact.phone,
                "address": contact.address,
                "company_name": contact.company_name,
                "notes": contact.notes if hasattr(contact, 'notes') else None,
                "user_account_id": contact.user_account_id if hasattr(contact, 'user_account_id') else None,
                "created_at": contact.created_at.strftime('%Y-%m-%d %H:%M:%S') if contact.created_at else None,
                "updated_at": contact.updated_at.strftime('%Y-%m-%d %H:%M:%S') if contact.updated_at else None,
                "is_colleague": hasattr(contact, 'is_from_user'),  # True seulement pour les contacts de la table User
                "account_type": getattr(contact, 'account_type', 'external')  # Utilise account_type si disponible, sinon 'external'
            }
            for contact in paginated_contacts
        ]

        return jsonify({
            "contacts": contacts_data,
            "total": total_contacts,
            "pages": (total_contacts + per_page - 1) // per_page,
            "current_page": page,
            "per_page": per_page
        }), 200

    except Exception as e:
        logging.error(f"Erreur lors de la récupération des contacts : {str(e)}")
        return jsonify({"error": f"Erreur lors de la récupération des contacts : {str(e)}"}), 500


@contact_bp.route('/contacts/<int:id>', methods=['GET'])
@jwt_required()
def get_contact(id):
    """
    Récupère un contact spécifique appartenant à l'utilisateur connecté ou synchronisé avec son entreprise.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Vérifier l'appartenance du contact
        contact = Contact.query.filter(
            Contact.id == id,
            or_(
                Contact.user_id == user.id,
                Contact.company_id == user.company_id
            )
        ).first()

        if not contact:
            return jsonify({"error": "Contact introuvable ou non autorisé."}), 404

        # Retourner les détails du contact
        return jsonify({
            "id": contact.id,
            "user_id": contact.user_id,
            "company_id": contact.company_id,
            "name": contact.name,
            "email": contact.email,
            "phone": contact.phone,
            "address": contact.address,
            "company_name": contact.company_name,
            "notes": contact.notes,
            "account_type": contact.account_type,
            "user_account_id": contact.user_account_id,
            "created_at": contact.created_at.strftime('%Y-%m-%d %H:%M:%S') if contact.created_at else None,
            "updated_at": contact.updated_at.strftime('%Y-%m-%d %H:%M:%S') if contact.updated_at else None
        }), 200

    except Exception as e:
        logging.error(f"Erreur lors de la récupération du contact : {str(e)}")
        return jsonify({"error": f"Erreur lors de la récupération du contact : {str(e)}"}), 500


@contact_bp.route('/contacts/<int:id>', methods=['PUT'])
@jwt_required()
def update_contact(id):
    """
    Met à jour un contact existant appartenant à l'utilisateur connecté ou synchronisé avec son entreprise.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Récupérer le contact
        contact = Contact.query.filter(
            Contact.id == id,
            or_(
                Contact.user_id == user.id,
                Contact.company_id == user.company_id
            )
        ).first()

        if not contact:
            return jsonify({"error": "Contact introuvable ou non autorisé."}), 404

        # Mettre à jour les champs
        data = request.json
        contact.name = data.get('name', contact.name)
        contact.email = data.get('email', contact.email)
        contact.phone = data.get('phone', contact.phone)
        contact.address = data.get('address', contact.address)
        contact.company_name = data.get('company_name', contact.company_name)
        contact.notes = data.get('notes', contact.notes)

        db.session.commit()

        return jsonify({"message": "Contact mis à jour avec succès."}), 200

    except Exception as e:
        logging.error(f"Erreur lors de la mise à jour du contact : {str(e)}")
        return jsonify({"error": f"Erreur lors de la mise à jour du contact : {str(e)}"}), 500


@contact_bp.route('/contacts/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_contact(id):
    """
    Supprime un contact appartenant à l'utilisateur connecté ou synchronisé avec son entreprise.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"error": "Utilisateur introuvable."}), 404

        # Vérifier l'appartenance du contact
        contact = Contact.query.filter(
            Contact.id == id,
            or_(
                Contact.user_id == user.id,
                Contact.company_id == user.company_id
            )
        ).first()

        if not contact:
            return jsonify({"error": "Contact introuvable ou non autorisé."}), 404

        # Supprimer le contact
        db.session.delete(contact)
        db.session.commit()

        return jsonify({"message": "Contact supprimé avec succès."}), 200

    except Exception as e:
        logging.error(f"Erreur lors de la suppression du contact : {str(e)}")
        return jsonify({"error": f"Erreur lors de la suppression du contact : {str(e)}"}), 500


@contact_bp.route('/add-user-contact/<int:user_id>', methods=['POST'])
@jwt_required()
def add_user_contact(user_id):
    """
    Ajoute un utilisateur comme contact.
    """
    try:
        # Récupérer l'utilisateur connecté
        current_user_email = get_jwt_identity()
        current_user = User.query.filter_by(email=current_user_email).first()

        if not current_user:
            return jsonify({"error": "Utilisateur connecté introuvable."}), 404

        # Récupérer l'utilisateur à ajouter comme contact
        user_to_add = User.query.get(user_id)
        if not user_to_add:
            return jsonify({"error": "Utilisateur à ajouter introuvable."}), 404

        # Vérifier si le contact existe déjà POUR CE CONTEXTE SPÉCIFIQUE
        company_id = current_user.company_id if current_user.account_type == 'employee' else None
        
        if company_id:
            # Pour un employé : vérifier dans les contacts de l'entreprise
            existing_contact = Contact.query.filter(
                Contact.email == user_to_add.email,
                Contact.company_id == company_id
            ).first()
        else:
            # Pour un utilisateur individuel : vérifier dans ses contacts personnels
            existing_contact = Contact.query.filter(
                Contact.email == user_to_add.email,
                Contact.user_id == current_user.id
            ).first()

        if existing_contact:
            return jsonify({"error": "Cet utilisateur est déjà dans vos contacts."}), 400

        # Créer le contact avec le bon account_type
        company_id = current_user.company_id if current_user.account_type == 'employee' else None
        new_contact = Contact(
            user_id=current_user.id if not company_id else None,
            company_id=company_id,
            email=user_to_add.email,
            name=f"{user_to_add.name} {user_to_add.sub_name}",
            user_account_id=user_to_add.id,
            phone=user_to_add.phone,
            address=user_to_add.address,
            company_name=user_to_add.company.name if user_to_add.company else None,
            notes=f"Contact ajouté depuis la liste des utilisateurs",
            account_type=user_to_add.account_type  # Utiliser le type de compte de l'utilisateur ajouté
        )

        db.session.add(new_contact)
        db.session.commit()

        return jsonify({
            "message": "Contact ajouté avec succès.",
            "contact": {
                "id": new_contact.id,
                "name": new_contact.name,
                "email": new_contact.email,
                "phone": new_contact.phone,
                "address": new_contact.address,
                "company_name": new_contact.company_name,
                "notes": new_contact.notes,
                "account_type": new_contact.account_type,
                "user_account_id": new_contact.user_account_id,
                "created_at": new_contact.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        logging.error(f"Erreur lors de l'ajout du contact utilisateur : {str(e)}")
        return jsonify({"error": f"Erreur lors de l'ajout du contact : {str(e)}"}), 500


@contact_bp.route('/check-email', methods=['GET'])
def check_email():
    """
    Vérifie si un email existe dans la table des utilisateurs.
    """
    email = request.args.get('email')  # Récupérer l'email depuis les paramètres de requête
    logging.info(f"Vérification de l'email : {email}")  # Journaliser l'email reçu
    try:
        if not email:
            return jsonify({
                "exists": False,
                "message": "Aucun email fourni."
            }), 400
        user = User.query.filter_by(email=email).first()
        if user:
            return jsonify({
                "exists": True,
                "id": user.id,
                "message": "L'email existe déjà."
            }), 200
        else:
            return jsonify({
                "exists": False,
                "message": "L'email n'existe pas."
            }), 200
    except Exception as e:
        logging.error(f"Erreur lors de la vérification de l'email : {str(e)}")
        return jsonify({
            "error": f"Une erreur est survenue lors de la vérification : {str(e)}"
        }), 500