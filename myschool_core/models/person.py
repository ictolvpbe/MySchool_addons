# models/person.py
# -*- coding: utf-8 -*-
"""
Person Model for Odoo 19
========================

Person represents individuals in the myschool system including employees,
students, guardians, etc.

Includes Odoo User/Employee integration for automatic account creation.

For this model, the hr module needs to be installed and required in manifest.py

{
    'name': 'MySchool',
    'depends': [
        'base',
        'hr',  # Voeg toe voor HR Employee integratie
    ],
}

"""

from odoo import models, fields, api
import json
import logging

_logger = logging.getLogger(__name__)


class Person(models.Model):
    """
    Person model.
    
    Represents any person in the myschool system - employees, students,
    guardians, etc. The person_type_id field determines the type.
    
    Includes integration with Odoo's res.users and hr.employee for
    automatic account and HR record management.
    """
    _name = 'myschool.person'
    _description = 'Persoon'
    _rec_name = 'name'
    _order = 'name'

    # =========================================================================
    # Name Fields
    # =========================================================================
    
    name = fields.Char(
        string='Naam', 
        size=100,
        index=True,
        help='Volledige naam (Achternaam, Voornaam)'
    )
    first_name = fields.Char(
        string='Voornaam',
        help='Voornaam van de persoon'
    )
    short_name = fields.Char(
        string='Roepnaam',
        help='Informele naam / roepnaam'
    )
    abbreviation = fields.Char(
        string='Initialen/Afkorting', 
        help='Enkel voor personeel'
    )

    # =========================================================================
    # Unique References
    # =========================================================================
    
    sap_ref = fields.Char(
        string='SAP Referentie (pPersoon)', 
        size=10,
        index=True,
        help='Unieke referentie uit SAP/Informat systeem'
    )
    sap_person_uuid = fields.Char(
        string='SAP Persoon UUID', 
        size=40,
        index=True,
        help='UUID van de persoon in SAP/Informat'
    )
    stam_boek_nr = fields.Char(
        string='Stamboeknummer', 
        size=20,
        help='Stamboeknummer (voor personeel)'
    )

    # =========================================================================
    # Person Type
    # =========================================================================
    
    person_type_id = fields.Many2one(
        'myschool.person.type', 
        string='Type Persoon', 
        ondelete='set null', 
        tracking=True,
        index=True,
        help='Type persoon: EMPLOYEE, STUDENT, GUARDIAN, etc.'
    )

    # =========================================================================
    # Basic Information
    # =========================================================================
    
    gender = fields.Char(
        string='Geslacht', 
        size=5,
        help='M/V/X'
    )
    insz = fields.Char(
        string='Rijksregisternummer (INSZ)', 
        size=20,
        help='Belgisch rijksregisternummer'
    )
    birth_date = fields.Datetime(
        string='Geboortedatum'
    )

    # =========================================================================
    # Registration Data (for students)
    # =========================================================================
    
    reg_start_date = fields.Char(
        string='Registratie Startdatum', 
        size=50,
        help='Startdatum van inschrijving'
    )
    reg_end_date = fields.Char(
        string='Registratie Einddatum', 
        size=50,
        help='Einddatum van inschrijving'
    )
    reg_inst_nr = fields.Char(
        string='Instellingsnummer', 
        size=10,
        help='Instellingsnummer waar persoon geregistreerd is'
    )
    reg_group_code = fields.Char(
        string='Klascode', 
        size=10,
        help='Code van de klas (voor leerlingen)'
    )

    # =========================================================================
    # Account Information
    # =========================================================================
    
    email_cloud = fields.Char(
        string='E-mail Cloud',
        help='School/werk e-mailadres'
    )
    email_private = fields.Char(
        string='E-mail privé',
        help='Privé e-mailadres'
    )
    password = fields.Char(
        string='Wachtwoord', 
        help='Enkel voor kinderen lagere school', 
        groups='base.group_system'
    )

    # =========================================================================
    # Person Details (One2many)
    # =========================================================================
    
    person_details_set = fields.One2many(
        'myschool.person.details',
        'person_id',
        string='Persoonsdetails',
        help='Gedetailleerde gegevens per instelling'
    )

    # =========================================================================
    # Status Fields
    # =========================================================================
    
    is_active = fields.Boolean(
        string='Is Actief', 
        default=True, 
        tracking=True,
        index=True,
        help='Geeft aan of de persoon actief is in het systeem'
    )
    automatic_sync = fields.Boolean(
        string='Auto Sync', 
        default=True, 
        required=True,
        help='Automatisch synchroniseren met externe systemen'
    )

    # =========================================================================
    # ODOO USER/EMPLOYEE INTEGRATION FIELDS
    # =========================================================================
    
    odoo_user_id = fields.Many2one(
        'res.users', 
        string='Odoo User',
        ondelete='set null',
        index=True,
        help='Gekoppelde Odoo gebruikersaccount voor deze persoon'
    )
    
    odoo_employee_id = fields.Many2one(
        'hr.employee',
        string='Odoo Employee',
        ondelete='set null',
        index=True,
        help='Gekoppeld Odoo HR medewerker record'
    )
    
    has_odoo_account = fields.Boolean(
        string='Heeft Odoo Account',
        compute='_compute_has_odoo_account',
        store=True,
        help='Geeft aan of deze persoon een Odoo gebruikersaccount heeft'
    )

    # =========================================================================
    # SQL Constraints
    # =========================================================================
    
    _sql_constraints = [
        ('sap_ref_unique', 'unique(sap_ref)', 'De SAP Referentie moet uniek zijn!'),
        ('sap_uuid_unique', 'unique(sap_person_uuid)', 'De SAP Persoon UUID moet uniek zijn!'),
    ]

    # =========================================================================
    # Computed Fields
    # =========================================================================
    
    @api.depends('odoo_user_id')
    def _compute_has_odoo_account(self):
        """Compute whether person has an Odoo account."""
        for record in self:
            record.has_odoo_account = bool(record.odoo_user_id)

    # =========================================================================
    # Odoo Integration Actions
    # =========================================================================
    
    def action_create_odoo_user(self):
        """
        Manual action to create Odoo user for this person.
        Can be called from a button in the form view.
        """
        self.ensure_one()
        
        if self.odoo_user_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': f'Persoon {self.name} heeft al een Odoo gebruikersaccount.',
                    'type': 'info',
                }
            }
        
        # Create ODOO-PERSON-ADD task
        BeTask = self.env['myschool.betask']
        BeTaskType = self.env['myschool.betask.type']
        
        task_type = BeTaskType.search([
            ('target', '=', 'ODOO'),
            ('object', '=', 'PERSON'),
            ('action', '=', 'ADD')
        ], limit=1)
        
        if not task_type:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Fout',
                    'message': 'BeTaskType ODOO-PERSON-ADD niet gevonden. Maak deze eerst aan.',
                    'type': 'danger',
                }
            }
        
        task_data = {
            'person_id': self.id,
            'personId': self.sap_person_uuid,
            'name': self.name,
            'first_name': self.first_name or '',
            'email': self.email_cloud or self.email_private,
        }
        
        BeTask.create({
            'name': f'ODOO-PERSON-ADD-{self.name}',
            'betasktype_id': task_type.id,
            'status': 'new',
            'data': json.dumps(task_data),
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Succes',
                'message': f'Taak aangemaakt om Odoo gebruiker te maken voor {self.name}.',
                'type': 'success',
            }
        }
    
    def action_view_odoo_user(self):
        """Action to view the linked Odoo user."""
        self.ensure_one()
        
        if not self.odoo_user_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': f'Geen Odoo gebruiker gekoppeld aan {self.name}.',
                    'type': 'info',
                }
            }
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Odoo Gebruiker',
            'res_model': 'res.users',
            'res_id': self.odoo_user_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_odoo_employee(self):
        """Action to view the linked HR employee."""
        self.ensure_one()
        
        if not self.odoo_employee_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': f'Geen HR Medewerker gekoppeld aan {self.name}.',
                    'type': 'info',
                }
            }
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'HR Medewerker',
            'res_model': 'hr.employee',
            'res_id': self.odoo_employee_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_sync_group_memberships(self):
        """
        Manual action to sync Odoo group memberships based on roles.
        """
        self.ensure_one()
        
        if not self.odoo_user_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': f'Persoon {self.name} heeft geen Odoo gebruikersaccount.',
                    'type': 'info',
                }
            }
        
        # Call the processor method
        processor = self.env['myschool.betask.processor']
        processor._sync_person_group_memberships(self)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Succes',
                'message': f'Groepslidmaatschappen gesynchroniseerd voor {self.name}.',
                'type': 'success',
            }
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def get_display_name(self):
        """Get formatted display name."""
        self.ensure_one()
        if self.first_name:
            return f"{self.first_name} {self.name.split(',')[0].strip() if ',' in self.name else self.name}"
        return self.name
    
    def is_employee(self):
        """Check if this person is an employee."""
        self.ensure_one()
        return self.person_type_id and self.person_type_id.name == 'EMPLOYEE'
    
    def is_student(self):
        """Check if this person is a student."""
        self.ensure_one()
        return self.person_type_id and self.person_type_id.name == 'STUDENT'

    # =========================================================================
    # Deactivation Logic
    # =========================================================================

    def write(self, vals):
        """
        Override write to handle deactivation cascading.

        When is_active is set to False for an employee:
        - Deactivate linked Odoo user
        - Deactivate linked HR employee
        - Deactivate all proprelations
        """
        # Check if we're deactivating
        if 'is_active' in vals and vals['is_active'] is False:
            for record in self:
                if record.is_active:  # Was active, now being deactivated
                    record._on_deactivate()

        return super().write(vals)

    def _on_deactivate(self):
        """
        Handle person deactivation - cascade to related records.

        This method is called when a person is being deactivated.
        It deactivates:
        - Linked Odoo user (res.users)
        - Linked HR employee (hr.employee)
        - All proprelations where this person is involved
        """
        self.ensure_one()
        _logger.info(f'Deactivating person: {self.name} (ID: {self.id})')

        changes = []

        # Deactivate Odoo user
        if self.odoo_user_id:
            try:
                self.odoo_user_id.write({'active': False})
                changes.append(f'Odoo user {self.odoo_user_id.login} deactivated')
                _logger.info(f'Deactivated Odoo user: {self.odoo_user_id.login}')
            except Exception as e:
                _logger.error(f'Failed to deactivate Odoo user: {e}')
                changes.append(f'ERROR deactivating Odoo user: {e}')

        # Deactivate HR employee
        if self.odoo_employee_id:
            try:
                self.odoo_employee_id.write({'active': False})
                changes.append(f'HR employee {self.odoo_employee_id.name} deactivated')
                _logger.info(f'Deactivated HR employee: {self.odoo_employee_id.name}')
            except Exception as e:
                _logger.error(f'Failed to deactivate HR employee: {e}')
                changes.append(f'ERROR deactivating HR employee: {e}')

        # Deactivate all proprelations where this person is involved
        proprelation_count = self._deactivate_proprelations()
        if proprelation_count > 0:
            changes.append(f'{proprelation_count} proprelation(s) deactivated')

        _logger.info(f'Deactivation complete for {self.name}: {", ".join(changes)}')
        return changes

    def _deactivate_proprelations(self):
        """
        Deactivate all proprelations where this person is involved.

        Searches for proprelations where:
        - id_person = this person
        - id_person_parent = this person
        - id_person_child = this person

        Returns:
            int: Number of proprelations deactivated
        """
        self.ensure_one()
        PropRelation = self.env['myschool.proprelation']

        # Find all proprelations involving this person
        proprelations = PropRelation.search([
            '|', '|',
            ('id_person', '=', self.id),
            ('id_person_parent', '=', self.id),
            ('id_person_child', '=', self.id),
            ('is_active', '=', True),
        ])

        count = len(proprelations)
        if count > 0:
            proprelations.write({'is_active': False})
            _logger.info(f'Deactivated {count} proprelation(s) for person {self.name}')

        return count

    def action_deactivate_employee(self):
        """
        Manual action to deactivate an employee.

        This will:
        - Set is_active to False
        - Deactivate Odoo user
        - Deactivate HR employee
        - Deactivate all proprelations
        """
        self.ensure_one()

        if not self.is_active:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': f'{self.name} is al gedeactiveerd.',
                    'type': 'info',
                }
            }

        # Deactivate - this will trigger _on_deactivate via write()
        self.write({'is_active': False})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Succes',
                'message': f'{self.name} is gedeactiveerd. Odoo gebruiker, HR medewerker en relaties zijn ook gedeactiveerd.',
                'type': 'success',
            }
        }

    def action_reactivate_employee(self):
        """
        Manual action to reactivate an employee.

        Note: This only reactivates the person, not the Odoo user/employee/proprelations.
        Those should be reactivated manually or via separate tasks if needed.
        """
        self.ensure_one()

        if self.is_active:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': f'{self.name} is al actief.',
                    'type': 'info',
                }
            }

        self.write({'is_active': True})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Succes',
                'message': f'{self.name} is geheractiveerd. Let op: Odoo gebruiker en HR medewerker moeten apart geheractiveerd worden.',
                'type': 'warning',
            }
        }
