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
import traceback
from datetime import datetime
from typing import Dict, Optional, Any, List

_logger = logging.getLogger(__name__)


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
    PROPRELATION_TYPE_ORG_TREE = 'OrgTree'


    # PERSON-TREE: Defines where a Person resides in the Org tree
    PROPRELATION_TYPE_PERSON_TREE = 'PERSON-TREE'
    
    # PPSBR: Person-Period-School-BackendRole relation
    PROPRELATION_TYPE_PPSBR = 'PPSBR'
    
    # SR-BR: SapRole to BackendRole mapping
    PROPRELATION_TYPE_SR_BR = 'SR-BR'
    
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
            'full_json_string': json.dumps(employee_json, ensure_ascii=False),
            'extra_field_1': inst_nr,
        }
        
        for json_key, odoo_field in self.EMPLOYEE_DETAILS_FIELD_MAP.items():
            value = employee_json.get(json_key)
            if value is not None and value != 'null':
                if isinstance(value, (dict, list)):
                    vals[odoo_field] = json.dumps(value, ensure_ascii=False)
                else:
                    vals[odoo_field] = str(value)
        
        hoofd_ambt = employee_json.get('hoofdAmbt')
        if hoofd_ambt and isinstance(hoofd_ambt, dict):
            vals['hoofd_ambt'] = hoofd_ambt.get('code', '')
        elif hoofd_ambt:
            vals['hoofd_ambt'] = str(hoofd_ambt)
        
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
            'full_json_string': json.dumps(full_data, ensure_ascii=False),
            'extra_field_1': inst_nr,
        }
        
        if student_json:
            for json_key, odoo_field in self.STUDENT_DETAILS_FIELD_MAP.items():
                value = student_json.get(json_key)
                if value is not None and value != 'null':
                    if isinstance(value, (dict, list)):
                        vals[odoo_field] = json.dumps(value, ensure_ascii=False)
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

    def _create_person_from_employee_json(self, employee_json: dict, inst_nr: str = ''):
        """Create a Person and PersonDetails record from employee JSON."""
        Person = self.env['myschool.person']
        PersonDetails = self.env['myschool.person.details']
        
        person_vals = self._map_employee_json_to_person_vals(employee_json)
        person_vals['is_active'] = True
        person_vals['automatic_sync'] = True
        
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
        
        return new_person

    def _update_person_from_employee_json(
        self, 
        person, 
        employee_json: dict, 
        inst_nr: str = '',
        action: str = 'UPDATE'
    ) -> bool:
        """Update a Person and PersonDetails record from employee JSON."""
        PersonDetails = self.env['myschool.person.details']
        
        person_vals = self._map_employee_json_to_person_vals(employee_json)
        
        if action == 'REACTIVATE':
            person_vals['is_active'] = True
            _logger.info(f"Reactivating employee {person.name}")
        
        person.write(person_vals)
        
        existing_details = PersonDetails.search([
            ('person_id', '=', person.id),
            ('extra_field_1', '=', inst_nr)
        ], limit=1)
        
        details_vals = self._map_employee_json_to_person_details_vals(
            employee_json,
            person.id,
            inst_nr
        )
        
        if existing_details:
            existing_details.write(details_vals)
            _logger.info(f"Updated PersonDetails for {person.name}, instNr {inst_nr}")
        else:
            PersonDetails.create(details_vals)
            _logger.info(f"Created new PersonDetails for {person.name}, instNr {inst_nr}")
        
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
        
        return True

    def _deactivate_person(self, person, data_json: dict = None, inst_nr: str = '') -> bool:
        """Deactivate a Person record and their PropRelations."""
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
                    'full_json_string': json.dumps(data_json, ensure_ascii=False)
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
        Person = self.env['myschool.person']
        PersonDetails = self.env['myschool.person.details']
        
        person_vals = self._map_student_json_to_person_vals(registration_json, student_json)
        
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
    ) -> bool:
        """Update a Person and PersonDetails record from student JSON."""
        PersonDetails = self.env['myschool.person.details']
        
        person_vals = self._map_student_json_to_person_vals(registration_json, student_json)
        
        if action == 'REACTIVATE':
            person_vals['is_active'] = True
            person_vals['reg_end_date'] = None
            _logger.info(f"Reactivating student {person.name}")
        
        person.write(person_vals)
        
        existing_details = PersonDetails.search([
            ('person_id', '=', person.id),
            ('extra_field_1', '=', inst_nr)
        ], limit=1)
        
        details_vals = self._map_student_json_to_person_details_vals(
            registration_json,
            student_json or {},
            person.id,
            inst_nr
        )
        
        if existing_details:
            existing_details.write(details_vals)
        else:
            PersonDetails.create(details_vals)
        
        return True

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

    def _update_org_from_json(self, org, org_json: dict) -> bool:
        """Update an Org record from JSON."""
        org_vals = self._map_org_json_to_org_vals(org_json)
        org.write(org_vals)
        _logger.info(f"Updated org {org.name}")
        return True

    def _deactivate_org(self, org) -> bool:
        """Deactivate an Org record."""
        org.write({'is_active': False})
        _logger.info(f"Deactivated org {org.name}")
        return True

    # =========================================================================
    # TASK REGISTRATION METHODS
    # =========================================================================
    
    @api.model
    def _register_task_success(self, task, result_data=None):
        """Mark task as successfully completed."""
        task.action_set_completed(result_data)
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
        """Process a single task."""
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
            
            if result:
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
            
            # LDAP handlers
            ('LDAP', 'EMPLOYEE', 'ADD'): self.process_ldap_employee_add,
            ('LDAP', 'EMPLOYEE', 'UPD'): self.process_ldap_employee_upd,
            ('LDAP', 'EMPLOYEE', 'DEACT'): self.process_ldap_employee_deact,
            ('LDAP', 'STUDENT', 'ADD'): self.process_ldap_student_add,
            ('LDAP', 'ORG', 'ADD'): self.process_ldap_org_add,
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
                return self._update_person_from_employee_json(existing, data, inst_nr, 'UPDATE')
        
        try:
            new_person = self._create_person_from_employee_json(data, inst_nr)
            return True
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
            return self._create_person_from_employee_json(data, inst_nr) is not None
        
        try:
            if action == 'REACTIVATE':
                return self._update_person_from_employee_json(person, data, inst_nr, 'REACTIVATE')
            elif action == 'ADD-DETAILS':
                return self._update_person_from_employee_json(person, data, inst_nr, 'UPDATE')
            else:
                return self._update_person_from_employee_json(person, data, inst_nr, 'UPDATE')
        except Exception as e:
            self._log_error('BETASK-521', f'Error updating employee: {str(e)}')
            raise
    
    @api.model
    def process_db_employee_deact(self, task):
        """Process DB EMPLOYEE DEACT task - Deactivate employee."""
        _logger.info(f'Processing DB_EMPLOYEE_DEACT: {task.name}')
        
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
            return True
        
        try:
            self._deactivate_person(person, data, inst_nr)
            return True
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
                return self._update_person_from_student_json(existing, data, data, inst_nr, 'UPDATE')
        
        try:
            new_person = self._create_person_from_student_json(data, data, inst_nr)
            return True
        except Exception as e:
            self._log_error('BETASK-541', f'Error creating student: {str(e)}')
            raise
    
    @api.model
    def process_db_student_upd(self, task):
        """Process DB STUDENT UPD task - Update existing student."""
        _logger.info(f'Processing DB_STUDENT_UPD: {task.name}')
        
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
            return self._create_person_from_student_json(data, data, inst_nr) is not None
        
        try:
            self._update_person_from_student_json(person, data, data, inst_nr, action)
            return True
        except Exception as e:
            self._log_error('BETASK-551', f'Error updating student: {str(e)}')
            raise
    
    @api.model
    def process_db_student_deact(self, task):
        """Process DB STUDENT DEACT task - Deactivate student."""
        _logger.info(f'Processing DB_STUDENT_DEACT: {task.name}')
        
        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-560', f'No data in task {task.name}')
            return False
        
        inst_nr = data.get('instelnr', '') or data.get('instNr', '')
        person_uuid = data.get('persoonId') or data.get('personId')
        
        Person = self.env['myschool.person']
        person = Person.search([('sap_person_uuid', '=', person_uuid)], limit=1)
        
        if not person:
            _logger.warning(f'Student {person_uuid} not found for DEACT')
            return True
        
        try:
            reg_end_date = data.get('regEndDate') or data.get('einddatum')
            if reg_end_date:
                parsed_date = self._parse_date_safe(reg_end_date)
                if parsed_date:
                    person.write({'reg_end_date': parsed_date.strftime('%Y-%m-%d')})
            
            self._deactivate_person(person, data, inst_nr)
            return True
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
            return self._update_org_from_json(existing, data)
        
        try:
            new_org = self._create_org_from_json(data)
            return True
        except Exception as e:
            self._log_error('BETASK-571', f'Error creating org: {str(e)}')
            raise
    
    @api.model
    def process_db_org_upd(self, task):
        """Process DB ORG UPD task - Update existing organization."""
        _logger.info(f'Processing DB_ORG_UPD: {task.name}')
        
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
            return self._create_org_from_json(data) is not None
        
        try:
            self._update_org_from_json(org, data)
            return True
        except Exception as e:
            self._log_error('BETASK-581', f'Error updating org: {str(e)}')
            raise
    
    @api.model
    def process_db_org_deact(self, task):
        """Process DB ORG DEACT task - Deactivate organization."""
        _logger.info(f'Processing DB_ORG_DEACT: {task.name}')
        
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
            return True
        
        try:
            self._deactivate_org(org)
            return True
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
        data = self._parse_task_data(task.data)
        
        if not data:
            return False
        
        Role = self.env['myschool.role']
        
        try:
            new_role = Role.create(data)
            _logger.info(f'Created role: {new_role.name}')
            return True
        except Exception as e:
            self._log_error('BETASK-600', f'Error creating role: {str(e)}')
            raise
    
    @api.model
    def process_db_role_upd(self, task):
        """Process DB ROLE UPD task."""
        _logger.info(f'Processing DB_ROLE_UPD: {task.name}')
        data = self._parse_task_data(task.data)
        # TODO: Implement role update logic
        return True

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
            # Step 3: Get Role (SAP Role -> Backend Role via SR-BR)
            # -----------------------------------------------------------------
            role = None
            be_role = None
            role_id = data.get('roleId')
            role_code = data.get('roleCode')
            
            if role_id:
                role = Role.browse(role_id)
            elif role_code:
                role = Role.search([('shortname', '=', role_code)], limit=1)
            
            # Find Backend Role via SR-BR relation
            if role:
                sr_br_type = PropRelationType.search([
                    ('name', '=', self.PROPRELATION_TYPE_SR_BR)
                ], limit=1)
                
                if sr_br_type:
                    sr_br_relation = PropRelation.search([
                        ('id_role', '=', role.id),
                        ('proprelation_type_id', '=', sr_br_type.id),
                        ('is_active', '=', True)
                    ], limit=1)
                    
                    if sr_br_relation and sr_br_relation.id_role_parent:
                        be_role = sr_br_relation.id_role_parent
                        _logger.info(f'Found Backend Role {be_role.name} for SAP Role {role.name}')
            
            role_to_use = be_role if be_role else role
            
            if not role_to_use:
                self._log_error('BETASK-703', f'No role found for task {task.name}')
                return False
            
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
                return True
            
            # -----------------------------------------------------------------
            # Step 7: Create PPSBR PropRelation
            # -----------------------------------------------------------------
            relation_name = f'{person.name} - {role_to_use.name}'
            if org:
                relation_name += f' - {org.name}'
            if period:
                relation_name += f' ({period.name})'
            
            proprel_vals = {
                'name': relation_name,
                'proprelation_type_id': ppsbr_type.id,
                'id_person': person.id,
                'id_role': role_to_use.id,
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
            
            if be_role and role:
                proprel_vals['id_role_child'] = role.id
            
            if role_to_use and hasattr(role_to_use, 'priority'):
                proprel_vals['priority'] = role_to_use.priority
            
            new_proprel = PropRelation.create(proprel_vals)
            _logger.info(f'Created PPSBR PropRelation: {relation_name} (ID: {new_proprel.id})')
            
            # -----------------------------------------------------------------
            # Step 8: Update Person's position in Org tree
            # -----------------------------------------------------------------
            self._update_person_tree_position(person)
            
            return True
            
        except Exception as e:
            self._log_error('BETASK-709', f'Error creating PropRelation: {str(e)}')
            raise

    @api.model
    def process_db_proprelation_upd(self, task):
        """Process DB PROPRELATION UPD task - Update existing PropRelation."""
        _logger.info(f'Processing DB_PROPRELATION_UPD: {task.name}')
        
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
            
            # Always recalculate tree position after PPSBR update
            ppsbr_type = PropRelationType.search([
                ('name', '=', self.PROPRELATION_TYPE_PPSBR)
            ], limit=1)
            
            if proprel.id_person and ppsbr_type and proprel.proprelation_type_id.id == ppsbr_type.id:
                _logger.info(f'[TREE-POS] PPSBR updated, recalculating tree position for {proprel.id_person.name}')
                self._update_person_tree_position(proprel.id_person)
            
            return True
            
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
                return True
            
            if not proprel.is_active:
                _logger.info(f'PropRelation already inactive: {proprel.name}')
                return True
            
            if not person and proprel.id_person:
                person = proprel.id_person
            
            proprel.write({'is_active': False})
            reason = data.get('reason', 'Deactivated by sync')
            _logger.info(f'Deactivated PropRelation: {proprel.name}, reason: {reason}')
            
            # Recalculate Person's tree position if this was a PPSBR
            ppsbr_type = PropRelationType.search([
                ('name', '=', self.PROPRELATION_TYPE_PPSBR)
            ], limit=1)
            
            if person and ppsbr_type and proprel.proprelation_type_id.id == ppsbr_type.id:
                _logger.info(f'PPSBR deactivated, recalculating tree position for {person.name}')
                self._update_person_tree_position(person)
            
            return True
            
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
                _logger.info(f'[TREE-POS] No PPSBR records found - nothing to do')
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
            # -----------------------------------------------------------------
            _logger.debug(f'[TREE-POS] Step 5: Looking for BRSO PropRelationType...')
            
            brso_type = PropRelationType.search([
                ('name', '=', self.PROPRELATION_TYPE_BRSO)
            ], limit=1)
            
            target_org = None
            
            if brso_type:
                _logger.debug(f'[TREE-POS] Found BRSO type: ID={brso_type.id}')
                
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
            
            tree_vals = {
                'name': f'{person.name} -> {target_org.name}',
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
    # LDAP TASK PROCESSORS (Placeholders)
    # =========================================================================
    
    @api.model
    def process_ldap_org_add(self, task):
        """Process LDAP ORG ADD task."""
        _logger.info(f'Processing LDAP_ORG_ADD: {task.name}')
        # TODO: Implement LDAP organization creation
        return True
    
    @api.model
    def process_ldap_employee_add(self, task):
        """Process LDAP EMPLOYEE ADD task."""
        _logger.info(f'Processing LDAP_EMPLOYEE_ADD: {task.name}')
        # TODO: Implement LDAP employee creation
        return True
    
    @api.model
    def process_ldap_employee_upd(self, task):
        """Process LDAP EMPLOYEE UPD task."""
        _logger.info(f'Processing LDAP_EMPLOYEE_UPD: {task.name}')
        # TODO: Implement LDAP employee update
        return True
    
    @api.model
    def process_ldap_employee_deact(self, task):
        """Process LDAP EMPLOYEE DEACT task."""
        _logger.info(f'Processing LDAP_EMPLOYEE_DEACT: {task.name}')
        # TODO: Implement LDAP employee deactivation
        return True
    
    @api.model
    def process_ldap_student_add(self, task):
        """Process LDAP STUDENT ADD task."""
        _logger.info(f'Processing LDAP_STUDENT_ADD: {task.name}')
        # TODO: Implement LDAP student creation
        return True

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
        
        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-800', f'No data in task {task.name}')
            return False
        
        try:
            Person = self.env['myschool.person']
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
                return True
            
            # Prepare user data
            email = data.get('email') or person.email_cloud or person.email_private
            login = data.get('login') or email or self._generate_login(person)
            
            if not login:
                self._log_error('BETASK-803', f'Cannot determine login for person {person.name}')
                return False
            
            # Check if user with this login already exists
            existing_user = ResUsers.search([('login', '=', login)], limit=1)
            
            if existing_user:
                _logger.info(f'User with login {login} already exists, linking to person')
                person.write({'odoo_user_id': existing_user.id})
                
                # Link HR employee if exists, hr module installed, AND person is EMPLOYEE type
                is_employee_type = (
                    person.person_type_id and 
                    person.person_type_id.name and 
                    person.person_type_id.name.upper() == 'EMPLOYEE'
                )
                
                if hr_installed and is_employee_type:
                    existing_employee = HrEmployee.search([('user_id', '=', existing_user.id)], limit=1)
                    if existing_employee:
                        person.write({'odoo_employee_id_int': existing_employee.id})
                        _logger.info(f'Linked existing HR Employee: {existing_employee.name}')
                
                # Sync group memberships
                self._sync_person_group_memberships(person)
                return True
            
            # Create new Odoo user (without password - Odoo will handle it)
            user_vals = {
                'name': person.name or f"{data.get('first_name', '')} {data.get('name', '')}".strip(),
                'login': login,
                'email': email,
                'active': True,
            }
            
            new_user = ResUsers.create(user_vals)
            _logger.info(f'Created Odoo user: {new_user.login} (ID: {new_user.id})')
            
            # Link user to person
            person.write({'odoo_user_id': new_user.id})
            
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
                
                # Link employee to person (using integer field)
                person.write({'odoo_employee_id_int': new_employee.id})
            elif not hr_installed:
                _logger.info('HR module not installed - skipping HR Employee creation')
            elif not is_employee_type:
                person_type_name = person.person_type_id.name if person.person_type_id else 'None'
                _logger.info(f'Person type is {person_type_name} (not EMPLOYEE) - skipping HR Employee creation')
            
            # Sync group memberships based on roles
            self._sync_person_group_memberships(person)
            
            return True
            
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
        
        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-810', f'No data in task {task.name}')
            return False
        
        try:
            Person = self.env['myschool.person']
            
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
            
            # Update HR Employee if exists (and hr module installed)
            hr_installed = 'hr.employee' in self.env
            if hr_installed and person.odoo_employee_id_int:
                HrEmployee = self.env['hr.employee']
                employee = HrEmployee.browse(person.odoo_employee_id_int)
                
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
            
            # Sync group memberships (roles may have changed)
            self._sync_person_group_memberships(person)
            
            return True
            
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
        
        data = self._parse_task_data(task.data)
        if not data:
            self._log_error('BETASK-820', f'No data in task {task.name}')
            return False
        
        try:
            Person = self.env['myschool.person']
            
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
                return True
            
            reason = data.get('reason', 'Deactivated by sync')
            
            # IMPORTANT: Deactivate HR Employee FIRST (before User, due to FK constraint)
            hr_installed = 'hr.employee' in self.env
            if hr_installed and person.odoo_employee_id_int:
                HrEmployee = self.env['hr.employee']
                employee = HrEmployee.browse(person.odoo_employee_id_int)
                if employee.exists() and employee.active:
                    employee.write({'active': False})
                    _logger.info(f'Archived HR Employee: {employee.name}, reason: {reason}')
            
            # Remove from all Odoo groups
            if person.odoo_user_id:
                self._remove_user_from_all_role_groups(person.odoo_user_id)
            
            # Deactivate Odoo User (after HR Employee is archived)
            if person.odoo_user_id and person.odoo_user_id.active:
                person.odoo_user_id.write({'active': False})
                _logger.info(f'Archived Odoo user: {person.odoo_user_id.login}, reason: {reason}')
            
            return True
            
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
