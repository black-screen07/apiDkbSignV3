-- Migration pour supprimer les contraintes d'unicité sur la table contacts
-- Permet à un même email d'appartenir à plusieurs utilisateurs ou entreprises

-- Supprimer la contrainte unique_email_per_user
ALTER TABLE contacts DROP INDEX IF EXISTS unique_email_per_user;

-- Supprimer la contrainte unique_email_per_company  
ALTER TABLE contacts DROP INDEX IF EXISTS unique_email_per_company;

-- Vérifier que les contraintes ont été supprimées
SHOW INDEX FROM contacts WHERE Key_name IN ('unique_email_per_user', 'unique_email_per_company');
