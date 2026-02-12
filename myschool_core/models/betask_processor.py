# -*- coding: utf-8 -*-
"""
Backend Task Processor - Complete Version with Debug Logging
=============================================================

Converted from BeTaskServiceProcessorImpl.java

This module provides the processing logic for backend tasks.
It processes tasks based on their type and executes the appropriate actions.

Supported task types:
- EMPLOYEE: ADD, UPD, DEACT
- STUDENT: ADD, UPD, DEACT
- ORG: ADD, UPD, DEACT
- ROLE: ADD, UPD
- PROPRELATION: ADD, UPD, DEACT
- RELATION: ADD, UPD
- ODOO: PERSON, GROUPMEMBER
- LDAP variants

PropRelation Types:
- PERSON-TREE: Defines Person position in Org tree
- PPSBR: Person-Period-School-BackendRole relation
- SR-BR: SapRole to BackendRole mapping
- BRSO: BackendRole to School Org mapping

The processor can be triggered by:
- Cron job (scheduled action)
- Manual button click
- API call
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging
import json
import random
import string
import traceback
from datetime import datetime
from typing import Dict, Optional, Any, List

_logger = logging.getLogger(__name__)


# =============================================================================
# PROPRELATION NAME BUILDER FUNCTION
# =============================================================================

def build_proprelation_name(proprelation_type_name: str, **kwargs) -> str:
    """
    Build a standardized proprelation name.
    
    Format: TYPE:Abbr1=value1,Abbr2=value2,...
    Example: PPSBR:Ro=EMPLOYEE,Or=int.olvp.bawa,Pn=Demeyer
    
    Field abbreviations:
        id_org -> Or (uses name_tree or name)
        id_org_parent -> OrP (uses name_tree or name)
        id_org_child -> OrC (uses name_tree or name)
        id_period -> Pd (uses name)
        id_period_parent -> PdP (uses name)
        id_period_child -> PdC (uses name)
        id_role -> Ro (uses name)
        id_role_parent -> RoP (uses name)
        id_role_child -> RoC (uses name)
        id_person -> Pn (uses name)
        id_person_parent -> PnP (uses name)
        id_person_child -> PnC (uses name)
    
    Args:
        proprelation_type_name: The type name (e.g., 'BRSO', 'ORG-TREE', 'PERSON-TREE')
        **kwargs: Field values as records
    
    Returns:
        String like 'PPSBR:Ro=EMPLOYEE,Or=int.olvp.bawa,Pn=Demeyer'
    """
    # Field mapping: field_name -> (abbreviation, primary_field, fallback_field)
    field_map = {
        'id_org': ('Or', 'name_tree', 'name'),
        'id_org_parent': ('OrP', 'name_tree', 'name'),
        'id_org_child': ('OrC', 'name_tree', 'name'),
        'id_period': ('Pd', 'name', 'name'),
        'id_period_parent': ('PdP', 'name', 'name'),
        'id_period_child': ('PdC', 'name', 'name'),
        'id_role': ('Ro', 'name', 'name'),
        'id_role_parent': ('RoP', 'name', 'name'),
        'id_role_child': ('RoC', 'name', 'name'),
        'id_person': ('Pn', 'name', 'name'),
        'id_person_parent': ('PnP', 'name', 'name'),
        'id_person_child': ('PnC', 'name', 'name'),
    }
    
    # Order of fields in the name (for consistent output)
    field_order = [
        'id_role', 'id_role_parent', 'id_role_child',
        'id_org_parent', 'id_org', 'id_org_child',
        'id_person', 'id_person_parent', 'id_person_child',
        'id_period', 'id_period_parent', 'id_period_child',
    ]
    
    parts = []
    
    for field_name in field_order:
        if field_name in kwargs and kwargs[field_name]:
            record = kwargs[field_name]
            abbr, primary_field, fallback_field = field_map[field_name]
            
            # Get value from record
            value = None
            if hasattr(record, primary_field) and getattr(record, primary_field):
                value = getattr(record, primary_field)
            elif hasattr(record, fallback_field) and getattr(record, fallback_field):
                value = getattr(record, fallback_field)
            elif hasattr(record, 'name'):
                value = record.name
            
            if value:
                parts.append(f"{abbr}={value}")
    
    # Build the full name
    type_prefix = proprelation_type_name.upper() if proprelation_type_name else 'UNKNOWN'
    
    if parts:
        return f"{type_prefix}:{','.join(parts)}"
    return type_prefix


class BeTaskProcessor(models.AbstractModel):
    """
    Processor service for Backend Tasks.
    Equivalent to BeTaskServiceProcessorImpl.java
    """
    _name = 'myschool.betask.processor'
    _description = 'Backend Task Processor'

    # =========================================================================
    # FIELD MAPPING CONSTANTS
    # =========================================================================
    
    # -------------------------------------------------------------------------
    # EMPLOYEE Field Mappings (JSON -> Odoo)
    # -------------------------------------------------------------------------
    
    EMPLOYEE_FIELD_MAP = {
        'pPersoon': 'sap_ref',
        'personId': 'sap_person_uuid',
        'stamnr': 'stam_boek_nr',
        'naam': 'name',
        'voornaam': 'first_name',
        'nickname': 'short_name',
        'initialen': 'abbreviation',
        'geslacht': 'gender',
        'rijksregisternr': 'insz',
        'geboortedatum': 'birth_date',
        'isActive': 'is_active',
    }
    
    EMPLOYEE_DATE_FIELDS = ['birth_date']
    
    EMPLOYEE_DETAILS_FIELD_MAP = {
        'adressen': 'addresses',
        'emailadressen': 'emails',
        'comnrs': 'comnrs',
        'bank': 'bank_accounts',
        'relaties': 'relations',
        'partner': 'partner',
        'kinderen': 'children',
        'assignments': 'assignments',
    }

    # -------------------------------------------------------------------------
    # STUDENT Field Mappings (JSON -> Odoo)
    # -------------------------------------------------------------------------
    
    STUDENT_FIELD_MAP = {
        'pPersoon': 'sap_ref',
        'persoonId': 'sap_person_uuid',
        'stamnr': 'stam_boek_nr',
        'naam': 'name',
        'voornaam': 'first_name',
        'nickname': 'short_name',
        'geslacht': 'gender',
        'rijksregisternr': 'insz',
        'geboortedatum': 'birth_date',
        'begindatum': 'reg_start_date',
        'einddatum': 'reg_end_date',
        'instelnr': 'reg_inst_nr',
    }
    
    STUDENT_DATE_FIELDS = ['birth_date']
    
    STUDENT_DETAILS_FIELD_MAP = {
        'adressen': 'addresses',
        'emails': 'emails',
        'comnrs': 'comnrs',
        'relaties': 'relations',
    }

    # -------------------------------------------------------------------------
    # ORG Field Mappings (JSON -> Odoo)
    # -------------------------------------------------------------------------
    
    ORG_FIELD_MAP = {
        'name': 'name',
        'orgtype': 'org_type_name',
        'instnr': 'inst_nr',
        'isadm': 'is_administrative',
    }

    # -------------------------------------------------------------------------
    # PropRelation Type Constants (UPDATED NAMES)
    # -------------------------------------------------------------------------
    
    # PERSON-TREE: Defines where a Person resides in the Org tree
    PROPRELATION_TYPE_PERSON_TREE = 'PERSON-TREE'
    
    # PPSBR: Person-Period-School-BackendRole relation
    PROPRELATION_TYPE_PPSBR = 'PPSBR'
    
    # SR-BR: SapRole to BackendRole mapping
    PROPRELATION_TYPE_SR_BR = 'SRBR'
    
    # BRSO: BackendRole to School Org mapping
    PROPRELATION_TYPE_BRSO = 'BRSO'

    # =========================================================================
    # DATE PARSING HELPER
    # =========================================================================
    
    def _parse_date_safe(self, date_string: str) -> Optional[datetime]:
        """
        Safely parse a date string trying multiple formats.
        
        @param date_string: Date string to parse
        @return: datetime object or None if parsing fails
        """
        if not date_string or date_string in ('null', 'None', ''):
            return None
        
        date_formats = [
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d',
            '%d-%m-%Y',
            '%d/%m/%Y',
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_string, fmt)
            except (ValueError, TypeError):
                continue
        
        _logger.warning(f"Could not parse date: {date_string}")
        return None

    # =========================================================================
    # FIELD CHANGE TRACKING HELPER
    # =========================================================================

    def _get_field_changes(self, record, new_vals: dict, exclude_fields: list = None) -> List[str]:
        """
        Compare current record values with new values and return list of changes.

        Args:
            record: Odoo record to compare against
            new_vals: Dictionary of new field values
            exclude_fields: List of field names to exclude from comparison

        Returns:
            List of change descriptions like "field_name: 'old_value' → 'new_value'"
        """
        changes = []
        exclude = exclude_fields or []

        for field_name, new_value in new_vals.items():
            if field_name in exclude:
                continue

            # Get old value from record
            old_value = getattr(record, field_name, None)

            # Handle Many2one fields - compare IDs
            if hasattr(old_value, 'id'):
                old_value = old_value.id

            # Normalize values for comparison
            old_str = str(old_value) if old_value not in (None, False, '') else ''
            new_str = str(new_value) if new_value not in (None, False, '') else ''

            # Skip if values are the same
            if old_str == new_str:
                continue

            # Format the change description
            old_display = old_str[:50] + '...' if len(old_str) > 50 else old_str
            new_display = new_str[:50] + '...' if len(new_str) > 50 else new_str

            if not old_display:
                changes.append(f"  {field_name}: (empty) → '{new_display}'")
            elif not new_display:
                changes.append(f"  {field_name}: '{old_display}' → (empty)")
            else:
                changes.append(f"  {field_name}: '{old_display}' → '{new_display}'")

        return changes

    # =========================================================================
    # JSON TO ODOO MAPPING METHODS - EMPLOYEE
    # =========================================================================

    def _map_employee_json_to_person_vals(self, employee_json: dict) -> dict:
        """Map imported Informat employee JSON to myschool.person field values."""
        vals = {}
        
        for json_key, odoo_field in self.EMPLOYEE_FIELD_MAP.items():
            value = employee_json.get(json_key)
            
            if value is None or value == 'null':
                continue
            
            if odoo_field in self.EMPLOYEE_DATE_FIELDS:
                value = self._parse_date_safe(value)
            
            if odoo_field == 'sap_ref' and value is not None:
                value = str(value)
            
            vals[odoo_field] = value
        
        # Build full name: "LASTNAME, Firstname"
        first_name = employee_json.get('voornaam', '')
        last_name = employee_json.get('naam', '')
        if last_name or first_name:
            vals['name'] = f"{last_name}, {first_name}".strip(', ')
        
        # Extract email addresses
        email_addresses = employee_json.get('emailadressen', [])
        if email_addresses:
            for email_obj in email_addresses:
                email_type = (email_obj.get('type', '') or '').lower()
                email_addr = email_obj.get('email')
                if email_addr:
                    if email_type == 'school':
                        vals['email_cloud'] = email_addr
                    elif email_type in ('privé', 'prive', 'private'):
                        vals['email_private'] = email_addr
        
        return vals

    def _map_employee_json_to_person_details_vals(
        self,
        employee_json: dict,
        person_id: int,
        inst_nr: str = ''
    ) -> dict:
        """Map imported Informat employee JSON to myschool.person.details field values."""
        vals = {
            'person_id': person_id,
            'full_json_string': json.dumps(employee_json, indent=2, ensure_ascii=False),
            'extra_field_1': inst_nr,
        }

        for json_key, odoo_field in self.EMPLOYEE_DETAILS_FIELD_MAP.items():
            value = employee_json.get(json_key)
            if value is not None and value != 'null':
                if isinstance(value, (dict, list)):
                    vals[odoo_field] = json.dumps(value, indent=2, ensure_ascii=False)
                else:
                    vals[odoo_field] = str(value)

        hoofd_ambt = employee_json.get('hoofdAmbt')
        if hoofd_ambt and isinstance(hoofd_ambt, dict):
            vals['hoofd_ambt'] = hoofd_ambt.get('code', '')
        elif hoofd_ambt:
            vals['hoofd_ambt'] = str(hoofd_ambt)

        # Include assignments if present in employee_json
        assignments = employee_json.get('assignments')
        if assignments:
            vals['assignments'] = json.dumps(assignments, indent=2, ensure_ascii=False)

        return vals

    # =========================================================================
    # JSON TO ODOO MAPPING METHODS - STUDENT
    # =========================================================================

    def _map_student_json_to_person_vals(
        self, 
        registration_json: dict, 
        student_json: dict = None
    ) -> dict:
        """Map imported Informat student JSON to myschool.person field values."""
        vals = {}
        
        merged_data = {**registration_json}
        if student_json:
            merged_data.update(student_json)
        
        for json_key, odoo_field in self.STUDENT_FIELD_MAP.items():
            value = merged_data.get(json_key)
            
            if value is None or value == 'null':
                continue
            
            if odoo_field in self.STUDENT_DATE_FIELDS:
                value = self._parse_date_safe(value)
            elif odoo_field in ('reg_start_date', 'reg_end_date'):
                if value:
                    parsed = self._parse_date_safe(value)
                    value = parsed.strftime('%Y-%m-%d') if parsed else str(value)
            
            if odoo_field == 'sap_ref' and value is not None:
                value = str(value)
            
            vals[odoo_field] = value
        
        first_name = merged_data.get('voornaam', '')
        last_name = merged_data.get('naam', '')
        if last_name or first_name:
            vals['name'] = f"{last_name}, {first_name}".strip(', ')
        
        vals['is_active'] = True
        vals['automatic_sync'] = True
        
        inschr_klassen = registration_json.get('inschrKlassen', [])
        if inschr_klassen:
            first_class = inschr_klassen[0] if inschr_klassen else {}
            vals['reg_group_code'] = first_class.get('klasCode', '')
        
        vals['reg_inst_nr'] = registration_json.get('instelnr', '')
        
        return vals

    def _map_student_json_to_person_details_vals(
        self, 
        registration_json: dict,
        student_json: dict,
        person_id: int,
        inst_nr: str = ''
    ) -> dict:
        """Map imported Informat student JSON to myschool.person.details field values."""
        full_data = {**registration_json}
        if student_json:
            full_data.update(student_json)
        
        vals = {
            'person_id': person_id,
            'full_json_string': json.dumps(full_data, indent=2, ensure_ascii=False),
            'extra_field_1': inst_nr,
        }

        if student_json:
            for json_key, odoo_field in self.STUDENT_DETAILS_FIELD_MAP.items():
                value = student_json.get(json_key)
                if value is not None and value != 'null':
                    if isinstance(value, (dict, list)):
                        vals[odoo_field] = json.dumps(value, indent=2, ensure_ascii=False)
                    else:
                        vals[odoo_field] = str(value)

        return vals

    # =========================================================================
    # JSON TO ODOO MAPPING METHODS - ORG
    # =========================================================================

    def _map_org_json_to_org_vals(self, org_json: dict) -> dict:
        """Map imported org/class JSON to myschool.org field values."""
        vals = {
            'is_active': True,
            'automatic_sync': True,
        }
        
        if 'name' in org_json:
            vals['name'] = org_json['name']
            vals['name_short'] = org_json.get('name', '')[:20]
        
        if 'instnr' in org_json:
            vals['inst_nr'] = org_json['instnr']
        
        if 'isadm' in org_json:
            vals['is_administrative'] = str(org_json['isadm']).lower() == 'true'
        
        org_type_name = org_json.get('orgtype', '')
        if org_type_name:
            OrgType = self.env['myschool.org.type']
            org_type = OrgType.search([('name', '=', org_type_name)], limit=1)
            if org_type:
                vals['org_type_id'] = org_type.id
        
        return vals

    # =========================================================================
    # EMPLOYEE CRUD METHODS
    # =========================================================================

    def  _create_person_from_employee_json(self, employee_json: dict, inst_nr: str = ''):
        """Create a Person and PersonDetails record from employee JSON."""
        Person = self.env['myschool.person'].with_context(skip_manual_audit=True)
        PersonDetails = self.env['myschool.person.details']

        person_vals = self._map_employee_json_to_person_vals(employee_json)
        person_vals['is_active'] = True
        person_vals['automatic_sync'] = True

        # Generate random password for new person
        chars = string.ascii_letters + string.digits
        person_vals['password'] = ''.join(random.choice(chars) for _ in range(8))

        PersonType = self.env['myschool.person.type']
        employee_type = PersonType.search([('name', '=', 'EMPLOYEE')], limit=1)
        if employee_type:
            person_vals['person_type_id'] = employee_type.id

        _logger.info(f"Creating employee: {person_vals.get('name', 'Unknown')}")
        new_person = Person.create(person_vals)
        
        details_vals = self._map_employee_json_to_person_details_vals(
            employee_json,
            new_person.id,
            inst_nr
        )
        details_vals['is_active'] = True  # First version is active
        PersonDetails.create(details_vals)

        _logger.info(f"Created employee {new_person.name} (ID: {new_person.id})")
        
        # Trigger ODOO-PERSON-ADD task to create Odoo User and HR Employee
        odoo_task_data = {
            'person_id': new_person.id,
            'personId': employee_json.get('personId'),
            'name': new_person.name,
            'first_name': employee_json.get('voornaam', ''),
            'email': new_person.email_cloud or new_person.email_private,
        }
        self._create_betask_internal(
            'ODOO', 'PERSON', 'ADD',
            json.dumps(odoo_task_data),
            None
        )
        _logger.info(f'Created ODOO-PERSON-ADD task for {new_person.name}')

        # Create PPSBR PropRelation between person, school org and role
        self._create_ppsbr_for_new_employee(new_person, employee_json, inst_nr)

        return new_person

    def _create_ppsbr_for_new_employee(self, person, employee_json: dict, inst_nr: str):
        """
        Create a backend task to create a PPSBR PropRelation for a newly created employee.

        Links the person to the school org with the EMPLOYEE backend role.
        """
        Org = self.env['myschool.org']
        Role = self.env['myschool.role']

        if not inst_nr:
            _logger.warning(f'No inst_nr provided for employee {person.name}, cannot create PPSBR task')
            return

        # Find the school org
        school_org = Org.search([
            ('inst_nr', '=', inst_nr),
            ('is_active', '=', True)
        ], limit=1)
        if not school_org:
            self._log_error('BETASK-551', f'School org not found for inst_nr {inst_nr}')
            return

        # Find the EMPLOYEE backend role
        employee_role = Role.search([('name', '=', 'EMPLOYEE')], limit=1)
        if not employee_role:
            self._log_error('BETASK-552', f'EMPLOYEE role not found')
            return

        # Create DB-PROPRELATION-ADD task
        proprel_data = {
            'personId': person.sap_person_uuid,
            'person_db_id': person.id,
            'instNr': inst_nr,
            'orgId': school_org.id,
            'roleId': employee_role.id,
            'roleName': employee_role.name,
        }
        self._create_betask_internal(
            'DB', 'PROPRELATION', 'ADD',
            json.dumps(proprel_data),
            None
        )
        _logger.info(f'Created DB-PROPRELATION-ADD task for {person.name} at {school_org.name} with EMPLOYEE role')

    def _ensure_ppsbr_exists_for_employee(self, person, inst_nr: str, field_changes: list = None):
        """
        Check if a PPSBR exists for the person at the school with EMPLOYEE role.
        If not, create a DB-PROPRELATION-ADD task to create it.
        """
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        Org = self.env['myschool.org']
        Role = self.env['myschool.role']

        if not inst_nr:
            return

        # Get PPSBR type
        ppsbr_type = PropRelationType.search([
            ('name', '=', self.PROPRELATION_TYPE_PPSBR)
        ], limit=1)
        if not ppsbr_type:
            return

        # Find the school org
        school_org = Org.search([
            ('inst_nr', '=', inst_nr),
            ('is_active', '=', True)
        ], limit=1)
        if not school_org:
            return

        # Find the EMPLOYEE backend role
        employee_role = Role.search([('name', '=', 'EMPLOYEE')], limit=1)
        if not employee_role:
            return

        # Check if PPSBR already exists
        existing_ppsbr = PropRelation.search([
            ('id_person', '=', person.id),
            ('id_org', '=', school_org.id),
            ('id_role', '=', employee_role.id),
            ('proprelation_type_id', '=', ppsbr_type.id),
            ('is_active', '=', True)
        ], limit=1)

        if existing_ppsbr:
            return  # PPSBR already exists

        # Create DB-PROPRELATION-ADD task
        proprel_data = {
            'personId': person.sap_person_uuid,
            'person_db_id': person.id,
            'instNr': inst_nr,
            'orgId': school_org.id,
            'roleId': employee_role.id,
            'roleName': employee_role.name,
        }
        self._create_betask_internal(
            'DB', 'PROPRELATION', 'ADD',
            json.dumps(proprel_data),
            None
        )
        _logger.info(f'Created DB-PROPRELATION-ADD task for {person.name} at {school_org.name} with EMPLOYEE role')

        if field_changes is not None:
            field_changes.append(f"Created PPSBR task for {school_org.name} with EMPLOYEE role")

    def _update_person_from_employee_json(
        self,
        person,
        employee_json: dict,
        inst_nr: str = '',
        action: str = 'UPDATE'
    ) -> dict:
        """Update a Person and PersonDetails record from employee JSON.

        Returns:
            dict with 'success' and 'field_changes' keys
        """
        # Skip manual audit for backend task processing
        person = person.with_context(skip_manual_audit=True)
        PersonDetails = self.env['myschool.person.details']
        field_changes = []

        person_vals = self._map_employee_json_to_person_vals(employee_json)

        if action == 'REACTIVATE':
            person_vals['is_active'] = True
            _logger.info(f"Reactivating employee {person.name}")

        # Track field changes before writing
        person_changes = self._get_field_changes(person, person_vals)
        if person_changes:
            field_changes.append(f"Person fields changed:")
            field_changes.extend(person_changes)

        person.write(person_vals)

        # Search for current ACTIVE PersonDetails record
        existing_details = PersonDetails.search([
            ('person_id', '=', person.id),
            ('extra_field_1', '=', inst_nr),
            ('is_active', '=', True)
        ], limit=1)

        details_vals = self._map_employee_json_to_person_details_vals(
            employee_json,
            person.id,
            inst_nr
        )
        details_vals['is_active'] = True  # New records are always active

        if existing_details:
            # Track detail changes (exclude large JSON fields from detailed logging)
            detail_changes = self._get_field_changes(
                existing_details, details_vals,
                exclude_fields=['full_json_string', 'person_id', 'is_active']
            )

            # Also check if full_json_string has changed
            old_json = existing_details.full_json_string or ''
            new_json = details_vals.get('full_json_string', '')
            json_changed = old_json != new_json

            if detail_changes or json_changed:
                # Changes detected - create new version, deactivate old
                field_changes.append(f"PersonDetails version created (previous deactivated):")
                if detail_changes:
                    field_changes.extend(detail_changes)
                if json_changed:
                    field_changes.append(f"  full_json_string: [content changed]")

                # Deactivate the current record
                existing_details.write({'is_active': False})
                _logger.info(f"Deactivated PersonDetails ID {existing_details.id} for {person.name}")

                # Create new active version
                new_details = PersonDetails.create(details_vals)
                _logger.info(f"Created new PersonDetails version ID {new_details.id} for {person.name}, instNr {inst_nr}")
            else:
                field_changes.append(f"PersonDetails unchanged - no new version created")
                _logger.info(f"No changes in PersonDetails for {person.name}, instNr {inst_nr}")
        else:
            # No active record exists - create first version
            PersonDetails.create(details_vals)
            field_changes.append(f"Created first PersonDetails version for instNr {inst_nr}")
            _logger.info(f"Created first PersonDetails for {person.name}, instNr {inst_nr}")

        # Trigger ODOO-PERSON-UPD task if person has Odoo user
        if person.odoo_user_id:
            odoo_task_data = {
                'person_id': person.id,
                'personId': employee_json.get('personId'),
                'name': person.name,
                'email': person.email_cloud or person.email_private,
            }
            self._create_betask_internal(
                'ODOO', 'PERSON', 'UPD',
                json.dumps(odoo_task_data),
                None
            )
            _logger.info(f'Created ODOO-PERSON-UPD task for {person.name}')

        # Check if PPSBR exists for this person at this school with EMPLOYEE role
        # If not, create a task to create it
        self._ensure_ppsbr_exists_for_employee(person, inst_nr, field_changes)

        return {'success': True, 'field_changes': field_changes}

    def _deactivate_person(self, person, data_json: dict = None, inst_nr: str = '') -> bool:
        """Deactivate a Person record and their PropRelations."""
        # Skip manual audit for backend task processing
        person = person.with_context(skip_manual_audit=True)
        PersonDetails = self.env['myschool.person.details']
        
        # Trigger ODOO-PERSON-DEACT task BEFORE deactivating (to capture user info)
        if person.odoo_user_id:
            odoo_task_data = {
                'person_id': person.id,
                'personId': person.sap_person_uuid,
                'reason': 'Employee deactivated'
            }
            self._create_betask_internal(
                'ODOO', 'PERSON', 'DEACT',
                json.dumps(odoo_task_data),
                None
            )
            _logger.info(f'Created ODOO-PERSON-DEACT task for {person.name}')
        
        # First deactivate PropRelations
        self._deactivate_person_proprelations(person)
        
        # Then deactivate person
        person.write({'is_active': False})
        _logger.info(f"Deactivated person {person.name}")
        
        if data_json:
            existing_details = PersonDetails.search([
                ('person_id', '=', person.id),
                ('extra_field_1', '=', inst_nr)
            ], limit=1)
            
            if existing_details:
                existing_details.write({
                    'full_json_string': json.dumps(data_json, indent=2, ensure_ascii=False)
                })
        
        return True

    def _deactivate_person_proprelations(self, person) -> bool:
        """Deactivate all PropRelations for a person."""
        PropRelation = self.env['myschool.proprelation']
        
        active_proprels = PropRelation.search([
            ('id_person', '=', person.id),
            ('is_active', '=', True)
        ])
        
        if active_proprels:
            active_proprels.write({'is_active': False})
            _logger.info(f'Deactivated {len(active_proprels)} PropRelations for {person.name}')
        
        return True

    # =========================================================================
    # STUDENT CRUD METHODS
    # =========================================================================

    def _create_person_from_student_json(
        self,
        registration_json: dict,
        student_json: dict = None,
        inst_nr: str = ''
    ):
        """Create a Person and PersonDetails record from student JSON."""
        Person = self.env['myschool.person'].with_context(skip_manual_audit=True)
        PersonDetails = self.env['myschool.person.details']

        person_vals = self._map_student_json_to_person_vals(registration_json, student_json)

        # Generate random password for new person
        chars = string.ascii_letters + string.digits
        person_vals['password'] = ''.join(random.choice(chars) for _ in range(8))

        PersonType = self.env['myschool.person.type']
        student_type = PersonType.search([('name', '=', 'STUDENT')], limit=1)
        if student_type:
            person_vals['person_type_id'] = student_type.id

        _logger.info(f"Creating student: {person_vals.get('name', 'Unknown')}")
        new_person = Person.create(person_vals)
        
        details_vals = self._map_student_json_to_person_details_vals(
            registration_json,
            student_json or {},
            new_person.id,
            inst_nr or registration_json.get('instelnr', '')
        )
        details_vals['is_active'] = True  # First version is active
        PersonDetails.create(details_vals)

        _logger.info(f"Created student {new_person.name} (ID: {new_person.id})")
        return new_person

    def _update_person_from_student_json(
        self,
        person,
        registration_json: dict,
        student_json: dict = None,
        inst_nr: str = '',
        action: str = 'UPDATE'
    ) -> dict:
        """Update a Person and PersonDetails record from student JSON.

        Returns:
            dict with 'success' and 'field_changes' keys
        """
        # Skip manual audit for backend task processing
        person = person.with_context(skip_manual_audit=True)
        PersonDetails = self.env['myschool.person.details']
        field_changes = []

        person_vals = self._map_student_json_to_person_vals(registration_json, student_json)

        if action == 'REACTIVATE':
            person_vals['is_active'] = True
            person_vals['reg_end_date'] = None
            _logger.info(f"Reactivating student {person.name}")

        # Track field changes before writing
        person_changes = self._get_field_changes(person, person_vals)
        if person_changes:
            field_changes.append(f"Person fields changed:")
            field_changes.extend(person_changes)

        person.write(person_vals)

        # Search for current ACTIVE PersonDetails record
        existing_details = PersonDetails.search([
            ('person_id', '=', person.id),
            ('extra_field_1', '=', inst_nr),
            ('is_active', '=', True)
        ], limit=1)

        details_vals = self._map_student_json_to_person_details_vals(
            registration_json,
            student_json or {},
            person.id,
            inst_nr
        )
        details_vals['is_active'] = True  # New records are always active

        if existing_details:
            # Track detail changes (exclude large JSON fields from detailed logging)
            detail_changes = self._get_field_changes(
                existing_details, details_vals,
                exclude_fields=['full_json_string', 'person_id', 'is_active']
            )

            # Also check if full_json_string has changed
            old_json = existing_details.full_json_string or ''
            new_json = details_vals.get('full_json_string', '')
            json_changed = old_json != new_json

            if detail_changes or json_changed:
                # Changes detected - create new version, deactivate old
                field_changes.append(f"PersonDetails version created (previous deactivated):")
                if detail_changes:
                    field_changes.extend(detail_changes)
                if json_changed:
                    field_changes.append(f"  full_json_string: [content changed]")

                # Deactivate the current record
                existing_details.write({'is_active': False})
                _logger.info(f"Deactivated PersonDetails ID {existing_details.id} for {person.name}")

                # Create new active version
                new_details = PersonDetails.create(details_vals)
                _logger.info(f"Created new PersonDetails version ID {new_details.id} for {person.name}, instNr {inst_nr}")
            else:
                field_changes.append(f"PersonDetails unchanged - no new version created")
                _logger.info(f"No changes in PersonDetails for {person.name}, instNr {inst_nr}")
        else:
            # No active record exists - create first version
            PersonDetails.create(details_vals)
            field_changes.append(f"Created first PersonDetails version for instNr {inst_nr}")
            _logger.info(f"Created first PersonDetails for {person.name}, instNr {inst_nr}")

        return {'success': True, 'field_changes': field_changes}

    # =========================================================================
    # ORG CRUD METHODS
    # =========================================================================

    def _create_org_from_json(self, org_json: dict):
        """Create an Org record from JSON."""
        Org = self.env['myschool.org']
        
        org_vals = self._map_org_json_to_org_vals(org_json)
        
        _logger.info(f"Creating org: {org_vals.get('name', 'Unknown')}")
        new_org = Org.create(org_vals)
        
        _logger.info(f"Created org {new_org.name} (ID: {new_org.id})")
        return new_org

    def _update_org_from_json(self, org, org_json: dict) -> dict:
        """Update an Org record from JSON.

        Returns:
            dict with 'success' and 'field_changes' keys
        """
        org_vals = self._map_org_json_to_org_vals(org_json)

        # Track field changes before writing
        field_changes = self._get_field_changes(org, org_vals)

        org.write(org_vals)
        _logger.info(f"Updated org {org.name}")

        return {'success': True, 'field_changes': field_changes}

    def _deactivate_org(self, org) -> bool:
        """Deactivate an Org record."""
        org.write({'is_active': False})
        _logger.info(f"Deactivated org {org.name}")
        return True

    # =========================================================================
    # TASK REGISTRATION METHODS
    # =========================================================================
    
    @api.model
    def _register_task_success(self, task, result_data=None, changes=None):
        """Mark task as successfully completed."""
        task.action_set_completed(result_data, changes)
        _logger.info(f'Task {task.name} completed successfully')
        return True
    
    @api.model
    def _register_task_error(self, task, error_msg=None):
        """Mark task as failed."""
        task.action_set_error(error_msg)
        _logger.error(f'Task {task.name} failed: {error_msg}')
        return False

    # =========================================================================
    # MAIN PROCESSING METHODS
    # =========================================================================
    
    @api.model
    def process_tasks_by_type(self, task_type):
        """Process all pending tasks of a specific type."""
        self._log_event('BETASK-002', f'START PROCESSING TASKS: {task_type.name}')
        
        manual_tasks = self._check_manual_tasks()
        if manual_tasks:
            self._log_error(
                'BETASK-003',
                f'Found {len(manual_tasks)} manual tasks. Please process them first!'
            )
        
        task_service = self.env['myschool.betask.service']
        tasks_to_process = task_service.find_by_type_and_status(task_type, 'new')
        
        if not tasks_to_process:
            _logger.info(f'No pending tasks found for type: {task_type.name}')
            return True
        
        _logger.info(f'Found {len(tasks_to_process)} tasks to process for type: {task_type.name}')
        
        all_success = True
        processed_count = 0
        error_count = 0
        
        for task in tasks_to_process:
            try:
                result = self.process_single_task(task)
                if result:
                    processed_count += 1
                else:
                    error_count += 1
                    all_success = False
            except Exception as e:
                error_count += 1
                all_success = False
                self._register_task_error(task, str(e))
                _logger.exception(f'Exception processing task {task.name}')
        
        self._log_event(
            'BETASK-004',
            f'COMPLETED PROCESSING {task_type.name}: {processed_count} success, {error_count} errors'
        )
        
        return all_success
    
    @api.model
    def process_single_task(self, task):
        """Process a single task.

        Processor methods can return:
        - True/False: simple success/failure
        - dict with 'success' and optional 'changes': detailed result
        - string: treated as changes description (success=True)
        """
        if not task:
            return False

        if task.status not in ['new', 'error']:
            _logger.warning(f'Task {task.name} is not in processable status: {task.status}')
            return False

        task.action_set_processing()

        try:
            processor_method = task.betasktype_id.processor_method

            if processor_method and hasattr(self, processor_method):
                method = getattr(self, processor_method)
                result = method(task)
            else:
                result = self._process_task_generic(task)

            # Handle different return types
            if isinstance(result, dict):
                success = result.get('success', True)
                changes = result.get('changes')
                if success:
                    return self._register_task_success(task, changes=changes)
                else:
                    return self._register_task_error(task, result.get('error', 'Processing failed'))
            elif isinstance(result, str):
                # String result means success with changes description
                return self._register_task_success(task, changes=result)
            elif result:
                return self._register_task_success(task)
            else:
                return self._register_task_error(task, 'Processing returned False')
                
        except Exception as e:
            error_msg = f'{str(e)}\n{traceback.format_exc()}'
            self._log_error('BETASK-500', f'Error processing task {task.name}: {error_msg}')
            return self._register_task_error(task, str(e))
    
    @api.model
    def process_all_pending(self):
        """Process all pending tasks for all auto-process task types."""
        self._log_event('BETASK-001', 'START PROCESSING ALL PENDING TASKS')
        
        type_service = self.env['myschool.betask.type.service']
        task_types = type_service.find_auto_process_types()
        
        results = {
            'total_types': len(task_types),
            'processed_types': 0,
            'total_tasks': 0,
            'successful_tasks': 0,
            'failed_tasks': 0,
        }
        
        for task_type in task_types:
            task_service = self.env['myschool.betask.service']
            pending_tasks = task_service.find_by_type_and_status(task_type, 'new')
            
            if pending_tasks:
                results['total_tasks'] += len(pending_tasks)
                
                for task in pending_tasks:
                    try:
                        if self.process_single_task(task):
                            results['successful_tasks'] += 1
                        else:
                            results['failed_tasks'] += 1
                    except Exception as e:
                        results['failed_tasks'] += 1
                        _logger.exception(f'Exception processing task {task.name}')
                
                results['processed_types'] += 1
        
        self._log_event(
            'BETASK-005',
            f'COMPLETED ALL PENDING: {results["successful_tasks"]} success, {results["failed_tasks"]} errors'
        )
        
        return results

    # =========================================================================
    # GENERIC TASK ROUTER
    # =========================================================================
    
    @api.model
    def _process_task_generic(self, task):
        """Generic task processor - routes to specific handlers based on type."""
        target = task.betasktype_id.target
        obj = task.betasktype_id.object
        action = task.betasktype_id.action
        
        _logger.info(f'Processing task {task.name}: {target}_{obj}_{action}')
        
        handler_map = {
            # DB EMPLOYEE handlers
            ('DB', 'EMPLOYEE', 'ADD'): self.process_db_employee_add,
            ('DB', 'EMPLOYEE', 'UPD'): self.process_db_employee_upd,
            ('DB', 'EMPLOYEE', 'DEACT'): self.process_db_employee_deact,
            
            # DB STUDENT handlers
            ('DB', 'STUDENT', 'ADD'): self.process_db_student_add,
            ('DB', 'STUDENT', 'UPD'): self.process_db_student_upd,
            ('DB', 'STUDENT', 'DEACT'): self.process_db_student_deact,
            
            # DB ORG handlers
            ('DB', 'ORG', 'ADD'): self.process_db_org_add,
            ('DB', 'ORG', 'UPD'): self.process_db_org_upd,
            ('DB', 'ORG', 'DEACT'): self.process_db_org_deact,
            
            # DB ROLE handlers
            ('DB', 'ROLE', 'ADD'): self.process_db_role_add,
            ('DB', 'ROLE', 'UPD'): self.process_db_role_upd,
            
            # DB PROPRELATION handlers
            ('DB', 'PROPRELATION', 'ADD'): self.process_db_proprelation_add,
            ('DB', 'PROPRELATION', 'UPD'): self.process_db_proprelation_upd,
            ('DB', 'PROPRELATION', 'DEACT'): self.process_db_proprelation_deact,
            
            # DB RELATION handlers (for student relations)
            ('DB', 'RELATION', 'ADD'): self.process_db_relation_add,
            ('DB', 'RELATION', 'UPD'): self.process_db_relation_upd,
            
            # ODOO PERSON handlers (User/Employee management)
            ('ODOO', 'PERSON', 'ADD'): self.process_odoo_person_add,
            ('ODOO', 'PERSON', 'UPD'): self.process_odoo_person_upd,
            ('ODOO', 'PERSON', 'DEACT'): self.process_odoo_person_deact,
            
            # ODOO GROUPMEMBER handlers
            ('ODOO', 'GROUPMEMBER', 'ADD'): self.process_odoo_groupmember_add,
            ('ODOO', 'GROUPMEMBER', 'REMOVE'): self.process_odoo_groupmember_remove,
            
            # LDAP USER handlers
            ('LDAP', 'USER', 'ADD'): self.process_ldap_user_add,
            ('LDAP', 'USER', 'UPD'): self.process_ldap_user_upd,
            ('LDAP', 'USER', 'DEACT'): self.process_ldap_user_deact,
            ('LDAP', 'USER', 'DEL'): self.process_ldap_user_del,

            # LDAP GROUP handlers
            ('LDAP', 'GROUP', 'ADD'): self.process_ldap_group_add,
            ('LDAP', 'GROUP', 'UPD'): self.process_ldap_group_upd,
            ('LDAP', 'GROUP', 'DEACT'): self.process_ldap_group_deact,
            ('LDAP', 'GROUP', 'DEL'): self.process_ldap_group_del,

            # LDAP GROUPMEMBER handlers
            ('LDAP', 'GROUPMEMBER', 'ADD'): self.process_ldap_groupmember_add,
            ('LDAP', 'GROUPMEMBER', 'REMOVE'): self.process_ldap_groupmember_remove,
        }
        
        handler = handler_map.get((target, obj, action))
        
        if handler:
            return handler(task)
        else:
            _logger.warning(f'No specific handler for {target}_{obj}_{action}, using fallback')
            return True
    
    @api.model
    def _parse_task_data(self, data_str):
        """Parse task data from string (usually JSON)."""
        if not data_str:
            return None
        try:
            return json.loads(data_str)
        except (json.JSONDecodeError, TypeError):
            return data_str

    # =========================================================================
    # DB EMPLOYEE TASK PROCESSORS
    # =========================================================================
    
    @api.model
    def process_db_employee_add(self, task):
        """Process DB EMPLOYEE ADD task - Create new employee."""
        _logger.info(f'Processing DB_EMPLOYEE_ADD: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-510', f'No data in task {task.name}')
            return False

        inst_nr = data.get('instNr', '')
        person_uuid = data.get('personId')

        if person_uuid:
            Person = self.env['myschool.person']
            existing = Person.search([('sap_person_uuid', '=', person_uuid)], limit=1)
            if existing:
                _logger.warning(f'Employee {person_uuid} already exists, converting to UPDATE')
                changes.append(f"Employee {person_uuid} already exists - converted to UPDATE")
                result = self._update_person_from_employee_json(existing, data, inst_nr, 'UPDATE')
                changes.append(f"Updated person: {existing.name} (ID: {existing.id})")
                if result.get('field_changes'):
                    changes.extend(result['field_changes'])
                return {'success': True, 'changes': '\n'.join(changes)}

        try:
            new_person = self._create_person_from_employee_json(data, inst_nr)
            changes.append(f"Created person: {new_person.name} (ID: {new_person.id})")
            changes.append(f"Created ODOO-PERSON-ADD task for user/employee creation")
            return {'success': True, 'changes': '\n'.join(changes)}
        except Exception as e:
            self._log_error('BETASK-511', f'Error creating employee: {str(e)}')
            raise
    
    @api.model
    def process_db_employee_upd(self, task):
        """
        Process DB EMPLOYEE UPD task - Update existing employee.

        Handles actions: UPDATE, ADD-DETAILS, REACTIVATE
        """
        _logger.info(f'Processing DB_EMPLOYEE_UPD: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        data2 = self._parse_task_data(task.data2)

        if not data:
            self._log_error('BETASK-520', f'No data in task {task.name}')
            return False

        action = 'UPDATE'
        if data2 and isinstance(data2, dict):
            action = data2.get('action', 'UPDATE')

        inst_nr = data.get('instNr', '')
        person_uuid = data.get('personId')

        _logger.info(f'Employee UPD action: {action}, instNr: {inst_nr}')

        Person = self.env['myschool.person']
        person = Person.search([('sap_person_uuid', '=', person_uuid)], limit=1)

        if not person:
            _logger.warning(f'Employee {person_uuid} not found, converting to ADD')
            changes.append(f"Employee {person_uuid} not found - converted to ADD")
            new_person = self._create_person_from_employee_json(data, inst_nr)
            if new_person:
                changes.append(f"Created person: {new_person.name} (ID: {new_person.id})")
            return {'success': new_person is not None, 'changes': '\n'.join(changes)}

        try:
            if action == 'REACTIVATE':
                result = self._update_person_from_employee_json(person, data, inst_nr, 'REACTIVATE')
                changes.append(f"Reactivated person: {person.name} (ID: {person.id})")
            elif action == 'ADD-DETAILS':
                result = self._update_person_from_employee_json(person, data, inst_nr, 'UPDATE')
                changes.append(f"Added details for person: {person.name} (ID: {person.id})")
            else:
                result = self._update_person_from_employee_json(person, data, inst_nr, 'UPDATE')
                changes.append(f"Updated person: {person.name} (ID: {person.id})")
            # Include field-level changes
            if result.get('field_changes'):
                changes.extend(result['field_changes'])
            if person.odoo_user_id:
                changes.append(f"Created ODOO-PERSON-UPD task for Odoo user update")
            return {'success': True, 'changes': '\n'.join(changes)}
        except Exception as e:
            self._log_error('BETASK-521', f'Error updating employee: {str(e)}')
            raise
    
    @api.model
    def process_db_employee_deact(self, task):
        """Process DB EMPLOYEE DEACT task - Deactivate employee."""
        _logger.info(f'Processing DB_EMPLOYEE_DEACT: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-530', f'No data in task {task.name}')
            return False

        inst_nr = data.get('instNr', '')
        person_uuid = data.get('personId')

        Person = self.env['myschool.person']
        person = Person.search([('sap_person_uuid', '=', person_uuid)], limit=1)

        if not person:
            _logger.warning(f'Employee {person_uuid} not found for DEACT')
            changes.append(f"Employee {person_uuid} not found - nothing to deactivate")
            return {'success': True, 'changes': '\n'.join(changes)}

        try:
            had_odoo_user = bool(person.odoo_user_id)
            self._deactivate_person(person, data, inst_nr)
            changes.append(f"Deactivated person: {person.name} (ID: {person.id})")
            changes.append(f"Deactivated related PropRelations")
            if had_odoo_user:
                changes.append(f"Created ODOO-PERSON-DEACT task for Odoo user deactivation")
            return {'success': True, 'changes': '\n'.join(changes)}
        except Exception as e:
            self._log_error('BETASK-531', f'Error deactivating employee: {str(e)}')
            raise

    # =========================================================================
    # DB STUDENT TASK PROCESSORS
    # =========================================================================
    
    @api.model
    def process_db_student_add(self, task):
        """Process DB STUDENT ADD task - Create new student."""
        _logger.info(f'Processing DB_STUDENT_ADD: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-540', f'No data in task {task.name}')
            return False

        inst_nr = data.get('instelnr', '') or data.get('instNr', '')
        person_uuid = data.get('persoonId') or data.get('personId')

        if person_uuid:
            Person = self.env['myschool.person']
            existing = Person.search([('sap_person_uuid', '=', person_uuid)], limit=1)
            if existing:
                _logger.warning(f'Student {person_uuid} already exists, converting to UPDATE')
                changes.append(f"Student {person_uuid} already exists - converted to UPDATE")
                result = self._update_person_from_student_json(existing, data, data, inst_nr, 'UPDATE')
                changes.append(f"Updated person: {existing.name} (ID: {existing.id})")
                if result.get('field_changes'):
                    changes.extend(result['field_changes'])
                return {'success': True, 'changes': '\n'.join(changes)}

        try:
            new_person = self._create_person_from_student_json(data, data, inst_nr)
            changes.append(f"Created student: {new_person.name} (ID: {new_person.id})")
            return {'success': True, 'changes': '\n'.join(changes)}
        except Exception as e:
            self._log_error('BETASK-541', f'Error creating student: {str(e)}')
            raise
    
    @api.model
    def process_db_student_upd(self, task):
        """Process DB STUDENT UPD task - Update existing student."""
        _logger.info(f'Processing DB_STUDENT_UPD: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        data2 = self._parse_task_data(task.data2)

        if not data:
            self._log_error('BETASK-550', f'No data in task {task.name}')
            return False

        action = 'UPDATE'
        if data2 and isinstance(data2, dict):
            action = data2.get('action', 'UPDATE')

        inst_nr = data.get('instelnr', '') or data.get('instNr', '')
        person_uuid = data.get('persoonId') or data.get('personId')

        Person = self.env['myschool.person']
        person = Person.search([('sap_person_uuid', '=', person_uuid)], limit=1)

        if not person:
            _logger.warning(f'Student {person_uuid} not found, converting to ADD')
            changes.append(f"Student {person_uuid} not found - converted to ADD")
            new_person = self._create_person_from_student_json(data, data, inst_nr)
            if new_person:
                changes.append(f"Created student: {new_person.name} (ID: {new_person.id})")
            return {'success': new_person is not None, 'changes': '\n'.join(changes)}

        try:
            result = self._update_person_from_student_json(person, data, data, inst_nr, action)
            changes.append(f"Updated student: {person.name} (ID: {person.id})")
            changes.append(f"Action: {action}")
            if result.get('field_changes'):
                changes.extend(result['field_changes'])
            return {'success': True, 'changes': '\n'.join(changes)}
        except Exception as e:
            self._log_error('BETASK-551', f'Error updating student: {str(e)}')
            raise
    
    @api.model
    def process_db_student_deact(self, task):
        """Process DB STUDENT DEACT task - Deactivate student."""
        _logger.info(f'Processing DB_STUDENT_DEACT: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-560', f'No data in task {task.name}')
            return False

        inst_nr = data.get('instelnr', '') or data.get('instNr', '')
        person_uuid = data.get('persoonId') or data.get('personId')

        # Skip manual audit for backend task processing
        Person = self.env['myschool.person'].with_context(skip_manual_audit=True)
        person = Person.search([('sap_person_uuid', '=', person_uuid)], limit=1)

        if not person:
            _logger.warning(f'Student {person_uuid} not found for DEACT')
            changes.append(f"Student {person_uuid} not found - nothing to deactivate")
            return {'success': True, 'changes': '\n'.join(changes)}

        try:
            reg_end_date = data.get('regEndDate') or data.get('einddatum')
            if reg_end_date:
                parsed_date = self._parse_date_safe(reg_end_date)
                if parsed_date:
                    person.write({'reg_end_date': parsed_date.strftime('%Y-%m-%d')})
                    changes.append(f"Set registration end date: {parsed_date.strftime('%Y-%m-%d')}")

            self._deactivate_person(person, data, inst_nr)
            changes.append(f"Deactivated student: {person.name} (ID: {person.id})")
            changes.append(f"Deactivated related PropRelations")
            return {'success': True, 'changes': '\n'.join(changes)}
        except Exception as e:
            self._log_error('BETASK-561', f'Error deactivating student: {str(e)}')
            raise

    # =========================================================================
    # DB ORG TASK PROCESSORS
    # =========================================================================
    
    @api.model
    def process_db_org_add(self, task):
        """Process DB ORG ADD task - Create new organization/class."""
        _logger.info(f'Processing DB_ORG_ADD: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-570', f'No data in task {task.name}')
            return False

        org_name = data.get('name', '')
        inst_nr = data.get('instnr', '')

        Org = self.env['myschool.org']
        existing = Org.search([
            ('name_short', '=', org_name),
            ('inst_nr', '=', inst_nr),
            ('is_active', '=', True)
        ], limit=1)

        if existing:
            _logger.warning(f'Org {org_name} already exists, converting to UPDATE')
            changes.append(f"Org {org_name} already exists - converted to UPDATE")
            result = self._update_org_from_json(existing, data)
            changes.append(f"Updated org: {existing.name} (ID: {existing.id})")
            if result.get('field_changes'):
                changes.extend(result['field_changes'])
            return {'success': True, 'changes': '\n'.join(changes)}

        try:
            new_org = self._create_org_from_json(data)
            changes.append(f"Created org: {new_org.name} (ID: {new_org.id})")
            return {'success': True, 'changes': '\n'.join(changes)}
        except Exception as e:
            self._log_error('BETASK-571', f'Error creating org: {str(e)}')
            raise
    
    @api.model
    def process_db_org_upd(self, task):
        """Process DB ORG UPD task - Update existing organization."""
        _logger.info(f'Processing DB_ORG_UPD: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-580', f'No data in task {task.name}')
            return False

        org_id = data.get('orgId')
        org_name = data.get('name', '')
        inst_nr = data.get('instnr', '')

        Org = self.env['myschool.org']

        if org_id:
            org = Org.browse(org_id)
        else:
            org = Org.search([
                ('name_short', '=', org_name),
                ('inst_nr', '=', inst_nr)
            ], limit=1)

        if not org:
            _logger.warning(f'Org not found, converting to ADD')
            changes.append(f"Org not found - converted to ADD")
            new_org = self._create_org_from_json(data)
            if new_org:
                changes.append(f"Created org: {new_org.name} (ID: {new_org.id})")
            return {'success': new_org is not None, 'changes': '\n'.join(changes)}

        try:
            result = self._update_org_from_json(org, data)
            changes.append(f"Updated org: {org.name} (ID: {org.id})")
            if result.get('field_changes'):
                changes.extend(result['field_changes'])
            return {'success': True, 'changes': '\n'.join(changes)}
        except Exception as e:
            self._log_error('BETASK-581', f'Error updating org: {str(e)}')
            raise
    
    @api.model
    def process_db_org_deact(self, task):
        """Process DB ORG DEACT task - Deactivate organization."""
        _logger.info(f'Processing DB_ORG_DEACT: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-590', f'No data in task {task.name}')
            return False

        org_id = data.get('orgId')
        org_name = data.get('name', '')
        inst_nr = data.get('instnr', '')

        Org = self.env['myschool.org']

        if org_id:
            org = Org.browse(org_id)
        else:
            org = Org.search([
                ('name_short', '=', org_name),
                ('inst_nr', '=', inst_nr),
                ('is_active', '=', True)
            ], limit=1)

        if not org:
            _logger.warning(f'Org not found for DEACT')
            changes.append(f"Org not found - nothing to deactivate")
            return {'success': True, 'changes': '\n'.join(changes)}

        try:
            self._deactivate_org(org)
            changes.append(f"Deactivated org: {org.name} (ID: {org.id})")
            return {'success': True, 'changes': '\n'.join(changes)}
        except Exception as e:
            self._log_error('BETASK-591', f'Error deactivating org: {str(e)}')
            raise

    # =========================================================================
    # DB ROLE TASK PROCESSORS
    # =========================================================================
    
    @api.model
    def process_db_role_add(self, task):
        """Process DB ROLE ADD task."""
        _logger.info(f'Processing DB_ROLE_ADD: {task.name}')
        changes = []
        data = self._parse_task_data(task.data)

        if not data:
            return False

        Role = self.env['myschool.role']

        try:
            new_role = Role.create(data)
            _logger.info(f'Created role: {new_role.name}')
            changes.append(f"Created role: {new_role.name} (ID: {new_role.id})")
            return {'success': True, 'changes': '\n'.join(changes)}
        except Exception as e:
            self._log_error('BETASK-600', f'Error creating role: {str(e)}')
            raise

    @api.model
    def process_db_role_upd(self, task):
        """Process DB ROLE UPD task."""
        _logger.info(f'Processing DB_ROLE_UPD: {task.name}')
        changes = []
        data = self._parse_task_data(task.data)
        changes.append("Role update - no changes implemented yet")
        return {'success': True, 'changes': '\n'.join(changes)}

    # =========================================================================
    # DB PROPRELATION TASK PROCESSORS
    # =========================================================================

    @api.model
    def process_db_proprelation_add(self, task):
        """
        Process DB PROPRELATION ADD task - Create new PropRelation (PPSBR).

        Creates a PPSBR record linking Person-Period-School-BackendRole.
        After creating PPSBR records, determines the Person's position in Org tree.

        Expected data structure:
        {
            "personId": "uuid",
            "person_db_id": 123,
            "instNr": "011007",
            "orgId": 456,
            "roleCode": "00000255",
            "roleName": "ict-coordinator",
            "roleId": 789,
            "periodId": 10,
            "assignment": { ... }
        }
        """
        _logger.info(f'Processing DB_PROPRELATION_ADD: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-700', f'No data in task {task.name}')
            return False

        try:
            PropRelation = self.env['myschool.proprelation']
            PropRelationType = self.env['myschool.proprelation.type']
            Person = self.env['myschool.person']
            Org = self.env['myschool.org']
            Role = self.env['myschool.role']
            Period = self.env['myschool.period']
            
            # -----------------------------------------------------------------
            # Step 1: Get Person
            # -----------------------------------------------------------------
            person_id = data.get('person_db_id')
            person_uuid = data.get('personId')
            
            if person_id:
                person = Person.browse(person_id)
            elif person_uuid:
                person = Person.search([('sap_person_uuid', '=', person_uuid)], limit=1)
            else:
                self._log_error('BETASK-701', f'No person identifier in task {task.name}')
                return False
            
            if not person or not person.exists():
                self._log_error('BETASK-702', f'Person not found for task {task.name}')
                return False
            
            # -----------------------------------------------------------------
            # Step 2: Get School Org
            # -----------------------------------------------------------------
            org = None
            org_id = data.get('orgId')
            inst_nr = data.get('instNr')
            
            if org_id:
                org = Org.browse(org_id)
            elif inst_nr:
                org = Org.search([
                    ('inst_nr', '=', inst_nr),
                    ('is_active', '=', True),
                    ('org_type_id.name', '=', 'SCHOOL')
                ], limit=1)
                if not org:
                    org = Org.search([
                        ('inst_nr', '=', inst_nr),
                        ('is_active', '=', True)
                    ], limit=1)
            
            # -----------------------------------------------------------------
            # Step 3: Get Backend Role
            # Two scenarios:
            # A) roleId provided WITHOUT roleCode: roleId is already a Backend Role (e.g., EMPLOYEE)
            # B) roleCode provided: it's a SAP Role shortname, need SR-BR lookup for Backend Role
            # -----------------------------------------------------------------
            backend_role = None
            role_id = data.get('roleId')
            role_code = data.get('roleCode')  # SAP Role shortname (optional)
            role_name = data.get('roleName')  # Role name

            _logger.debug(f'[PPSBR] Role lookup - roleId: {role_id}, roleCode: {role_code}, roleName: {role_name}')

            # Scenario A: roleId provided without roleCode - assume it's already a Backend Role
            if role_id and not role_code:
                backend_role = Role.browse(role_id)
                if backend_role and backend_role.exists():
                    _logger.info(f'[PPSBR] Using Backend Role directly: {backend_role.name} (ID: {backend_role.id})')
                else:
                    self._log_error('BETASK-703', f'Role with ID {role_id} not found. Task: {task.name}')
                    return False

            # Scenario B: roleCode provided - find SAP Role, then lookup Backend Role via SR-BR
            elif role_code:
                # Find the SAP Role
                sap_role = Role.search([('shortname', '=', role_code)], limit=1)

                if not sap_role:
                    _logger.warning(f'[PPSBR] SAP Role not found for roleCode={role_code}')
                    self._log_error('BETASK-703', f'SAP Role not found for roleCode={role_code}. Task: {task.name}')
                    return False

                _logger.debug(f'[PPSBR] Found SAP Role: {sap_role.name} (shortname: {sap_role.shortname}, ID: {sap_role.id})')

                # Find Backend Role via SR-BR relation
                sr_br_type = PropRelationType.search([
                    ('name', '=', self.PROPRELATION_TYPE_SR_BR)
                ], limit=1)

                if sr_br_type:
                    sr_br_relation = PropRelation.search([
                        ('proprelation_type_id', '=', sr_br_type.id),
                        ('is_active', '=', True),
                        ('id_role_parent', '!=', False),
                        '|',
                        ('id_role', '=', sap_role.id),
                        ('id_role_child', '=', sap_role.id)
                    ], limit=1)

                    if sr_br_relation and sr_br_relation.id_role_parent:
                        backend_role = sr_br_relation.id_role_parent
                        _logger.info(
                            f'[PPSBR] Found Backend Role via SR-BR: {backend_role.name} (ID: {backend_role.id}) '
                            f'for SAP Role {sap_role.name} (ID: {sap_role.id})'
                        )
                    else:
                        self._log_error(
                            'BETASK-703',
                            f'No SR-BR relation found for SAP Role {sap_role.name} (roleCode={role_code}). '
                            f'Please ensure SR-BR mapping exists. Task: {task.name}'
                        )
                        return False
                else:
                    _logger.warning(f'[PPSBR] SR-BR PropRelationType not found!')
                    self._log_error('BETASK-703', f'SR-BR PropRelationType not found. Task: {task.name}')
                    return False

            # Fallback: try to find by roleName
            elif role_name:
                backend_role = Role.search([('name', '=', role_name)], limit=1)
                if backend_role:
                    _logger.info(f'[PPSBR] Found Role by name: {backend_role.name} (ID: {backend_role.id})')
                else:
                    self._log_error('BETASK-703', f'Role not found for roleName={role_name}. Task: {task.name}')
                    return False
            else:
                self._log_error('BETASK-703', f'No role identifier in task {task.name}')
                return False

            role_to_use = backend_role
            
            # -----------------------------------------------------------------
            # Step 4: Get Period (optional)
            # -----------------------------------------------------------------
            period = None
            period_id = data.get('periodId')
            
            if period_id:
                period = Period.browse(period_id)
            else:
                period = Period.search([('is_active', '=', True)], limit=1)
            
            # -----------------------------------------------------------------
            # Step 5: Get PPSBR PropRelationType
            # -----------------------------------------------------------------
            ppsbr_type = PropRelationType.search([
                ('name', '=', self.PROPRELATION_TYPE_PPSBR)
            ], limit=1)
            
            if not ppsbr_type:
                ppsbr_type = PropRelationType.create({
                    'name': self.PROPRELATION_TYPE_PPSBR,
                    'usage': 'Person-Period-School-BackendRole relation',
                    'is_active': True
                })
            
            # -----------------------------------------------------------------
            # Step 6: Check if PPSBR already exists
            # -----------------------------------------------------------------
            search_domain = [
                ('id_person', '=', person.id),
                ('proprelation_type_id', '=', ppsbr_type.id),
                ('is_active', '=', True)
            ]
            if org:
                search_domain.append(('id_org', '=', org.id))
            if role_to_use:
                search_domain.append(('id_role', '=', role_to_use.id))
            if period:
                search_domain.append(('id_period', '=', period.id))
            
            existing = PropRelation.search(search_domain, limit=1)
            
            if existing:
                _logger.info(f'PPSBR PropRelation already exists for {person.name}')
                self._update_person_tree_position(person)
                changes.append(f"PPSBR already exists for {person.name}")
                changes.append(f"Updated PERSON-TREE position")
                return {'success': True, 'changes': '\n'.join(changes)}
            
            # -----------------------------------------------------------------
            # Step 7: Create PPSBR PropRelation with standardized name
            # -----------------------------------------------------------------
            # Build standardized name using build_proprelation_name
            name_kwargs = {'id_person': person, 'id_role': role_to_use}
            if org:
                name_kwargs['id_org'] = org
            if period:
                name_kwargs['id_period'] = period
            
            relation_name = build_proprelation_name(self.PROPRELATION_TYPE_PPSBR, **name_kwargs)
            
            proprel_vals = {
                'name': relation_name,
                'proprelation_type_id': ppsbr_type.id,
                'id_person': person.id,
                'id_role': role_to_use.id,  # This is the BACKEND Role
                'is_active': True,
                'is_organisational': True,
                'automatic_sync': True,
                'start_date': fields.Datetime.now(),
            }
            
            if org:
                proprel_vals['id_org'] = org.id
                proprel_vals['id_org_parent'] = org.id
            
            if period:
                proprel_vals['id_period'] = period.id
            
            # Note: We do NOT store the SAP Role in PPSBR
            # The PPSBR only contains the Backend Role in id_role
            # The SAP Role mapping is maintained separately in SR-BR relations
            
            if role_to_use and hasattr(role_to_use, 'priority'):
                proprel_vals['priority'] = role_to_use.priority
            
            new_proprel = PropRelation.create(proprel_vals)
            _logger.info(f'Created PPSBR PropRelation: {relation_name} (ID: {new_proprel.id}), Backend Role: {role_to_use.name}')
            changes.append(f"Created PPSBR: {relation_name} (ID: {new_proprel.id})")
            changes.append(f"Person: {person.name}")
            changes.append(f"Backend Role: {role_to_use.name}")
            if org:
                changes.append(f"Org: {org.name}")
            if period:
                changes.append(f"Period: {period.name}")

            # -----------------------------------------------------------------
            # Step 8: Update Person's position in Org tree
            # -----------------------------------------------------------------
            self._update_person_tree_position(person)
            changes.append(f"Updated PERSON-TREE position")

            return {'success': True, 'changes': '\n'.join(changes)}

        except Exception as e:
            self._log_error('BETASK-709', f'Error creating PropRelation: {str(e)}')
            raise

    @api.model
    def process_db_proprelation_upd(self, task):
        """Process DB PROPRELATION UPD task - Update existing PropRelation."""
        _logger.info(f'Processing DB_PROPRELATION_UPD: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-710', f'No data in task {task.name}')
            return False

        try:
            PropRelation = self.env['myschool.proprelation']
            
            proprel_id = data.get('proprelation_id')
            
            if proprel_id:
                proprel = PropRelation.browse(proprel_id)
            else:
                Person = self.env['myschool.person']
                Org = self.env['myschool.org']
                Role = self.env['myschool.role']
                
                person_uuid = data.get('personId')
                inst_nr = data.get('instNr')
                role_code = data.get('roleCode')
                
                person = Person.search([('sap_person_uuid', '=', person_uuid)], limit=1) if person_uuid else None
                org = Org.search([('inst_nr', '=', inst_nr), ('is_active', '=', True)], limit=1) if inst_nr else None
                role = Role.search([('shortname', '=', role_code)], limit=1) if role_code else None
                
                search_domain = [('is_active', '=', True)]
                if person:
                    search_domain.append(('id_person', '=', person.id))
                if org:
                    search_domain.append(('id_org', '=', org.id))
                if role:
                    search_domain.append(('id_role', '=', role.id))
                
                proprel = PropRelation.search(search_domain, limit=1)
            
            if not proprel or not proprel.exists():
                self._log_error('BETASK-711', f'PropRelation not found for task {task.name}')
                return False
            
            updates = data.get('updates', {})
            update_vals = {}
            
            if 'priority' in updates:
                update_vals['priority'] = updates['priority']
            
            if 'is_administrative' in updates:
                update_vals['is_administrative'] = updates['is_administrative']
            
            if 'is_master' in updates:
                update_vals['is_master'] = updates['is_master']
            
            if update_vals:
                proprel.write(update_vals)
                _logger.info(f'Updated PropRelation: {proprel.name}')
                changes.append(f"Updated PropRelation: {proprel.name} (ID: {proprel.id})")
                changes.append(f"Updated fields: {', '.join(update_vals.keys())}")
            else:
                changes.append(f"No updates needed for PropRelation: {proprel.name}")

            # Always recalculate tree position after PPSBR update
            ppsbr_type = PropRelationType.search([
                ('name', '=', self.PROPRELATION_TYPE_PPSBR)
            ], limit=1)

            if proprel.id_person and ppsbr_type and proprel.proprelation_type_id.id == ppsbr_type.id:
                _logger.info(f'[TREE-POS] PPSBR updated, recalculating tree position for {proprel.id_person.name}')
                self._update_person_tree_position(proprel.id_person)
                changes.append(f"Recalculated PERSON-TREE for {proprel.id_person.name}")

            return {'success': True, 'changes': '\n'.join(changes)}

        except Exception as e:
            self._log_error('BETASK-719', f'Error updating PropRelation: {str(e)}')
            raise

    @api.model
    def process_db_proprelation_deact(self, task):
        """
        Process DB PROPRELATION DEACT task - Deactivate PropRelation.

        After deactivating a PPSBR, recalculates the Person's tree position.
        """
        _logger.info(f'Processing DB_PROPRELATION_DEACT: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-720', f'No data in task {task.name}')
            return False

        try:
            PropRelation = self.env['myschool.proprelation']
            PropRelationType = self.env['myschool.proprelation.type']
            Person = self.env['myschool.person']
            
            proprel_id = data.get('proprelation_id')
            proprel = None
            person = None
            
            if proprel_id:
                proprel = PropRelation.browse(proprel_id)
                if proprel and proprel.id_person:
                    person = proprel.id_person
            else:
                Org = self.env['myschool.org']
                Role = self.env['myschool.role']
                
                person_uuid = data.get('personId')
                inst_nr = data.get('instNr')
                role_code = data.get('roleCode')
                
                if person_uuid:
                    person = Person.search([('sap_person_uuid', '=', person_uuid)], limit=1)
                
                org = Org.search([('inst_nr', '=', inst_nr), ('is_active', '=', True)], limit=1) if inst_nr else None
                role = Role.search([('shortname', '=', role_code)], limit=1) if role_code else None
                
                search_domain = [('is_active', '=', True)]
                if person:
                    search_domain.append(('id_person', '=', person.id))
                if org:
                    search_domain.append(('id_org', '=', org.id))
                if role:
                    search_domain.append(('id_role', '=', role.id))
                
                proprel = PropRelation.search(search_domain, limit=1)
            
            if not proprel or not proprel.exists():
                _logger.warning(f'PropRelation not found for DEACT - may already be deactivated')
                changes.append("PropRelation not found - may already be deactivated")
                return {'success': True, 'changes': '\n'.join(changes)}

            if not proprel.is_active:
                _logger.info(f'PropRelation already inactive: {proprel.name}')
                changes.append(f"PropRelation already inactive: {proprel.name}")
                return {'success': True, 'changes': '\n'.join(changes)}

            if not person and proprel.id_person:
                person = proprel.id_person

            proprel.write({'is_active': False})
            reason = data.get('reason', 'Deactivated by sync')
            _logger.info(f'Deactivated PropRelation: {proprel.name}, reason: {reason}')
            changes.append(f"Deactivated PropRelation: {proprel.name} (ID: {proprel.id})")
            changes.append(f"Reason: {reason}")

            # Recalculate Person's tree position if this was a PPSBR
            ppsbr_type = PropRelationType.search([
                ('name', '=', self.PROPRELATION_TYPE_PPSBR)
            ], limit=1)

            if person and ppsbr_type and proprel.proprelation_type_id.id == ppsbr_type.id:
                _logger.info(f'PPSBR deactivated, recalculating tree position for {person.name}')
                self._update_person_tree_position(person)
                changes.append(f"Recalculated PERSON-TREE for {person.name}")

            # Check if person should be deactivated (no more active proprelations)
            # This check runs for ALL proprelation types, not just PPSBR
            # Only auto-deactivate persons with automatic_sync=True
            if person and person.is_active and person.automatic_sync:
                remaining_active_proprels = PropRelation.search([
                    ('id_person', '=', person.id),
                    ('is_active', '=', True)
                ])

                _logger.info(f'Remaining active proprelations for {person.name}: {len(remaining_active_proprels)}')

                if not remaining_active_proprels:
                    _logger.info(f'No active proprelations left for {person.name} - deactivating person')
                    changes.append(f"No active proprelations remaining - deactivating person")

                    # Skip manual audit for backend task processing
                    person_ctx = person.with_context(skip_manual_audit=True)

                    # Create ODOO-PERSON-DEACT task if person has Odoo user
                    if person.odoo_user_id:
                        odoo_task_data = {
                            'person_id': person.id,
                            'personId': person.sap_person_uuid,
                            'reason': 'No active proprelations'
                        }
                        self._create_betask_internal(
                            'ODOO', 'PERSON', 'DEACT',
                            json.dumps(odoo_task_data),
                            None
                        )
                        _logger.info(f'Created ODOO-PERSON-DEACT task for {person.name}')
                        changes.append(f"Created ODOO-PERSON-DEACT task")

                    # Only deactivate the person, NOT their other proprelations
                    person_ctx.write({'is_active': False})
                    _logger.info(f"Deactivated person {person.name}")
                    changes.append(f"Person {person.name} deactivated")

            return {'success': True, 'changes': '\n'.join(changes)}

        except Exception as e:
            self._log_error('BETASK-729', f'Error deactivating PropRelation: {str(e)}')
            raise

    # =========================================================================
    # PERSON TREE POSITION - WITH DEBUG LOGGING
    # =========================================================================

    def _update_person_tree_position(self, person) -> bool:
        """
        Determine and update the Person's position in the Org tree.
        
        Logic:
        1. Get all active PPSBR records for the person
        2. Order by role priority (lowest number = highest priority)
        3. If multiple roles have same priority, use alphabetically first
           and create a sysevent for admin review
        4. Find the corresponding Org via BRSO PropRelation
        5. Create/update PERSON-TREE PropRelation
        
        @param person: Person record
        @return: True if successful
        """
        _logger.info(f'========== START: Updating Org tree position for person: {person.name} (ID: {person.id}) ==========')
        
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        
        try:
            # -----------------------------------------------------------------
            # Step 1: Get PPSBR PropRelationType
            # -----------------------------------------------------------------
            _logger.debug(f'[TREE-POS] Step 1: Looking for PPSBR PropRelationType...')
            
            ppsbr_type = PropRelationType.search([
                ('name', '=', self.PROPRELATION_TYPE_PPSBR)
            ], limit=1)
            
            if not ppsbr_type:
                _logger.warning(f'[TREE-POS] PPSBR PropRelationType not found! Constant value: {self.PROPRELATION_TYPE_PPSBR}')
                _logger.debug(f'[TREE-POS] Available PropRelationTypes: {PropRelationType.search([]).mapped("name")}')
                return False
            
            _logger.debug(f'[TREE-POS] Found PPSBR type: ID={ppsbr_type.id}, name={ppsbr_type.name}')
            
            # -----------------------------------------------------------------
            # Step 2: Get all active PPSBR records for this person
            # -----------------------------------------------------------------
            _logger.debug(f'[TREE-POS] Step 2: Searching PPSBR records for person {person.id}...')
            
            search_domain = [
                ('id_person', '=', person.id),
                ('proprelation_type_id', '=', ppsbr_type.id),
                ('is_active', '=', True),
                ('id_role', '!=', False)
            ]
            _logger.debug(f'[TREE-POS] Search domain: {search_domain}')
            
            ppsbr_records = PropRelation.search(search_domain)
            
            _logger.info(f'[TREE-POS] Found {len(ppsbr_records)} PPSBR records for {person.name}')
            
            if not ppsbr_records:
                _logger.info(f'[TREE-POS] No active PPSBR records found - checking if PERSON-TREE should be deactivated')

                # Deactivate any existing active PERSON-TREE proprelations for this person
                person_tree_type = PropRelationType.search([
                    ('name', '=', self.PROPRELATION_TYPE_PERSON_TREE)
                ], limit=1)

                if person_tree_type:
                    existing_tree_records = PropRelation.search([
                        ('id_person', '=', person.id),
                        ('proprelation_type_id', '=', person_tree_type.id),
                        ('is_active', '=', True)
                    ])

                    if existing_tree_records:
                        for tree_record in existing_tree_records:
                            _logger.info(
                                f'[TREE-POS] Deactivating PERSON-TREE {tree_record.id} for {person.name} '
                                f'(no active PPSBR relations remaining)'
                            )
                            tree_record.write({'is_active': False})
                        _logger.info(f'[TREE-POS] Deactivated {len(existing_tree_records)} PERSON-TREE record(s)')
                    else:
                        _logger.debug(f'[TREE-POS] No active PERSON-TREE records to deactivate')
                else:
                    _logger.debug(f'[TREE-POS] PERSON-TREE type not found - nothing to deactivate')

                return True
            
            # Log all found PPSBR records
            for idx, ppsbr in enumerate(ppsbr_records):
                _logger.debug(
                    f'[TREE-POS] PPSBR #{idx + 1}: '
                    f'ID={ppsbr.id}, '
                    f'name={ppsbr.name}, '
                    f'role={ppsbr.id_role.name if ppsbr.id_role else "None"} (ID: {ppsbr.id_role.id if ppsbr.id_role else "None"}), '
                    f'org={ppsbr.id_org.name if ppsbr.id_org else "None"} (ID: {ppsbr.id_org.id if ppsbr.id_org else "None"}), '
                    f'period={ppsbr.id_period.name if ppsbr.id_period else "None"}, '
                    f'priority={ppsbr.priority}'
                )
            
            # -----------------------------------------------------------------
            # Step 3: Build list with priorities and sort
            # -----------------------------------------------------------------
            _logger.debug(f'[TREE-POS] Step 3: Building priority list and sorting...')
            
            ppsbr_with_priority = []
            
            for ppsbr in ppsbr_records:
                role = ppsbr.id_role
                if role:
                    priority = ppsbr.priority
                    if priority is None or priority == 0:
                        priority = getattr(role, 'priority', None)
                    if priority is None or priority == 0:
                        priority = 9999
                    
                    role_name = role.name or ''
                    
                    _logger.debug(
                        f'[TREE-POS] Processing PPSBR {ppsbr.id}: '
                        f'role={role_name}, '
                        f'ppsbr.priority={ppsbr.priority}, '
                        f'role.priority={getattr(role, "priority", "N/A")}, '
                        f'final_priority={priority}'
                    )
                    
                    ppsbr_with_priority.append((ppsbr, role, priority, role_name))
                else:
                    _logger.warning(f'[TREE-POS] PPSBR {ppsbr.id} has no role - skipping')
            
            if not ppsbr_with_priority:
                _logger.warning(f'[TREE-POS] No PPSBR records with valid roles for {person.name}')
                return True
            
            _logger.debug(f'[TREE-POS] Before sorting - {len(ppsbr_with_priority)} records:')
            for ppsbr, role, priority, role_name in ppsbr_with_priority:
                _logger.debug(f'[TREE-POS]   - {role_name}: priority={priority}')
            
            # Sort by priority (ascending), then by role name (alphabetically)
            ppsbr_with_priority.sort(key=lambda x: (x[2], x[3]))
            
            _logger.debug(f'[TREE-POS] After sorting:')
            for ppsbr, role, priority, role_name in ppsbr_with_priority:
                _logger.debug(f'[TREE-POS]   - {role_name}: priority={priority}')
            
            # -----------------------------------------------------------------
            # Step 4: Check for same priority conflicts
            # -----------------------------------------------------------------
            _logger.debug(f'[TREE-POS] Step 4: Checking for priority conflicts...')
            
            highest_priority = ppsbr_with_priority[0][2]
            same_priority_records = [x for x in ppsbr_with_priority if x[2] == highest_priority]
            
            _logger.debug(f'[TREE-POS] Highest priority value: {highest_priority}')
            _logger.debug(f'[TREE-POS] Records with highest priority: {len(same_priority_records)}')
            
            if len(same_priority_records) > 1:
                role_names = [x[3] for x in same_priority_records]
                warning_msg = (
                    f'Person {person.name} has {len(same_priority_records)} roles with same priority {highest_priority}: '
                    f'{", ".join(role_names)}. Using alphabetically first: {role_names[0]}. '
                    f'Please review and adjust role priorities if needed.'
                )
                
                _logger.warning(f'[TREE-POS] PRIORITY CONFLICT: {warning_msg}')
                
                self._log_event('PROPREL-PRIORITY', warning_msg)
            
            # Select the winner
            selected_ppsbr, selected_role, selected_priority, selected_role_name = ppsbr_with_priority[0]
            
            _logger.info(
                f'[TREE-POS] SELECTED: role={selected_role_name} (ID: {selected_role.id}), '
                f'priority={selected_priority}, ppsbr_id={selected_ppsbr.id}'
            )
            
            # -----------------------------------------------------------------
            # Step 5: Find Org via BRSO PropRelation
            # NOTE: BRSO relations are ALWAYS linked to Backend Roles, never SAP Roles.
            # The id_role in PPSBR should already be a Backend Role.
            # -----------------------------------------------------------------
            _logger.debug(f'[TREE-POS] Step 5: Looking for BRSO PropRelationType...')
            
            brso_type = PropRelationType.search([
                ('name', '=', self.PROPRELATION_TYPE_BRSO)
            ], limit=1)
            
            target_org = None
            
            if brso_type:
                _logger.debug(f'[TREE-POS] Found BRSO type: ID={brso_type.id}')
                
                # Validate: Check if selected_role is a Backend Role (optional safety check)
                # Backend Roles typically have role_type_id.name = 'BACKEND'
                if selected_role.role_type_id:
                    role_type_name = selected_role.role_type_id.name
                    if role_type_name and role_type_name.upper() == 'SAP':
                        _logger.warning(
                            f'[TREE-POS] WARNING: selected_role {selected_role.name} appears to be a SAP Role '
                            f'(role_type={role_type_name}). BRSO lookup may fail. '
                            f'PPSBR.id_role should contain Backend Roles, not SAP Roles!'
                        )
                    else:
                        _logger.debug(f'[TREE-POS] Role type: {role_type_name}')
                
                # Search BRSO using the Backend Role from PPSBR
                brso_search_domain = [
                    ('id_role', '=', selected_role.id),
                    ('proprelation_type_id', '=', brso_type.id),
                    ('is_active', '=', True),
                    ('id_org', '!=', False)
                ]
                _logger.debug(f'[TREE-POS] BRSO search domain: {brso_search_domain}')
                
                brso_relation = PropRelation.search(brso_search_domain, limit=1)
                
                if brso_relation:
                    target_org = brso_relation.id_org
                    _logger.info(
                        f'[TREE-POS] Found Org via BRSO: {target_org.name} (ID: {target_org.id}), '
                        f'brso_relation_id={brso_relation.id}'
                    )
                else:
                    _logger.warning(
                        f'[TREE-POS] No BRSO relation found for role {selected_role.name} (ID: {selected_role.id})'
                    )
                    all_brso = PropRelation.search([
                        ('proprelation_type_id', '=', brso_type.id),
                        ('is_active', '=', True)
                    ])
                    _logger.debug(f'[TREE-POS] All active BRSO relations ({len(all_brso)}):')
                    for brso in all_brso:
                        _logger.debug(
                            f'[TREE-POS]   - BRSO {brso.id}: '
                            f'role={brso.id_role.name if brso.id_role else "None"} (ID: {brso.id_role.id if brso.id_role else "None"}), '
                            f'org={brso.id_org.name if brso.id_org else "None"}'
                        )
            else:
                _logger.warning(f'[TREE-POS] BRSO PropRelationType not found! Constant value: {self.PROPRELATION_TYPE_BRSO}')
            
            # Fallback: use the Org from the PPSBR record
            if not target_org and selected_ppsbr.id_org:
                target_org = selected_ppsbr.id_org
                _logger.info(
                    f'[TREE-POS] FALLBACK: Using Org from PPSBR: {target_org.name} (ID: {target_org.id})'
                )
            
            if not target_org:
                _logger.warning(f'[TREE-POS] No target Org found for {person.name} - cannot create PERSON-TREE')
                return True
            
            # -----------------------------------------------------------------
            # Step 5b: If target_org is administrative, find non-administrative parent
            # -----------------------------------------------------------------
            if target_org.is_administrative:
                _logger.debug(
                    f'[TREE-POS] Target Org {target_org.name} is administrative (is_administrative=True), '
                    f'searching for non-administrative parent...'
                )
                
                original_org = target_org
                non_admin_org = self._find_non_administrative_parent_org(target_org)
                
                if non_admin_org:
                    _logger.info(
                        f'[TREE-POS] Found non-administrative parent: {non_admin_org.name} (ID: {non_admin_org.id}) '
                        f'for administrative org {original_org.name}'
                    )
                    target_org = non_admin_org
                else:
                    _logger.warning(
                        f'[TREE-POS] No non-administrative parent found for {original_org.name}, '
                        f'using original administrative org'
                    )
            
            # -----------------------------------------------------------------
            # Step 6: Get/Create PERSON-TREE PropRelationType
            # -----------------------------------------------------------------
            _logger.debug(f'[TREE-POS] Step 6: Looking for PERSON-TREE PropRelationType...')
            
            person_tree_type = PropRelationType.search([
                ('name', '=', self.PROPRELATION_TYPE_PERSON_TREE)
            ], limit=1)
            
            if not person_tree_type:
                _logger.info(f'[TREE-POS] PERSON-TREE type not found, creating...')
                person_tree_type = PropRelationType.create({
                    'name': self.PROPRELATION_TYPE_PERSON_TREE,
                    'usage': 'Defines Person position in Org tree',
                    'is_active': True
                })
                _logger.info(f'[TREE-POS] Created PERSON-TREE type: ID={person_tree_type.id}')
            else:
                _logger.debug(f'[TREE-POS] Found PERSON-TREE type: ID={person_tree_type.id}')
            
            # -----------------------------------------------------------------
            # Step 7: Find existing PERSON-TREE record
            # -----------------------------------------------------------------
            _logger.debug(f'[TREE-POS] Step 7: Searching for existing PERSON-TREE record...')
            
            existing_tree_domain = [
                ('id_person', '=', person.id),
                ('proprelation_type_id', '=', person_tree_type.id),
                ('is_active', '=', True)
            ]
            _logger.debug(f'[TREE-POS] Existing PERSON-TREE search domain: {existing_tree_domain}')
            
            existing_tree = PropRelation.search(existing_tree_domain, limit=1)
            
            if existing_tree:
                _logger.debug(
                    f'[TREE-POS] Found existing PERSON-TREE: ID={existing_tree.id}, '
                    f'current_org={existing_tree.id_org.name if existing_tree.id_org else "None"} '
                    f'(ID: {existing_tree.id_org.id if existing_tree.id_org else "None"})'
                )
            else:
                _logger.debug(f'[TREE-POS] No existing PERSON-TREE found')
            
            # -----------------------------------------------------------------
            # Step 8: Prepare values and Create/Update PERSON-TREE
            # -----------------------------------------------------------------
            _logger.debug(f'[TREE-POS] Step 8: Preparing PERSON-TREE values...')
            
            # Build standardized name
            name_kwargs = {
                'id_person': person,
                'id_org': target_org,
                'id_role': selected_role
            }
            if selected_ppsbr.id_period:
                name_kwargs['id_period'] = selected_ppsbr.id_period
            
            tree_name = build_proprelation_name(self.PROPRELATION_TYPE_PERSON_TREE, **name_kwargs)
            
            tree_vals = {
                'name': tree_name,
                'proprelation_type_id': person_tree_type.id,
                'id_person': person.id,
                'id_org': target_org.id,
                'id_org_parent': target_org.id,
                'id_role': selected_role.id,
                'is_active': True,
                'is_organisational': True,
                'automatic_sync': True,
            }
            
            if selected_ppsbr.id_period:
                tree_vals['id_period'] = selected_ppsbr.id_period.id
                _logger.debug(f'[TREE-POS] Including period: {selected_ppsbr.id_period.name}')
            
            _logger.debug(f'[TREE-POS] PERSON-TREE values: {tree_vals}')
            
            if existing_tree:
                old_org_id = existing_tree.id_org.id if existing_tree.id_org else None
                old_org_name = existing_tree.id_org.name if existing_tree.id_org else "None"
                
                if old_org_id != target_org.id:
                    _logger.info(
                        f'[TREE-POS] ORG CHANGED: {old_org_name} (ID: {old_org_id}) -> '
                        f'{target_org.name} (ID: {target_org.id})'
                    )
                else:
                    _logger.debug(f'[TREE-POS] Org unchanged: {target_org.name}')
                
                existing_tree.write(tree_vals)
                _logger.info(f'[TREE-POS] UPDATED PERSON-TREE: ID={existing_tree.id}')
            else:
                new_tree = PropRelation.create(tree_vals)
                _logger.info(f'[TREE-POS] CREATED PERSON-TREE: ID={new_tree.id}, {person.name} -> {target_org.name}')
            
            _logger.info(f'========== END: Successfully updated Org tree position for {person.name} ==========')
            return True
            
        except Exception as e:
            _logger.error(f'[TREE-POS] EXCEPTION: {str(e)}')
            _logger.error(f'[TREE-POS] Traceback: {traceback.format_exc()}')
            self._log_error('PROPREL-900', f'Error updating tree for {person.name}: {str(e)}')
            return False

    # =========================================================================
    # BATCH UPDATE TREE POSITIONS (Utility)
    # =========================================================================

    def _find_non_administrative_parent_org(self, org, max_depth: int = 10):
        """
        Find the first non-administrative parent Org in the hierarchy.
        
        Traverses up the Org tree (via id_org_parent or parent_id) until it finds
        an Org where is_administrative = False.
        
        @param org: Starting Org record (administrative)
        @param max_depth: Maximum levels to traverse (prevent infinite loops)
        @return: Non-administrative Org or None if not found
        """
        _logger.debug(f'[TREE-POS] Searching non-administrative parent for: {org.name}')
        
        current_org = org
        depth = 0
        
        while current_org and depth < max_depth:
            depth += 1
            
            # Try to get parent org (check common field names)
            parent_org = None
            
            # Try id_org_parent first (common in PropRelation-style models)
            if hasattr(current_org, 'id_org_parent') and current_org.id_org_parent:
                parent_org = current_org.id_org_parent
            # Try parent_id (common Odoo convention)
            elif hasattr(current_org, 'parent_id') and current_org.parent_id:
                parent_org = current_org.parent_id
            # Try org_parent_id
            elif hasattr(current_org, 'org_parent_id') and current_org.org_parent_id:
                parent_org = current_org.org_parent_id
            
            if not parent_org:
                _logger.debug(
                    f'[TREE-POS] No parent found for {current_org.name} at depth {depth}'
                )
                return None
            
            _logger.debug(
                f'[TREE-POS] Depth {depth}: Checking parent {parent_org.name} '
                f'(is_administrative={parent_org.is_administrative})'
            )
            
            # Check if this parent is non-administrative
            if not parent_org.is_administrative:
                _logger.debug(
                    f'[TREE-POS] Found non-administrative org at depth {depth}: {parent_org.name}'
                )
                return parent_org
            
            # Move up to next parent
            current_org = parent_org
        
        _logger.warning(
            f'[TREE-POS] Max depth ({max_depth}) reached without finding non-administrative parent'
        )
        return None

    def _update_all_person_tree_positions(self) -> dict:
        """
        Utility method to recalculate tree positions for all active persons.
        Can be called manually or via scheduled action.
        """
        _logger.info('Starting batch update of all person tree positions')
        
        Person = self.env['myschool.person']
        
        active_persons = Person.search([
            ('is_active', '=', True),
            ('automatic_sync', '=', True)
        ])
        
        results = {
            'total': len(active_persons),
            'success': 0,
            'errors': 0
        }
        
        for person in active_persons:
            try:
                if self._update_person_tree_position(person):
                    results['success'] += 1
                else:
                    results['errors'] += 1
            except Exception as e:
                results['errors'] += 1
                _logger.error(f'Error updating tree for {person.name}: {str(e)}')
        
        _logger.info(f'Batch update completed: {results}')
        return results

    # =========================================================================
    # DB RELATION TASK PROCESSORS (Student Relations)
    # =========================================================================
    
    @api.model
    def process_db_relation_add(self, task):
        """Process DB RELATION ADD task - Create relation for student."""
        _logger.info(f'Processing DB_RELATION_ADD: {task.name}')
        data = self._parse_task_data(task.data)
        # TODO: Implement based on your relation storage strategy
        return True
    
    @api.model
    def process_db_relation_upd(self, task):
        """Process DB RELATION UPD task."""
        _logger.info(f'Processing DB_RELATION_UPD: {task.name}')
        data = self._parse_task_data(task.data)
        # TODO: Implement relation update logic
        return True

    # =========================================================================
    # LDAP TASK PROCESSORS
    # =========================================================================

    def _get_ldap_config_for_task(self, task, org_id=None):
        """
        Get the LDAP server configuration for a task.

        Args:
            task: Backend task record
            org_id: Optional organization ID

        Returns:
            ldap.server.config record or raises error
        """
        ldap_config_model = self.env['myschool.ldap.server.config']

        if org_id:
            config = ldap_config_model.get_server_for_org(org_id)
        else:
            # Try to get from task data
            data = self._parse_task_data(task.data)
            if data and data.get('org_id'):
                config = ldap_config_model.get_server_for_org(data.get('org_id'))
            else:
                # Get first active config
                config = ldap_config_model.search([('active', '=', True)], limit=1)

        if not config:
            raise ValidationError(_('No LDAP server configured. Please configure an LDAP server first.'))

        return config

    @api.model
    def process_ldap_user_add(self, task):
        """
        Process LDAP USER ADD task - Create user in Active Directory.

        Expected data structure:
        {
            "person_id": 123,
            "org_id": 456,
            "dry_run": false
        }
        """
        _logger.info(f'Processing LDAP_USER_ADD: {task.name}')
        changes = []

        try:
            data = self._parse_task_data(task.data)
            if not data:
                raise ValidationError(_('Task data is missing or invalid'))

            person_id = data.get('person_id')
            org_id = data.get('org_id')
            dry_run = data.get('dry_run', False)

            if not person_id:
                raise ValidationError(_('person_id is required in task data'))

            person = self.env['myschool.person'].browse(person_id)
            if not person.exists():
                raise ValidationError(_('Person with id %s not found') % person_id)

            org = None
            if org_id:
                org = self.env['myschool.org'].browse(org_id)
                if not org.exists():
                    raise ValidationError(_('Organization with id %s not found') % org_id)

            # Get LDAP configuration
            config = self._get_ldap_config_for_task(task, org_id)
            changes.append(f"Using LDAP server: {config.name}")

            # Call LDAP service
            ldap_service = self.env['myschool.ldap.service']
            result = ldap_service.create_user(config, person, org, dry_run=dry_run)

            if result.get('success'):
                changes.append(f"User created: {result.get('dn', 'N/A')}")
                changes.append(result.get('message', ''))
                task.write({'changes': '\n'.join(changes)})
                return True
            else:
                raise ValidationError(result.get('message', 'Unknown error'))

        except Exception as e:
            _logger.exception(f'LDAP_USER_ADD failed: {task.name}')
            changes.append(f"ERROR: {str(e)}")
            task.write({'changes': '\n'.join(changes)})
            raise

    @api.model
    def process_ldap_user_upd(self, task):
        """
        Process LDAP USER UPD task - Update user in Active Directory.

        Expected data structure:
        {
            "person_id": 123,
            "org_id": 456,
            "dry_run": false
        }
        """
        _logger.info(f'Processing LDAP_USER_UPD: {task.name}')
        changes = []

        try:
            data = self._parse_task_data(task.data)
            if not data:
                raise ValidationError(_('Task data is missing or invalid'))

            person_id = data.get('person_id')
            org_id = data.get('org_id')
            dry_run = data.get('dry_run', False)

            if not person_id:
                raise ValidationError(_('person_id is required in task data'))

            person = self.env['myschool.person'].browse(person_id)
            if not person.exists():
                raise ValidationError(_('Person with id %s not found') % person_id)

            org = None
            if org_id:
                org = self.env['myschool.org'].browse(org_id)

            # Get LDAP configuration
            config = self._get_ldap_config_for_task(task, org_id)
            changes.append(f"Using LDAP server: {config.name}")

            # Call LDAP service
            ldap_service = self.env['myschool.ldap.service']
            result = ldap_service.update_user(config, person, org, dry_run=dry_run)

            if result.get('success'):
                changes.append(f"User updated: {result.get('dn', 'N/A')}")
                changes.append(result.get('message', ''))
                task.write({'changes': '\n'.join(changes)})
                return True
            else:
                raise ValidationError(result.get('message', 'Unknown error'))

        except Exception as e:
            _logger.exception(f'LDAP_USER_UPD failed: {task.name}')
            changes.append(f"ERROR: {str(e)}")
            task.write({'changes': '\n'.join(changes)})
            raise

    @api.model
    def process_ldap_user_deact(self, task):
        """
        Process LDAP USER DEACT task - Deactivate user in Active Directory.

        Expected data structure:
        {
            "person_id": 123,
            "dry_run": false
        }
        """
        _logger.info(f'Processing LDAP_USER_DEACT: {task.name}')
        changes = []

        try:
            data = self._parse_task_data(task.data)
            if not data:
                raise ValidationError(_('Task data is missing or invalid'))

            person_id = data.get('person_id')
            dry_run = data.get('dry_run', False)

            if not person_id:
                raise ValidationError(_('person_id is required in task data'))

            person = self.env['myschool.person'].browse(person_id)
            if not person.exists():
                raise ValidationError(_('Person with id %s not found') % person_id)

            # Get LDAP configuration
            config = self._get_ldap_config_for_task(task, data.get('org_id'))
            changes.append(f"Using LDAP server: {config.name}")

            # Call LDAP service
            ldap_service = self.env['myschool.ldap.service']
            result = ldap_service.deactivate_user(config, person, dry_run=dry_run)

            if result.get('success'):
                changes.append(f"User deactivated: {result.get('dn', 'N/A')}")
                changes.append(result.get('message', ''))
                task.write({'changes': '\n'.join(changes)})
                return True
            else:
                raise ValidationError(result.get('message', 'Unknown error'))

        except Exception as e:
            _logger.exception(f'LDAP_USER_DEACT failed: {task.name}')
            changes.append(f"ERROR: {str(e)}")
            task.write({'changes': '\n'.join(changes)})
            raise

    @api.model
    def process_ldap_user_del(self, task):
        """
        Process LDAP USER DEL task - Delete user from Active Directory.

        Expected data structure:
        {
            "person_id": 123,
            "dry_run": false
        }
        """
        _logger.info(f'Processing LDAP_USER_DEL: {task.name}')
        changes = []

        try:
            data = self._parse_task_data(task.data)
            if not data:
                raise ValidationError(_('Task data is missing or invalid'))

            person_id = data.get('person_id')
            dry_run = data.get('dry_run', False)

            if not person_id:
                raise ValidationError(_('person_id is required in task data'))

            person = self.env['myschool.person'].browse(person_id)
            if not person.exists():
                raise ValidationError(_('Person with id %s not found') % person_id)

            # Get LDAP configuration
            config = self._get_ldap_config_for_task(task, data.get('org_id'))
            changes.append(f"Using LDAP server: {config.name}")

            # Call LDAP service
            ldap_service = self.env['myschool.ldap.service']
            result = ldap_service.delete_user(config, person, dry_run=dry_run)

            if result.get('success'):
                changes.append(f"User deleted: {result.get('dn', 'N/A')}")
                changes.append(result.get('message', ''))
                task.write({'changes': '\n'.join(changes)})
                return True
            else:
                raise ValidationError(result.get('message', 'Unknown error'))

        except Exception as e:
            _logger.exception(f'LDAP_USER_DEL failed: {task.name}')
            changes.append(f"ERROR: {str(e)}")
            task.write({'changes': '\n'.join(changes)})
            raise

    @api.model
    def process_ldap_group_add(self, task):
        """
        Process LDAP GROUP ADD task - Create group in Active Directory.

        Expected data structure:
        {
            "group_name": "MyGroup",
            "org_id": 456,
            "description": "Group description",
            "dry_run": false
        }
        """
        _logger.info(f'Processing LDAP_GROUP_ADD: {task.name}')
        changes = []

        try:
            data = self._parse_task_data(task.data)
            if not data:
                raise ValidationError(_('Task data is missing or invalid'))

            group_name = data.get('group_name')
            org_id = data.get('org_id')
            description = data.get('description')
            dry_run = data.get('dry_run', False)

            if not group_name:
                raise ValidationError(_('group_name is required in task data'))

            org = None
            if org_id:
                org = self.env['myschool.org'].browse(org_id)
                if not org.exists():
                    org = None

            # Get LDAP configuration
            config = self._get_ldap_config_for_task(task, org_id)
            changes.append(f"Using LDAP server: {config.name}")

            # Call LDAP service
            ldap_service = self.env['myschool.ldap.service']
            result = ldap_service.create_group(config, group_name, org, description, dry_run=dry_run)

            if result.get('success'):
                changes.append(f"Group created: {result.get('dn', 'N/A')}")
                changes.append(result.get('message', ''))
                task.write({'changes': '\n'.join(changes)})
                return True
            else:
                raise ValidationError(result.get('message', 'Unknown error'))

        except Exception as e:
            _logger.exception(f'LDAP_GROUP_ADD failed: {task.name}')
            changes.append(f"ERROR: {str(e)}")
            task.write({'changes': '\n'.join(changes)})
            raise

    @api.model
    def process_ldap_group_upd(self, task):
        """
        Process LDAP GROUP UPD task - Update group in Active Directory.

        Expected data structure:
        {
            "group_dn": "CN=MyGroup,OU=Groups,DC=school,DC=local",
            "changes": {"description": "New description"},
            "dry_run": false
        }
        """
        _logger.info(f'Processing LDAP_GROUP_UPD: {task.name}')
        changes_log = []

        try:
            data = self._parse_task_data(task.data)
            if not data:
                raise ValidationError(_('Task data is missing or invalid'))

            group_dn = data.get('group_dn')
            attribute_changes = data.get('changes', {})
            dry_run = data.get('dry_run', False)

            if not group_dn:
                raise ValidationError(_('group_dn is required in task data'))

            # Get LDAP configuration
            config = self._get_ldap_config_for_task(task, data.get('org_id'))
            changes_log.append(f"Using LDAP server: {config.name}")

            # Call LDAP service
            ldap_service = self.env['myschool.ldap.service']
            result = ldap_service.update_group(config, group_dn, attribute_changes, dry_run=dry_run)

            if result.get('success'):
                changes_log.append(f"Group updated: {group_dn}")
                changes_log.append(result.get('message', ''))
                task.write({'changes': '\n'.join(changes_log)})
                return True
            else:
                raise ValidationError(result.get('message', 'Unknown error'))

        except Exception as e:
            _logger.exception(f'LDAP_GROUP_UPD failed: {task.name}')
            changes_log.append(f"ERROR: {str(e)}")
            task.write({'changes': '\n'.join(changes_log)})
            raise

    @api.model
    def process_ldap_group_deact(self, task):
        """
        Process LDAP GROUP DEACT task - Deactivate group in Active Directory.

        Note: AD doesn't have native group deactivation. This task can be used
        to move the group to a disabled container or rename it with a prefix.

        Expected data structure:
        {
            "group_dn": "CN=MyGroup,OU=Groups,DC=school,DC=local",
            "dry_run": false
        }
        """
        _logger.info(f'Processing LDAP_GROUP_DEACT: {task.name}')
        changes = []

        try:
            data = self._parse_task_data(task.data)
            if not data:
                raise ValidationError(_('Task data is missing or invalid'))

            group_dn = data.get('group_dn')
            dry_run = data.get('dry_run', False)

            if not group_dn:
                raise ValidationError(_('group_dn is required in task data'))

            # Get LDAP configuration
            config = self._get_ldap_config_for_task(task, data.get('org_id'))
            changes.append(f"Using LDAP server: {config.name}")

            # For group deactivation, we rename by adding a prefix
            ldap_service = self.env['myschool.ldap.service']
            result = ldap_service.update_group(
                config,
                group_dn,
                {'description': 'DEACTIVATED - ' + (data.get('description', ''))},
                dry_run=dry_run
            )

            if result.get('success'):
                changes.append(f"Group deactivated: {group_dn}")
                changes.append(result.get('message', ''))
                task.write({'changes': '\n'.join(changes)})
                return True
            else:
                raise ValidationError(result.get('message', 'Unknown error'))

        except Exception as e:
            _logger.exception(f'LDAP_GROUP_DEACT failed: {task.name}')
            changes.append(f"ERROR: {str(e)}")
            task.write({'changes': '\n'.join(changes)})
            raise

    @api.model
    def process_ldap_group_del(self, task):
        """
        Process LDAP GROUP DEL task - Delete group from Active Directory.

        Expected data structure:
        {
            "group_dn": "CN=MyGroup,OU=Groups,DC=school,DC=local",
            "dry_run": false
        }
        """
        _logger.info(f'Processing LDAP_GROUP_DEL: {task.name}')
        changes = []

        try:
            data = self._parse_task_data(task.data)
            if not data:
                raise ValidationError(_('Task data is missing or invalid'))

            group_dn = data.get('group_dn')
            dry_run = data.get('dry_run', False)

            if not group_dn:
                raise ValidationError(_('group_dn is required in task data'))

            # Get LDAP configuration
            config = self._get_ldap_config_for_task(task, data.get('org_id'))
            changes.append(f"Using LDAP server: {config.name}")

            # Call LDAP service
            ldap_service = self.env['myschool.ldap.service']
            result = ldap_service.delete_group(config, group_dn, dry_run=dry_run)

            if result.get('success'):
                changes.append(f"Group deleted: {group_dn}")
                changes.append(result.get('message', ''))
                task.write({'changes': '\n'.join(changes)})
                return True
            else:
                raise ValidationError(result.get('message', 'Unknown error'))

        except Exception as e:
            _logger.exception(f'LDAP_GROUP_DEL failed: {task.name}')
            changes.append(f"ERROR: {str(e)}")
            task.write({'changes': '\n'.join(changes)})
            raise

    @api.model
    def process_ldap_groupmember_add(self, task):
        """
        Process LDAP GROUPMEMBER ADD task - Add member to group.

        Expected data structure:
        {
            "group_dn": "CN=MyGroup,OU=Groups,DC=school,DC=local",
            "member_dn": "CN=JohnDoe,OU=Users,DC=school,DC=local",
            OR
            "person_id": 123,
            "dry_run": false
        }
        """
        _logger.info(f'Processing LDAP_GROUPMEMBER_ADD: {task.name}')
        changes = []

        try:
            data = self._parse_task_data(task.data)
            if not data:
                raise ValidationError(_('Task data is missing or invalid'))

            group_dn = data.get('group_dn')
            member_dn = data.get('member_dn')
            person_id = data.get('person_id')
            dry_run = data.get('dry_run', False)

            if not group_dn:
                raise ValidationError(_('group_dn is required in task data'))

            # Get LDAP configuration
            config = self._get_ldap_config_for_task(task, data.get('org_id'))
            changes.append(f"Using LDAP server: {config.name}")

            ldap_service = self.env['myschool.ldap.service']

            # If member_dn not provided, find it from person_id
            if not member_dn and person_id:
                person = self.env['myschool.person'].browse(person_id)
                if not person.exists():
                    raise ValidationError(_('Person with id %s not found') % person_id)
                member_dn = ldap_service._find_user_dn(config, person)
                if not member_dn:
                    raise ValidationError(_('User not found in LDAP: %s') % person.name)

            if not member_dn:
                raise ValidationError(_('member_dn or person_id is required in task data'))

            # Call LDAP service
            result = ldap_service.add_group_member(config, group_dn, member_dn, dry_run=dry_run)

            if result.get('success'):
                changes.append(f"Member added to group: {member_dn}")
                changes.append(result.get('message', ''))
                task.write({'changes': '\n'.join(changes)})
                return True
            else:
                raise ValidationError(result.get('message', 'Unknown error'))

        except Exception as e:
            _logger.exception(f'LDAP_GROUPMEMBER_ADD failed: {task.name}')
            changes.append(f"ERROR: {str(e)}")
            task.write({'changes': '\n'.join(changes)})
            raise

    @api.model
    def process_ldap_groupmember_remove(self, task):
        """
        Process LDAP GROUPMEMBER REMOVE task - Remove member from group.

        Expected data structure:
        {
            "group_dn": "CN=MyGroup,OU=Groups,DC=school,DC=local",
            "member_dn": "CN=JohnDoe,OU=Users,DC=school,DC=local",
            OR
            "person_id": 123,
            "dry_run": false
        }
        """
        _logger.info(f'Processing LDAP_GROUPMEMBER_REMOVE: {task.name}')
        changes = []

        try:
            data = self._parse_task_data(task.data)
            if not data:
                raise ValidationError(_('Task data is missing or invalid'))

            group_dn = data.get('group_dn')
            member_dn = data.get('member_dn')
            person_id = data.get('person_id')
            dry_run = data.get('dry_run', False)

            if not group_dn:
                raise ValidationError(_('group_dn is required in task data'))

            # Get LDAP configuration
            config = self._get_ldap_config_for_task(task, data.get('org_id'))
            changes.append(f"Using LDAP server: {config.name}")

            ldap_service = self.env['myschool.ldap.service']

            # If member_dn not provided, find it from person_id
            if not member_dn and person_id:
                person = self.env['myschool.person'].browse(person_id)
                if not person.exists():
                    raise ValidationError(_('Person with id %s not found') % person_id)
                member_dn = ldap_service._find_user_dn(config, person)
                if not member_dn:
                    raise ValidationError(_('User not found in LDAP: %s') % person.name)

            if not member_dn:
                raise ValidationError(_('member_dn or person_id is required in task data'))

            # Call LDAP service
            result = ldap_service.remove_group_member(config, group_dn, member_dn, dry_run=dry_run)

            if result.get('success'):
                changes.append(f"Member removed from group: {member_dn}")
                changes.append(result.get('message', ''))
                task.write({'changes': '\n'.join(changes)})
                return True
            else:
                raise ValidationError(result.get('message', 'Unknown error'))

        except Exception as e:
            _logger.exception(f'LDAP_GROUPMEMBER_REMOVE failed: {task.name}')
            changes.append(f"ERROR: {str(e)}")
            task.write({'changes': '\n'.join(changes)})
            raise

    # =========================================================================
    # ODOO PERSON TASK PROCESSORS (User/Employee Management)
    # =========================================================================

    @api.model
    def process_odoo_person_add(self, task):
        """
        Process ODOO PERSON ADD task - Create Odoo User and HR Employee.
        
        Expected data structure:
        {
            "person_id": 123,
            "personId": "uuid",
            "name": "Demeyer, Mark",
            "first_name": "Mark",
            "email": "mark.demeyer@school.be",
            "login": "mark.demeyer"
        }
        """
        _logger.info(f'Processing ODOO_PERSON_ADD: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-800', f'No data in task {task.name}')
            return False

        try:
            # Skip manual audit for backend task processing
            Person = self.env['myschool.person'].with_context(skip_manual_audit=True)
            ResUsers = self.env['res.users']

            # Check if hr module is installed
            hr_installed = 'hr.employee' in self.env
            HrEmployee = self.env['hr.employee'] if hr_installed else None

            # Get the myschool.person record
            person_id = data.get('person_id')
            person_uuid = data.get('personId')

            if person_id:
                person = Person.browse(person_id)
            elif person_uuid:
                person = Person.search([('sap_person_uuid', '=', person_uuid)], limit=1)
            else:
                self._log_error('BETASK-801', f'No person identifier in task {task.name}')
                return False
            
            if not person or not person.exists():
                self._log_error('BETASK-802', f'Person not found for task {task.name}')
                return False
            
            # Check if already has Odoo user
            if person.odoo_user_id:
                _logger.info(f'Person {person.name} already has Odoo user: {person.odoo_user_id.login}')
                # Still sync group memberships
                self._sync_person_group_memberships(person)
                changes.append(f"Person {person.name} already has Odoo user: {person.odoo_user_id.login}")
                changes.append("Synced group memberships")
                return {'success': True, 'changes': '\n'.join(changes)}
            
            # Prepare user data
            email = data.get('email') or person.email_cloud or person.email_private
            login = data.get('login') or email or self._generate_login(person)
            
            if not login:
                self._log_error('BETASK-803', f'Cannot determine login for person {person.name}')
                return False
            
            # Check if user with this login already exists (include archived users)
            existing_user = ResUsers.with_context(active_test=False).search([('login', '=', login)], limit=1)
            
            if existing_user:
                _logger.info(f'User with login {login} already exists, linking to person')
                person.write({'odoo_user_id': existing_user.id})
                changes.append(f"Linked existing Odoo user: {existing_user.login} (ID: {existing_user.id})")

                # Reactivate user if archived
                if not existing_user.active:
                    existing_user.with_context(active_test=False).write({'active': True})
                    _logger.info(f'Reactivated archived Odoo user: {existing_user.login}')
                    changes.append(f"Reactivated archived Odoo user: {existing_user.login}")

                # Link HR employee if exists, hr module installed, AND person is EMPLOYEE type
                is_employee_type = (
                    person.person_type_id and
                    person.person_type_id.name and
                    person.person_type_id.name.upper() == 'EMPLOYEE'
                )

                if hr_installed and is_employee_type:
                    existing_employee = HrEmployee.with_context(active_test=False).search([('user_id', '=', existing_user.id)], limit=1)
                    if existing_employee:
                        person.write({'odoo_employee_id': existing_employee.id})
                        _logger.info(f'Linked existing HR Employee: {existing_employee.name}')
                        changes.append(f"Linked existing HR Employee: {existing_employee.name}")
                        # Reactivate employee if archived
                        if not existing_employee.active:
                            existing_employee.with_context(active_test=False).write({'active': True})
                            _logger.info(f'Reactivated archived HR Employee: {existing_employee.name}')
                            changes.append(f"Reactivated archived HR Employee: {existing_employee.name}")

                # Sync group memberships
                self._sync_person_group_memberships(person)
                changes.append("Synced group memberships")
                return {'success': True, 'changes': '\n'.join(changes)}
            
            # Create new Odoo user with person's password if available
            user_vals = {
                'name': person.name or f"{data.get('first_name', '')} {data.get('name', '')}".strip(),
                'login': login,
                'email': email,
                'active': True,
            }

            # Use the person's stored password if available
            if person.password:
                user_vals['password'] = person.password

            new_user = ResUsers.create(user_vals)
            _logger.info(f'Created Odoo user: {new_user.login} (ID: {new_user.id})')
            changes.append(f"Created Odoo user: {new_user.login} (ID: {new_user.id})")

            # Link user to person
            person.write({'odoo_user_id': new_user.id})
            changes.append(f"Linked to person: {person.name}")
            
            # Create HR Employee only for EMPLOYEE person types (not for students)
            is_employee_type = (
                person.person_type_id and 
                person.person_type_id.name and 
                person.person_type_id.name.upper() == 'EMPLOYEE'
            )
            
            if hr_installed and is_employee_type:
                HrEmployee = self.env['hr.employee']
                
                employee_name = person.name
                if person.first_name:
                    last_name = person.name.split(',')[0].strip() if ',' in person.name else person.name
                    employee_name = f"{person.first_name} {last_name}"
                
                employee_vals = {
                    'name': employee_name,
                    'user_id': new_user.id,
                    'work_email': email,
                    'active': True,
                }
                
                # Add company_id if available (required for visibility in some Odoo setups)
                if self.env.company:
                    employee_vals['company_id'] = self.env.company.id
                
                new_employee = HrEmployee.create(employee_vals)
                _logger.info(f'Created HR Employee: {new_employee.name} (ID: {new_employee.id}, company_id: {new_employee.company_id.id if new_employee.company_id else None})')
                changes.append(f"Created HR Employee: {new_employee.name} (ID: {new_employee.id})")

                # Link employee to person
                person.write({'odoo_employee_id': new_employee.id})
            elif not hr_installed:
                _logger.info('HR module not installed - skipping HR Employee creation')
                changes.append("HR module not installed - skipped HR Employee creation")
            elif not is_employee_type:
                person_type_name = person.person_type_id.name if person.person_type_id else 'None'
                _logger.info(f'Person type is {person_type_name} (not EMPLOYEE) - skipping HR Employee creation')
                changes.append(f"Person type {person_type_name} - skipped HR Employee creation")

            # Sync group memberships based on roles
            self._sync_person_group_memberships(person)
            changes.append("Synced group memberships")

            return {'success': True, 'changes': '\n'.join(changes)}

        except Exception as e:
            self._log_error('BETASK-809', f'Error creating Odoo user: {str(e)}')
            _logger.exception(f'Exception in process_odoo_person_add')
            raise

    @api.model
    def process_odoo_person_upd(self, task):
        """
        Process ODOO PERSON UPD task - Update Odoo User and HR Employee.
        
        Expected data structure:
        {
            "person_id": 123,
            "personId": "uuid",
            "name": "Demeyer, Mark",
            "email": "mark.demeyer@school.be"
        }
        """
        _logger.info(f'Processing ODOO_PERSON_UPD: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-810', f'No data in task {task.name}')
            return False

        try:
            # Skip manual audit for backend task processing
            Person = self.env['myschool.person'].with_context(skip_manual_audit=True)

            # Get the myschool.person record
            person_id = data.get('person_id')
            person_uuid = data.get('personId')

            if person_id:
                person = Person.browse(person_id)
            elif person_uuid:
                person = Person.search([('sap_person_uuid', '=', person_uuid)], limit=1)
            else:
                self._log_error('BETASK-811', f'No person identifier in task {task.name}')
                return False

            if not person or not person.exists():
                self._log_error('BETASK-812', f'Person not found for task {task.name}')
                return False

            # Update Odoo User if exists
            if person.odoo_user_id:
                user_updates = {}
                
                # Update name
                if data.get('name') and person.odoo_user_id.name != data['name']:
                    user_updates['name'] = data['name']
                elif person.name and person.odoo_user_id.name != person.name:
                    user_updates['name'] = person.name
                
                # Update email
                email = data.get('email') or person.email_cloud
                if email and person.odoo_user_id.email != email:
                    user_updates['email'] = email
                
                if user_updates:
                    person.odoo_user_id.write(user_updates)
                    _logger.info(f'Updated Odoo user {person.odoo_user_id.login}: {user_updates}')
                    changes.append(f"Updated Odoo user {person.odoo_user_id.login}: {', '.join(user_updates.keys())}")
            
            # Update HR Employee if exists (and hr module installed)
            hr_installed = 'hr.employee' in self.env
            if hr_installed and person.odoo_employee_id:
                employee = person.odoo_employee_id

                if employee.exists():
                    employee_updates = {}
                    
                    # Update name
                    employee_name = person.name
                    if person.first_name:
                        last_name = person.name.split(',')[0].strip() if ',' in person.name else person.name
                        employee_name = f"{person.first_name} {last_name}"
                    
                    if employee_name and employee.name != employee_name:
                        employee_updates['name'] = employee_name
                    
                    # Update work email
                    email = data.get('email') or person.email_cloud
                    if email and employee.work_email != email:
                        employee_updates['work_email'] = email
                    
                    if employee_updates:
                        employee.write(employee_updates)
                        _logger.info(f'Updated HR Employee {employee.name}')
                        changes.append(f"Updated HR Employee {employee.name}: {', '.join(employee_updates.keys())}")

            # Sync group memberships (roles may have changed)
            self._sync_person_group_memberships(person)
            changes.append("Synced group memberships")

            if not changes:
                changes.append(f"No updates needed for {person.name}")

            return {'success': True, 'changes': '\n'.join(changes)}

        except Exception as e:
            self._log_error('BETASK-819', f'Error updating Odoo user: {str(e)}')
            raise

    @api.model
    def process_odoo_person_deact(self, task):
        """
        Process ODOO PERSON DEACT task - Deactivate Odoo User and HR Employee.
        
        Expected data structure:
        {
            "person_id": 123,
            "personId": "uuid",
            "reason": "Employee deactivated"
        }
        """
        _logger.info(f'Processing ODOO_PERSON_DEACT: {task.name}')
        changes = []

        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-820', f'No data in task {task.name}')
            return False

        try:
            # Skip manual audit for backend task processing
            Person = self.env['myschool.person'].with_context(skip_manual_audit=True)

            # Get the myschool.person record
            person_id = data.get('person_id')
            person_uuid = data.get('personId')

            if person_id:
                person = Person.browse(person_id)
            elif person_uuid:
                person = Person.search([('sap_person_uuid', '=', person_uuid)], limit=1)
            else:
                self._log_error('BETASK-821', f'No person identifier in task {task.name}')
                return False

            if not person or not person.exists():
                _logger.warning(f'Person not found for DEACT task - may already be deleted')
                changes.append("Person not found - may already be deleted")
                return {'success': True, 'changes': '\n'.join(changes)}

            reason = data.get('reason', 'Deactivated by sync')

            # IMPORTANT: Deactivate HR Employee FIRST (before User, due to FK constraint)
            hr_installed = 'hr.employee' in self.env
            if hr_installed and person.odoo_employee_id:
                employee = person.odoo_employee_id
                if employee.exists() and employee.active:
                    employee.write({'active': False})
                    _logger.info(f'Archived HR Employee: {employee.name}, reason: {reason}')
                    changes.append(f"Archived HR Employee: {employee.name}")

            # Remove from all Odoo groups
            if person.odoo_user_id:
                self._remove_user_from_all_role_groups(person.odoo_user_id)
                changes.append("Removed user from all role groups")

            # Deactivate Odoo User (after HR Employee is archived)
            if person.odoo_user_id and person.odoo_user_id.active:
                person.odoo_user_id.write({'active': False})
                _logger.info(f'Archived Odoo user: {person.odoo_user_id.login}, reason: {reason}')
                changes.append(f"Archived Odoo user: {person.odoo_user_id.login}")

            changes.append(f"Reason: {reason}")
            return {'success': True, 'changes': '\n'.join(changes)}

        except Exception as e:
            self._log_error('BETASK-829', f'Error deactivating Odoo user: {str(e)}')
            raise

    # =========================================================================
    # ODOO GROUPMEMBER TASK PROCESSORS
    # =========================================================================

    @api.model
    def process_odoo_groupmember_add(self, task):
        """
        Process ODOO GROUPMEMBER ADD task - Add user to Odoo group.
        
        Expected data structure:
        {
            "person_id": 123,
            "user_id": 456,
            "group_id": 789,
            "role_id": 10,
            "role_name": "ict-coordinator"
        }
        """
        _logger.info(f'Processing ODOO_GROUPMEMBER_ADD: {task.name}')
        
        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-830', f'No data in task {task.name}')
            return False
        
        try:
            ResUsers = self.env['res.users']
            ResGroups = self.env['res.groups']
            Person = self.env['myschool.person']
            
            # Get user
            user_id = data.get('user_id')
            person_id = data.get('person_id')
            
            user = None
            if user_id:
                user = ResUsers.browse(user_id)
            elif person_id:
                person = Person.browse(person_id)
                if person and person.odoo_user_id:
                    user = person.odoo_user_id
            
            if not user or not user.exists():
                self._log_error('BETASK-831', f'User not found for task {task.name}')
                return False
            
            # Get group
            group_id = data.get('group_id')
            if not group_id:
                self._log_error('BETASK-832', f'No group_id in task {task.name}')
                return False
            
            group = ResGroups.browse(group_id)
            if not group or not group.exists():
                self._log_error('BETASK-833', f'Group {group_id} not found')
                return False
            
            # Check if user already in group
            if group in user.group_ids:
                _logger.info(f'User {user.login} already in group {group.full_name}')
                return True
            
            # Add user to group
            user.write({'group_ids': [(4, group.id)]})
            _logger.info(f'Added user {user.login} to group {group.full_name}')
            
            return True
            
        except Exception as e:
            self._log_error('BETASK-839', f'Error adding user to group: {str(e)}')
            raise

    @api.model
    def process_odoo_groupmember_remove(self, task):
        """
        Process ODOO GROUPMEMBER REMOVE task - Remove user from Odoo group.
        
        Expected data structure:
        {
            "person_id": 123,
            "user_id": 456,
            "group_id": 789,
            "role_id": 10,
            "reason": "Role removed"
        }
        """
        _logger.info(f'Processing ODOO_GROUPMEMBER_REMOVE: {task.name}')
        
        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-840', f'No data in task {task.name}')
            return False
        
        try:
            ResUsers = self.env['res.users']
            ResGroups = self.env['res.groups']
            Person = self.env['myschool.person']
            
            # Get user
            user_id = data.get('user_id')
            person_id = data.get('person_id')
            
            user = None
            if user_id:
                user = ResUsers.browse(user_id)
            elif person_id:
                person = Person.browse(person_id)
                if person and person.odoo_user_id:
                    user = person.odoo_user_id
            
            if not user or not user.exists():
                _logger.warning(f'User not found for GROUPMEMBER REMOVE - may already be deleted')
                return True
            
            # Get group
            group_id = data.get('group_id')
            if not group_id:
                self._log_error('BETASK-841', f'No group_id in task {task.name}')
                return False
            
            group = ResGroups.browse(group_id)
            if not group or not group.exists():
                _logger.warning(f'Group {group_id} not found - may already be deleted')
                return True
            
            # Check if user in group
            if group not in user.group_ids:
                _logger.info(f'User {user.login} not in group {group.full_name}')
                return True
            
            # Remove user from group
            reason = data.get('reason', 'Removed by sync')
            user.write({'group_ids': [(3, group.id)]})
            _logger.info(f'Removed user {user.login} from group {group.full_name}, reason: {reason}')
            
            return True
            
        except Exception as e:
            self._log_error('BETASK-849', f'Error removing user from group: {str(e)}')
            raise

    # =========================================================================
    # ODOO INTEGRATION HELPER METHODS
    # =========================================================================

    def _generate_login(self, person) -> str:
        """
        Generate a login name for a person.
        
        @param person: myschool.person record
        @return: Generated login string
        """
        import re
        
        # Try email first
        if person.email_cloud:
            return person.email_cloud
        
        if person.email_private:
            return person.email_private
        
        # Generate from name
        first_name = person.first_name or ''
        last_name = person.name.split(',')[0].strip() if ',' in person.name else person.name
        
        if first_name and last_name:
            login = f"{first_name.lower()}.{last_name.lower()}"
            login = re.sub(r'[^a-z0-9.]', '', login)
            return login
        
        # Fallback to abbreviation or sap_ref
        if person.abbreviation:
            return person.abbreviation.lower()
        
        if person.sap_ref:
            return f"user_{person.sap_ref}"
        
        return f"user_{person.id}"

    def _sync_person_group_memberships(self, person):
        """
        Synchronize Odoo group memberships for a person based on their roles.
        
        Checks all active PPSBR PropRelations for the person, and for each role
        with has_odoo_group=True, ensures the user is in the corresponding Odoo group.
        Also removes user from groups for roles they no longer have.
        
        @param person: myschool.person record
        """
        if not person.odoo_user_id:
            _logger.debug(f'[GROUP-SYNC] Person {person.name} has no Odoo user - skipping group sync')
            return
        
        _logger.info(f'[GROUP-SYNC] Syncing group memberships for {person.name}')
        
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        Role = self.env['myschool.role']
        
        # Get PPSBR type
        ppsbr_type = PropRelationType.search([
            ('name', '=', self.PROPRELATION_TYPE_PPSBR)
        ], limit=1)
        
        if not ppsbr_type:
            _logger.warning('[GROUP-SYNC] PPSBR PropRelationType not found')
            return
        
        # Get all active PPSBR for this person
        active_ppsbr = PropRelation.search([
            ('id_person', '=', person.id),
            ('proprelation_type_id', '=', ppsbr_type.id),
            ('is_active', '=', True),
            ('id_role', '!=', False)
        ])
        
        # Collect roles with Odoo groups
        current_group_ids = set()
        
        for ppsbr in active_ppsbr:
            role = ppsbr.id_role
            if role and hasattr(role, 'has_odoo_group') and role.has_odoo_group and role.odoo_group_id:
                current_group_ids.add(role.odoo_group_id.id)
                _logger.debug(f'[GROUP-SYNC] Role {role.name} has group: {role.odoo_group_id.full_name}')
        
        # Get all roles that have Odoo groups (to know which groups are managed)
        managed_roles = Role.search([
            ('has_odoo_group', '=', True),
            ('odoo_group_id', '!=', False)
        ])
        managed_group_ids = set(managed_roles.mapped('odoo_group_id').ids)
        
        # Current user groups (only consider managed groups)
        user = person.odoo_user_id
        user_group_ids = set(user.group_ids.ids)
        user_managed_groups = user_group_ids & managed_group_ids
        
        _logger.debug(f'[GROUP-SYNC] Current managed groups: {user_managed_groups}')
        _logger.debug(f'[GROUP-SYNC] Should have groups: {current_group_ids}')
        
        # Groups to add
        groups_to_add = current_group_ids - user_managed_groups
        
        # Groups to remove
        groups_to_remove = user_managed_groups - current_group_ids
        
        # Create tasks for additions
        for group_id in groups_to_add:
            group = self.env['res.groups'].browse(group_id)
            task_data = {
                'person_id': person.id,
                'user_id': user.id,
                'group_id': group_id,
                'group_name': group.full_name,
            }
            self._create_betask_internal(
                'ODOO', 'GROUPMEMBER', 'ADD',
                json.dumps(task_data),
                None
            )
            _logger.info(f'[GROUP-SYNC] Created ADD task: {person.name} -> {group.full_name}')
        
        # Create tasks for removals
        for group_id in groups_to_remove:
            group = self.env['res.groups'].browse(group_id)
            task_data = {
                'person_id': person.id,
                'user_id': user.id,
                'group_id': group_id,
                'group_name': group.full_name,
                'reason': 'Role no longer active'
            }
            self._create_betask_internal(
                'ODOO', 'GROUPMEMBER', 'REMOVE',
                json.dumps(task_data),
                None
            )
            _logger.info(f'[GROUP-SYNC] Created REMOVE task: {person.name} <- {group.full_name}')

    def _remove_user_from_all_role_groups(self, user):
        """
        Remove user from all groups that are managed via roles.
        Called when deactivating a user.
        
        @param user: res.users record
        """
        Role = self.env['myschool.role']
        
        # Get all managed groups
        managed_roles = Role.search([
            ('has_odoo_group', '=', True),
            ('odoo_group_id', '!=', False)
        ])
        
        managed_group_ids = managed_roles.mapped('odoo_group_id').ids
        
        # Remove user from all managed groups
        for group_id in managed_group_ids:
            if group_id in user.group_ids.ids:
                user.write({'group_ids': [(3, group_id)]})
                _logger.info(f'Removed user {user.login} from group ID {group_id}')

    def _create_betask_internal(self, target: str, obj: str, action: str, data: str, data2: str = None):
        """
        Internal method to create a BeTask.
        
        @param target: Task target (DB, ODOO, LDAP, etc.)
        @param obj: Task object (PERSON, GROUPMEMBER, etc.)
        @param action: Task action (ADD, UPD, DEACT, REMOVE, etc.)
        @param data: JSON string with task data
        @param data2: Optional JSON string with additional data
        @return: Created BeTask record or None
        """
        BeTask = self.env['myschool.betask']
        BeTaskType = self.env['myschool.betask.type']
        
        task_type = BeTaskType.search([
            ('target', '=', target),
            ('object', '=', obj),
            ('action', '=', action)
        ], limit=1)
        
        if not task_type:
            _logger.warning(f'BeTaskType not found: {target}-{obj}-{action}')
            return None
        
        task_vals = {
            'name': f'{target}-{obj}-{action}-{fields.Datetime.now()}',
            'betasktype_id': task_type.id,
            'status': 'new',
            'data': data,
            'data2': data2,
        }
        
        return BeTask.create(task_vals)

    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    @api.model
    def _check_manual_tasks(self):
        """Check for pending manual tasks."""
        task_service = self.env['myschool.betask.service']
        return task_service.find_manual_tasks()
    
    @api.model
    def _log_event(self, code, message):
        """Log event to SysEvent."""
        try:
            sys_event_service = self.env['myschool.sys.event.service']
            sys_event_service.create_sys_event(
                code=code,
                data=message,
                log_to_screen=True,
                source='BE'
            )
        except Exception:
            _logger.info(f'SysEvent [{code}]: {message}')
    
    @api.model
    def _log_error(self, code, message, blocking=False):
        """Log error to SysEvent."""
        try:
            sys_event_service = self.env['myschool.sys.event.service']
            error_type = 'ERROR-BLOCKING' if blocking else 'ERROR-NONBLOCKING'
            sys_event_service.create_sys_error(
                code=code,
                data=message,
                error_type=error_type,
                log_to_screen=True,
                source='BE'
            )
        except Exception:
            _logger.error(f'SysError [{code}]: {message}')

    # =========================================================================
    # GENERIC PROPRELATION HELPERS
    # =========================================================================
    
    # Parameter name mapping: friendly names -> PropRelation field names
    PARAM_TO_FIELD_MAP = {
        # Org mappings
        'org': 'id_org', 'organization': 'id_org', 'id_org': 'id_org',
        'org_parent': 'id_org_parent', 'parent_org': 'id_org_parent', 'id_org_parent': 'id_org_parent',
        'org_child': 'id_org_child', 'child_org': 'id_org_child', 'id_org_child': 'id_org_child',
        # Role mappings
        'role': 'id_role', 'id_role': 'id_role',
        'role_parent': 'id_role_parent', 'parent_role': 'id_role_parent', 'id_role_parent': 'id_role_parent',
        'role_child': 'id_role_child', 'child_role': 'id_role_child', 'id_role_child': 'id_role_child',
        # Person mappings
        'person': 'id_person', 'id_person': 'id_person',
        'person_parent': 'id_person_parent', 'parent_person': 'id_person_parent', 'id_person_parent': 'id_person_parent',
        'person_child': 'id_person_child', 'child_person': 'id_person_child', 'id_person_child': 'id_person_child',
        # Period mappings
        'period': 'id_period', 'id_period': 'id_period',
        'period_parent': 'id_period_parent', 'parent_period': 'id_period_parent', 'id_period_parent': 'id_period_parent',
        'period_child': 'id_period_child', 'child_period': 'id_period_child', 'id_period_child': 'id_period_child',
        # Other fields
        'priority': 'priority', 'is_active': 'is_active', 'active': 'is_active',
    }

    def _translate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Translate friendly parameter names to PropRelation field names.
        
        @param params: Dict with friendly names (e.g., {'person': record, 'role': record})
        @return: Dict with field names (e.g., {'id_person': record, 'id_role': record})
        """
        translated = {}
        for key, value in params.items():
            field_name = self.PARAM_TO_FIELD_MAP.get(key, key)
            translated[field_name] = value
        return translated

    def _get_or_create_proprelation_type(self, type_name: str, usage: str = None):
        """
        Get or create a PropRelationType by name.
        
        @param type_name: Type name (e.g., 'PPSBR', 'BRSO', 'PERSON-TREE')
        @param usage: Optional usage description
        @return: PropRelationType record
        """
        PropRelationType = self.env['myschool.proprelation.type']
        
        rel_type = PropRelationType.search([('name', '=', type_name)], limit=1)
        
        if not rel_type:
            vals = {'name': type_name, 'is_active': True}
            if usage:
                vals['usage'] = usage
            rel_type = PropRelationType.create(vals)
            _logger.info(f'Created PropRelationType: {type_name}')
        
        return rel_type

    def _create_proprelation(
        self,
        type_name: str,
        auto_name: bool = True,
        **kwargs
    ):
        """
        Create a new PropRelation with standardized name.
        
        @param type_name: PropRelation type name (e.g., 'PPSBR', 'BRSO')
        @param auto_name: If True, generate standardized name automatically
        @param kwargs: Field values using friendly names:
            - person, person_parent, person_child
            - org, org_parent, org_child  
            - role, role_parent, role_child
            - period, period_parent, period_child
            - priority, is_active
        @return: Created PropRelation record
        
        Example:
            proprel = self._create_proprelation(
                'PPSBR',
                person=person_record,
                role=role_record,
                org=org_record,
                period=period_record,
                priority=10
            )
        """
        PropRelation = self.env['myschool.proprelation']
        
        # Get or create the type
        rel_type = self._get_or_create_proprelation_type(type_name)
        
        # Translate parameters to field names
        translated = self._translate_params(kwargs)
        
        # Build values dict
        vals = {
            'proprelation_type_id': rel_type.id,
            'is_active': True,
        }
        
        # Add translated fields, converting records to IDs
        name_kwargs = {}
        for field_name, value in translated.items():
            if field_name.startswith('id_'):
                # This is a relation field
                if value:
                    record_id = value.id if hasattr(value, 'id') else value
                    vals[field_name] = record_id
                    name_kwargs[field_name] = value  # Keep record for name building
            elif field_name in ('priority', 'is_active'):
                vals[field_name] = value
        
        # Generate name if auto_name
        if auto_name:
            vals['name'] = build_proprelation_name(type_name, **name_kwargs)
        elif 'name' in kwargs:
            vals['name'] = kwargs['name']
        else:
            vals['name'] = type_name
        
        # Create the record
        proprel = PropRelation.create(vals)
        _logger.info(f'Created PropRelation: {proprel.name} (ID: {proprel.id})')
        
        return proprel

    def _find_proprelation(
        self,
        type_name: str,
        active_only: bool = True,
        **kwargs
    ):
        """
        Find a PropRelation by type and field values.
        
        @param type_name: PropRelation type name
        @param active_only: If True, only search active records
        @param kwargs: Field values to match (friendly names allowed)
        @return: PropRelation record or None
        
        Example:
            proprel = self._find_proprelation(
                'PPSBR',
                person=person_record,
                role=role_record,
                org=org_record
            )
        """
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        
        rel_type = PropRelationType.search([('name', '=', type_name)], limit=1)
        if not rel_type:
            return None
        
        domain = [('proprelation_type_id', '=', rel_type.id)]
        
        if active_only:
            domain.append(('is_active', '=', True))
        
        translated = self._translate_params(kwargs)
        for field_name, value in translated.items():
            if field_name.startswith('id_') and value:
                record_id = value.id if hasattr(value, 'id') else value
                domain.append((field_name, '=', record_id))
        
        return PropRelation.search(domain, limit=1) or None

    def _find_or_create_proprelation(
        self,
        type_name: str,
        auto_name: bool = True,
        **kwargs
    ) -> tuple:
        """
        Find existing PropRelation or create new one.
        
        @param type_name: PropRelation type name
        @param auto_name: Generate standardized name if creating
        @param kwargs: Field values (friendly names allowed)
        @return: Tuple (PropRelation record, created: bool)
        
        Example:
            proprel, created = self._find_or_create_proprelation(
                'PPSBR',
                person=person_record,
                role=role_record
            )
        """
        # Try to find existing active
        existing = self._find_proprelation(type_name, active_only=True, **kwargs)
        if existing:
            return existing, False
        
        # Check for inactive that can be reactivated
        inactive = self._find_proprelation(type_name, active_only=False, **kwargs)
        if inactive and not inactive.is_active:
            # Reactivate and update name
            update_vals = {'is_active': True}
            if auto_name:
                translated = self._translate_params(kwargs)
                name_kwargs = {k: v for k, v in translated.items() if k.startswith('id_') and v}
                update_vals['name'] = build_proprelation_name(type_name, **name_kwargs)
            inactive.write(update_vals)
            _logger.info(f'Reactivated PropRelation: {inactive.name} (ID: {inactive.id})')
            return inactive, False
        
        # Create new
        new_proprel = self._create_proprelation(type_name, auto_name=auto_name, **kwargs)
        return new_proprel, True

    def _update_proprelation_name(self, proprel) -> bool:
        """
        Update the name of a PropRelation to the standardized format.
        
        @param proprel: PropRelation record
        @return: True if name was updated
        """
        if not proprel or not proprel.exists() or not proprel.proprelation_type_id:
            return False
        
        type_name = proprel.proprelation_type_id.name
        
        # Build kwargs from existing fields
        kwargs = {}
        field_names = [
            'id_org', 'id_org_parent', 'id_org_child',
            'id_role', 'id_role_parent', 'id_role_child',
            'id_person', 'id_person_parent', 'id_person_child',
            'id_period', 'id_period_parent', 'id_period_child',
        ]
        
        for field_name in field_names:
            if hasattr(proprel, field_name):
                value = getattr(proprel, field_name)
                if value:
                    kwargs[field_name] = value
        
        if kwargs:
            new_name = build_proprelation_name(type_name, **kwargs)
            if proprel.name != new_name:
                proprel.write({'name': new_name})
                _logger.debug(f'Updated PropRelation name: {new_name}')
                return True
        
        return False

    # =========================================================================
    # CRON JOB ENTRY POINT
    # =========================================================================
    
    @api.model
    def cron_process_tasks(self):
        """Entry point for scheduled task processing."""
        _logger.info('Cron job started: Processing backend tasks')
        
        try:
            results = self.process_all_pending()
            _logger.info(f'Cron job completed: {results}')
            return results
        except Exception as e:
            _logger.exception('Cron job failed')
            self._log_error('BETASK-999', f'Cron job failed: {str(e)}', blocking=True)
            return False
