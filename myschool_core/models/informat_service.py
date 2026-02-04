# -*- coding: utf-8 -*-
"""
Informat Service for Odoo 19
============================

This service imports JSON data via API calls from Informat SAP,
stores retrieved data in files on the server, compares imported data
with data in the database, and creates BeTasks that will be processed
in a specific order.

Converted from Java syncsapImpl.java for myschool-core application.

@author: Converted to Odoo 19
@version: 0.1
@since: 2025-02-04
"""

import json
import logging
import os
import traceback
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class InformatService(models.AbstractModel):
    """
    Service class for synchronizing data from Informat SAP system.
    
    This service:
    - Retrieves data from the SAP via API calls
    - Stores retrieved data in JSON files on the server
    - Analyzes data and compares with database
    - Creates BeTasks for processing in specific order
    """
    _name = 'myschool.informat.service'
    _description = 'Informat SAP Synchronization Service'

    # =========================================================================
    # Configuration Constants
    # =========================================================================
    
    # Default paths (can be overridden by config)
    DEFAULT_STORAGE_PATH_DEV = 'storage/sapimport/dev'
    DEFAULT_STORAGE_PATH_PROD = 'storage/sapimport/prod'
    
    # API URLs
    IDENTITY_SERVER_URL = 'https://www.identityserver.be/connect/token'
    STUDENTS_API_URL = 'https://leerlingenapi.informatsoftware.be/1/students'
    EMPLOYEES_API_URL = 'https://personeelsapi.informatsoftware.be/employees'
    EMPLOYEE_ASSIGNMENTS_API_URL = 'https://personeelsapi.informatsoftware.be/employees/assignments'

    # =========================================================================
    # BeTask Configuration - ADJUST THESE TO MATCH YOUR MODEL!
    # =========================================================================
    
    # Model names
    BETASK_MODEL = 'myschool.betask'            # Change if your model is named differently
    BETASK_TYPE_MODEL = 'myschool.betask.type'  # Change if your model is named differently
    
    # Field names on BeTask model - ADJUST TO MATCH YOUR be_task.py!
    BETASK_NAME_FIELD = 'name'  # The Many2one field to BeTaskType
    BETASK_TYPE_FIELD = 'betasktype_id'   # The Many2one field to BeTaskType
    BETASK_STATUS_FIELD = 'status'          # The status/state field
    BETASK_DATA_FIELD = 'data'              # The JSON data field
    BETASK_DATA2_FIELD = 'data2'            # The secondary JSON data field
    
    # Field names on BeTaskType model - ADJUST TO MATCH YOUR be_task_type.py!
    BETASKTYPE_TARGET_FIELD = 'target'      # e.g., 'DB', 'LDAP', 'ALL', 'SYSTEM'
    BETASKTYPE_OBJECT_FIELD = 'object'      # e.g., 'STUDENT', 'EMPLOYEE', 'ORG'
    BETASKTYPE_ACTION_FIELD = 'action'      # e.g., 'ADD', 'UPD', 'DEACT'
    
    # Status values - ADJUST TO MATCH YOUR model's selection values!
    STATUS_NEW = 'new'                       # Could be: 'new', 'draft', 'pending'
    STATUS_COMPLETED = 'completed_ok'           # Could be: 'completed_ok', 'done'

    # =========================================================================
    # Storage Path Management
    # =========================================================================

    def _get_module_path(self) -> str:
        """
        Get the path to this module's directory.
        
        @return: Absolute path to the module directory
        """
        # Get the path of this file and navigate up to module root
        current_file = os.path.abspath(__file__)
        service_dir = os.path.dirname(current_file)
        module_dir = os.path.dirname(service_dir)
        return module_dir

    def _get_odoo_data_dir(self) -> str:
        """
        Get Odoo's data directory from configuration.
        
        @return: Path to Odoo data directory
        """
        from odoo import tools
        return tools.config.get('data_dir', '/var/lib/odoo')

    def _get_storage_path(self, dev_mode: bool = False) -> str:
        """
        Get the appropriate storage path based on mode.
        
        For development mode:
            - Uses module directory: {module_path}/storage/sapimport/dev
        
        For production mode:
            - Uses Odoo data directory: {data_dir}/storage/sapimport/prod
            - Or custom path from configuration
        
        @param dev_mode: If True, return dev path; if False, return prod path
        @return: Absolute path to storage directory
        """
        # Try to get path from configuration first
        try:
            Config = self.env.get('myschool.informat.service.config')
            if Config:
                config = Config.search([('active', '=', True)], limit=1)
                if config:
                    if dev_mode and config.storage_path_dev:
                        custom_path = config.storage_path_dev
                    elif not dev_mode and config.storage_path_prod:
                        custom_path = config.storage_path_prod
                    else:
                        custom_path = None
                    
                    # If custom path is absolute, use it directly
                    if custom_path and os.path.isabs(custom_path):
                        return custom_path
                    # If custom path is relative, resolve it
                    elif custom_path:
                        if dev_mode:
                            return os.path.join(self._get_module_path(), custom_path)
                        else:
                            return os.path.join(self._get_odoo_data_dir(), custom_path)
        except Exception as e:
            _logger.warning(f"Could not load storage path from config: {e}")
        
        # Fall back to default paths
        if dev_mode:
            # Dev files stored in module directory
            return os.path.join(self._get_module_path(), self.DEFAULT_STORAGE_PATH_DEV)
        else:
            # Prod files stored in Odoo data directory
            return os.path.join(self._get_odoo_data_dir(), self.DEFAULT_STORAGE_PATH_PROD)

    def _get_storage_path_for_students(self, dev_mode: bool = False) -> str:
        """
        Get storage path specifically for student files.
        Students have a subdirectory in dev mode.
        
        @param dev_mode: If True, return dev path with students subdirectory
        @return: Absolute path to students storage directory
        """
        base_path = self._get_storage_path(dev_mode)
        if dev_mode:
            return os.path.join(base_path, 'students')
        return base_path

    def _ensure_storage_directories(self, dev_mode: bool = False) -> bool:
        """
        Ensure all required storage directories exist.
        Creates them if they don't exist.
        
        @param dev_mode: Create directories for dev or prod mode
        @return: True if directories exist or were created successfully
        """
        try:
            directories = [
                self._get_storage_path(dev_mode),
                self._get_storage_path_for_students(dev_mode),
            ]
            
            for directory in directories:
                if not os.path.exists(directory):
                    os.makedirs(directory, exist_ok=True)
                    _logger.info(f"Created storage directory: {directory}")
            
            return True
            
        except OSError as e:
            _logger.error(f"Failed to create storage directories: {e}")
            self._create_sys_error("SAPSYNC-900", f"Failed to create storage directories: {e}")
            return False

    def _get_file_path(self, filename: str, dev_mode: bool = False, is_student: bool = False) -> str:
        """
        Get the full file path for a storage file.
        
        @param filename: Name of the file (e.g., 'dev-students-011007.json')
        @param dev_mode: Use dev or prod directory
        @param is_student: If True, use students subdirectory (dev mode only)
        @return: Full absolute path to the file
        """
        if is_student and dev_mode:
            base_path = self._get_storage_path_for_students(dev_mode)
        else:
            base_path = self._get_storage_path(dev_mode)
        
        return os.path.join(base_path, filename)

    @api.model
    def action_create_storage_directories(self):
        """
        Action to create storage directories from UI or shell.
        Creates both dev and prod directories.
        
        Can be called via:
        - UI button
        - Shell: env['myschool.informat.service'].action_create_storage_directories()
        """
        dev_created = self._ensure_storage_directories(dev_mode=True)
        prod_created = self._ensure_storage_directories(dev_mode=False)
        
        if dev_created and prod_created:
            message = (
                f"Storage directories created successfully:\n"
                f"- Dev: {self._get_storage_path(True)}\n"
                f"- Prod: {self._get_storage_path(False)}"
            )
            _logger.info(message)
            return {'success': True, 'message': message}
        else:
            return {'success': False, 'message': 'Failed to create some directories'}

    # =========================================================================
    # Main Synchronization Methods
    # =========================================================================

    @api.model
    def execute_sync(self, dev_mode: bool = True) -> bool:
        """
        Main synchronization method - retrieves data from SAP, analyzes it,
        and creates the required tasks.
        
        This method is designed to be called by a scheduled cron job.
        Equivalent to Java: executeSync()
        
        @param dev_mode: If True, uses local dev files instead of API calls
        @return: True if successful, False if errors occurred
        """

        dev_mode = True
        _logger.info("SAPSYNC-001: Starting Informat sync process")



        # # Debug: print all myschool models
        # myschool_models = [m for m in self.env.registry.models.keys() if 'myschool' in m]
        # print("Available models:", sorted(myschool_models))
        #
        # # Check if sys_event exists
        # print("sys_event exists:", 'myschool.sys.event' in self.env.registry.models)
        #
        # SysEvent = self.env.get('myschool.sys.event')
        # print("SysEvent:", SysEvent, type(SysEvent))
        #
        #
        #
        SysEvent = self.env.get('myschool.sys.event.service')
        SysEvent.create_sys_event("SAPSYNC-001", "Start Syncing Employee information",True)

        try:
            # Ensure storage directories exist
            if not self._ensure_storage_directories(dev_mode):
                return False
            
            # Calculate timestamp for last sync (15 days ago)
            timestamp_latest_sync = (datetime.now() - timedelta(days=15)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
            
            # Check for blocking tasks
            if self._check_blocking_tasks():
                return False
            
            # =====================================================
            # PHASE 1: Employee Processing
            # =====================================================
            
            # Get Employee related information
            all_imported_employees = self._get_employees_from_informat('', dev_mode)
            all_imported_employee_assignments = self._get_employee_assignments_from_informat(dev_mode)
            
            if all_imported_employees is None:
                self._create_sys_error("SAPSYNC-900", "Error in getEmployeesFromInformat")
                return False
                
            if all_imported_employee_assignments is None:
                self._create_sys_error("SAPSYNC-900", "Error in getEmployeeAssignmentsFromInformat")
            else:
                self._create_sys_event("SAPSYNC-001", f"Loaded {len(all_imported_employee_assignments)} employee assignments")

            # Analyze and create employee roles
            self._analyze_employee_assignments_and_create_roles(all_imported_employee_assignments)
            #self._process_betasks('DB', 'ROLE', 'ADD')
            #self._process_betasks('DB', 'ROLE', 'UPD')

            # NEW: Analyze employee data and create employee DB tasks (ADD/UPD/DEACT)
            if not self._sync_employees(
                all_imported_employees,
                all_imported_employee_assignments
            ):
                self._create_sys_error("SAPSYNC-900", "Error in _sync_employees")
                return False

            # =====================================================
            # PHASE 2: Student Processing
            # =====================================================
            
            # Retrieve Registration and Student information
            # all_imported_registrations = self._get_registrations_from_informat('', dev_mode)
            # all_imported_students = self._get_students_from_informat('', '', dev_mode)
            #
            # if all_imported_registrations is None:
            #     self._create_sys_error("SAPSYNC-900", "Error in getRegistrationsFromInformat")
            #     return False
            #
            # if all_imported_students is None:
            #     self._create_sys_error("SAPSYNC-900", "Error in getStudentsFromInformat")
            #     return False
            #
            # Process Org (class groups) tasks
            # self._analyze_student_data_and_create_org_tasks(all_imported_registrations)
            # self._process_betasks('DB', 'ORG', 'ADD')
            # self._process_betasks('DB', 'ORG', 'UPDATE')
            #
            # # Process Relations
            # self._analyze_data_and_create_relation_tasks(all_imported_students)
            # self._process_betasks('DB', 'RELATION', 'ADD')
            # self._process_betasks('DB', 'RELATION', 'UPD')
            #
            # # Process Students
            # self._analyze_data_and_create_student_tasks(all_imported_registrations, all_imported_students)
            # self._process_betasks('DB', 'STUDENT', 'ADD')
            # self._process_betasks('LDAP', 'STUDENT', 'ADD')
            # self._process_betasks('DB', 'STUDENT', 'UPD')
            #
            self._create_sys_event("SAPSYNC", "All tasks processed without errors")
            return True
            
        except Exception as e:
            self._create_sys_error("SAPSYNC-900", f"Executesync error: {traceback.format_exc()}")
            return False

    @api.model
    def execute_diff_sync(self, dev_mode: bool = False) -> bool:
        """
        Differential sync - retrieves JSON files since last run.
        Stores them to sapimport/prod for monitoring differential import structure.
        
        Equivalent to Java: executeDiffSync()
        
        @param dev_mode: If True, uses local dev files
        @return: True if successful
        """
        _logger.info("SAPSYNC-001: Starting differential Informat sync")
        
        try:
            timestamp_sync_start = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
            
            # Get timestamp of latest sync from config
            ConfigItem = self.env['myschool.config.item']
            timestamp_config = ConfigItem.search([
                ('name', '=', 'SapSyncLastTimestamp')
            ], limit=1)
            
            timestamp_latest_sync = ''
            if timestamp_config:
                timestamp_latest_sync = timestamp_config.string_value or ''
            
            # Perform the sync operations
            self._get_registrations_from_informat(timestamp_latest_sync, dev_mode)
            self._get_students_from_informat(timestamp_latest_sync, '', dev_mode)
            
            # Update the timestamp
            if timestamp_config:
                timestamp_config.string_value = timestamp_sync_start
            
            self._create_sys_event("SAPSYNC", "Differential sync completed")
            return True
            
        except Exception as e:
            self._create_sys_error("SAPSYNC-900", f"ExecuteDiffSync error: {traceback.format_exc()}")
            return False

    # =========================================================================
    # Data Retrieval Methods
    # =========================================================================

    def _get_bearer_token(self, org_short_name: str = 'olvp') -> Optional[str]:
        """
        Retrieve OAuth2 Bearer token from identity server.
        
        @param org_short_name: Short name of the organization
        @return: Bearer token string or None if failed
        """
        try:
            ConfigItem = self.env['myschool.config.item']
            
            api_id = ConfigItem.get_ci_value_by_org_and_name(org_short_name, 'SapInformatJSONApiId')
            api_password = ConfigItem.get_ci_value_by_org_and_name(org_short_name, 'SapInformatJSONApiPassword')
            
            if not api_id or not api_password:
                _logger.error("API credentials not found in config items")
                return None
            
            response = requests.post(
                self.IDENTITY_SERVER_URL,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                data={
                    'client_id': api_id,
                    'client_secret': api_password,
                    'grant_type': 'client_credentials'
                },
                timeout=30
            )
            
            if response.status_code != 200:
                _logger.error(f"Problem retrieving Bearer token: {response.status_code}")
                return None
            
            token_data = response.json()
            return token_data.get('access_token')
            
        except Exception as e:
            _logger.error(f"Error getting bearer token: {e}")
            return None

    def _get_registrations_from_informat(self, timestamp: str, dev_mode: bool) -> Optional[Dict[str, str]]:
        """
        Retrieve Student Registration information from Informat.
        
        Equivalent to Java: getRegistrationsFromInformat()
        
        @param timestamp: Retrieve changes after this timestamp
        @param dev_mode: Use local files if True
        @return: Dict with persoonId as key and JSON string as value, or None on error
        """
        procedure_name = '_get_registrations_from_informat'
        all_registrations: Dict[str, str] = {}
        
        self._create_sys_event("SAPSYNC-001", "Start importing Registration information")
        
        try:
            ConfigItem = self.env['myschool.config.item']
            current_school_year = ConfigItem.get_ci_value_by_org_and_name('olvp', 'CurrentSchoolYear')
            
            timestamp_string = f"&changedSince={timestamp}" if timestamp else ""
            
            # Get bearer token if not in dev mode
            bearer_token = None
            if not dev_mode:
                bearer_token = self._get_bearer_token()
                if not bearer_token:
                    return None
            
            # Get all schools with INFORMAT as SAP provider
            Org = self.env['myschool.org']
            schools = Org.search([('sap_provider', '=', '1')])
            
            for school in schools:
                self._create_sys_event("SAPSYNC-001", f"Start importing data for {school.inst_nr}")
                
                file_suffix = datetime.now().strftime('%Y%m%d%H%M%S.json')
                institution_number = school.inst_nr
                
                if dev_mode:
                    # Use local development files
                    json_file_path = self._get_file_path(
                        f"dev-registrations-{institution_number}.json", 
                        dev_mode=True
                    )
                    registrations_data = self._read_json_file(json_file_path)
                    
                    if registrations_data:
                        for registration in registrations_data:
                            persoon_id = registration.get('persoonId')
                            if persoon_id:
                                all_registrations[persoon_id] = json.dumps(registration)
                    else:
                        self._create_sys_event("SAPSYNC-900", f"File not found: {json_file_path}")
                else:
                    # Fetch from API
                    json_file_path = self._get_file_path(
                        f"registrations-{institution_number}-{file_suffix}",
                        dev_mode=False
                    )
                    
                    response = requests.get(
                        f"{self.STUDENTS_API_URL}/registrations?schoolYear={current_school_year}{timestamp_string}",
                        headers={
                            'Authorization': f'Bearer {bearer_token}',
                            'InstituteNo': institution_number,
                            'Accept': 'application/json'
                        },
                        timeout=60
                    )
                    
                    if response.status_code != 200:
                        self._create_sys_error("BETASK-900", f"{procedure_name}: Problem retrieving Registration Data")
                        continue
                    
                    if response.text and response.text != '[]':
                        # Write to file
                        self._write_json_file(json_file_path, response.text)
                        
                        # Parse and add to results
                        registrations_data = response.json()
                        for registration in registrations_data:
                            persoon_id = registration.get('persoonId')
                            if persoon_id:
                                all_registrations[persoon_id] = json.dumps(registration)
            
            self._create_sys_event("SAPSYNC-001", "Registrations retrieved successfully")
            return all_registrations
            
        except Exception as e:
            self._create_sys_error("BETASK-900", f"{procedure_name}: {traceback.format_exc()}")
            return None

    def _get_students_from_informat(self, timestamp: str, student_id: str, dev_mode: bool) -> Optional[Dict[str, str]]:
        """
        Retrieve Student data from SAP Informat for all orgs where SAP = 1.
        
        Equivalent to Java: getStudentsFromInformat()
        
        @param timestamp: Return students changed after this moment
        @param student_id: If specified, retrieve data for specific student
        @param dev_mode: Use local files if True
        @return: Dict with persoonId as key and JSON string as value, or None on error
        """
        procedure_name = '_get_students_from_informat'
        all_students: Dict[str, str] = {}
        
        self._create_sys_event("BETASK-001", f"{procedure_name} started")
        
        try:
            timestamp_string = f"&changedSince={timestamp}" if timestamp else ""
            student_id_string = f"/{student_id}" if student_id else ""
            
            # Get bearer token if not in dev mode
            bearer_token = None
            if not dev_mode:
                bearer_token = self._get_bearer_token()
                if not bearer_token:
                    return None
            
            ConfigItem = self.env['myschool.config.item']
            current_school_year = ConfigItem.get_ci_value_by_org_and_name('olvp', 'CurrentSchoolYear')
            
            # Get all schools with INFORMAT as SAP provider
            Org = self.env['myschool.org']
            schools = Org.search([('sap_provider', '=', '1')])
            
            for school in schools:
                _logger.info(f"Start importing student data for {school.inst_nr}")
                
                file_suffix = datetime.now().strftime('%Y%m%d%H%M%S.json')
                institution_number = school.inst_nr
                
                self._create_sys_event("SAPSYNC-001", f"Start importing Student data from Informat of Inst {institution_number}")
                
                if dev_mode:
                    # Use local development files (students have their own subdirectory)
                    json_file_path = self._get_file_path(
                        f"dev-students-{institution_number}.json",
                        dev_mode=True,
                        is_student=True
                    )
                    students_data = self._read_json_file(json_file_path)
                    
                    if students_data:
                        for student in students_data:
                            persoon_id = student.get('persoonId')
                            if persoon_id:
                                all_students[persoon_id] = json.dumps(student)
                    else:
                        self._create_sys_event("SAPSYNC-900", f"File not found: {json_file_path}")
                else:
                    # Fetch from API
                    json_file_path = self._get_file_path(
                        f"students-{institution_number}-{file_suffix}",
                        dev_mode=False
                    )
                    
                    response = requests.get(
                        f"{self.STUDENTS_API_URL}{student_id_string}?schoolYear={current_school_year}{timestamp_string}",
                        headers={
                            'Authorization': f'Bearer {bearer_token}',
                            'InstituteNo': institution_number,
                            'Accept': 'application/json'
                        },
                        timeout=60
                    )
                    
                    if response.status_code != 200:
                        self._create_sys_error("SAPSYNC-900", "Problem during retrieval of Student Data")
                        continue
                    
                    response_data = response.json()
                    students_data = response_data.get('students', [])
                    
                    if students_data:
                        # Write to file
                        self._write_json_file(json_file_path, json.dumps(students_data))
                        
                        for student in students_data:
                            persoon_id = student.get('persoonId')
                            if persoon_id:
                                all_students[persoon_id] = json.dumps(student)
            
            self._create_sys_event("SAPSYNC-001", "Students retrieved successfully")
            return all_students
            
        except Exception as e:
            self._create_sys_error("BETASK-900", f"{procedure_name}: {traceback.format_exc()}")
            return None

    def _get_employees_from_informat(self, timestamp: str, dev_mode: bool) -> Optional[Dict[str, str]]:
        """
        Retrieve Employee information from Informat.
        
        Equivalent to Java: getEmployeesFromInformat()
        
        @param timestamp: Retrieve changes after this timestamp
        @param dev_mode: Use local files if True
        @return: Dict with personId&instNr as key and JSON string as value, or None on error
        """
        procedure_name = '_get_employees_from_informat'
        all_employees: Dict[str, str] = {}


        self._create_sys_event("SAPSYNC-001", "Start importing Employee information")
        
        try:
            ConfigItem = self.env['myschool.config.item']
            current_school_year = ConfigItem.get_ci_value_by_org_and_name('olvp', 'CurrentSchoolYear')
            
            timestamp_string = f"&changedSince={timestamp}" if timestamp else ""
            
            # Get bearer token if not in dev mode
            bearer_token = None
            if not dev_mode:
                bearer_token = self._get_bearer_token()
                if not bearer_token:
                    return None
            
            # Get all schools with INFORMAT as SAP provider
            Org = self.env['myschool.org']
            schools = Org.search([('sap_provider', '=', '1')])  #todo: was INFORMAT - how to use string iso index
            
            for school in schools:
                self._create_sys_event("SAPSYNC-001", f"Start importing employee data for {school.inst_nr}")
                
                file_suffix = datetime.now().strftime('%Y%m%d%H%M%S.json')
                institution_number = school.inst_nr
                
                if dev_mode:
                    # Use local development files
                    json_file_path = self._get_file_path(
                        f"dev-employees-{institution_number}.json",
                        dev_mode=True
                    )
                    employees_data = self._read_json_file(json_file_path)
                    
                    if employees_data:
                        for employee in employees_data:
                            person_id = employee.get('personId')
                            if person_id:
                                key = f"{person_id}&{institution_number}"
                                all_employees[key] = json.dumps(employee)
                    else:
                        self._create_sys_event("SAPSYNC-900", f"File not found: {json_file_path}")
                else:
                    # Fetch from API
                    json_file_path = self._get_file_path(
                        f"employees-{institution_number}-{file_suffix}",
                        dev_mode=False
                    )
                    
                    response = requests.get(
                        f"{self.EMPLOYEES_API_URL}?schoolyear={current_school_year}{timestamp_string}",
                        headers={
                            'Authorization': f'Bearer {bearer_token}',
                            'Api-Version': '2',
                            'InstituteNo': institution_number,
                            'Accept': 'application/json'
                        },
                        timeout=60
                    )
                    
                    if response.status_code != 200:
                        self._create_sys_error("BETASK-900", f"{procedure_name}: Problem retrieving Employee Data")
                        continue
                    
                    if response.text and response.text != '[]':
                        # Write to file
                        self._write_json_file(json_file_path, response.text)
                        
                        employees_data = response.json()
                        for employee in employees_data:
                            person_id = employee.get('personId')
                            if person_id:
                                key = f"{person_id}&{institution_number}"
                                all_employees[key] = json.dumps(employee)
            
            self._create_sys_event("SAPSYNC-001", "Employees retrieved successfully")
            return all_employees
            
        except Exception as e:
            self._create_sys_error("BETASK-900", f"{procedure_name}: {traceback.format_exc()}")
            return None

    def _get_employee_assignments_from_informat(self, dev_mode: bool) -> Optional[Dict[str, str]]:
        """
        Retrieve Employee Assignments information from Informat.
        
        Equivalent to Java: getEmployeeAssignmentsFromInformat()
        
        @param dev_mode: Use local files if True
        @return: Dict with personId&instNr as key and JSON string as value, or None on error
        """
        procedure_name = '_get_employee_assignments_from_informat'
        all_assignments: Dict[str, str] = {}
        
        self._create_sys_event("SAPSYNC-001", "Start importing Employee Assignment information")
        
        try:
            ConfigItem = self.env['myschool.config.item']
            current_school_year = ConfigItem.get_ci_value_by_org_and_name('olvp', 'CurrentSchoolYear')
            
            # Get bearer token if not in dev mode
            bearer_token = None
            if not dev_mode:
                bearer_token = self._get_bearer_token()
                if not bearer_token:
                    return None
            
            # Get all schools with INFORMAT as SAP provider
            Org = self.env['myschool.org']
            schools = Org.search([('sap_provider', '=', '1')])
            
            for school in schools:
                self._create_sys_event("SAPSYNC-001", f"Start importing assignment data for {school.inst_nr}")
                
                file_suffix = datetime.now().strftime('%Y%m%d%H%M%S.json')
                institution_number = school.inst_nr
                
                if dev_mode:
                    # Use local development files
                    json_file_path = self._get_file_path(
                        f"dev-employeeassignments-{institution_number}.json",
                        dev_mode=True
                    )
                    assignments_data = self._read_json_file(json_file_path)
                    
                    if assignments_data:
                        for assignment in assignments_data:
                            # Replace "id" with "assignmentId" to avoid conflicts
                            if 'id' in assignment:
                                assignment['assignmentId'] = assignment.pop('id')

                            person_id = assignment.get('personId')
                            assignment_id = assignment.get('assignmentId', '')
                            if person_id:
                                # Include assignmentId in key to handle multiple assignments per person
                                key = f"{person_id}&{institution_number}&{assignment_id}"
                                all_assignments[key] = json.dumps(assignment)
                    else:
                        self._create_sys_event("SAPSYNC-900", f"File not found: {json_file_path}")
                else:
                    # Fetch from API
                    json_file_path = self._get_file_path(
                        f"employeeassignments-{institution_number}-{file_suffix}",
                        dev_mode=False
                    )
                    
                    response = requests.get(
                        f"{self.EMPLOYEE_ASSIGNMENTS_API_URL}?schoolyear={current_school_year}",
                        headers={
                            'Authorization': f'Bearer {bearer_token}',
                            'Api-Version': '2',
                            'InstituteNo': institution_number,
                            'Accept': 'application/json'
                        },
                        timeout=60
                    )
                    
                    if response.status_code != 200:
                        self._create_sys_error("BETASK-900", f"{procedure_name}: Problem retrieving Assignment Data")
                        continue
                    
                    if response.text and response.text != '[]':
                        # Write to file
                        self._write_json_file(json_file_path, response.text)
                        
                        assignments_data = response.json()
                        for assignment in assignments_data:
                            # Replace "id" with "assignmentId" to avoid conflicts
                            if 'id' in assignment:
                                assignment['assignmentId'] = assignment.pop('id')

                            person_id = assignment.get('personId')
                            assignment_id = assignment.get('assignmentId', '')
                            if person_id:
                                # Include assignmentId in key to handle multiple assignments per person
                                key = f"{person_id}&{institution_number}&{assignment_id}"
                                all_assignments[key] = json.dumps(assignment)
            
            self._create_sys_event("SAPSYNC-001", "Employee assignments retrieved successfully")
            return all_assignments
            
        except Exception as e:
            self._create_sys_error("BETASK-900", f"{procedure_name}: {traceback.format_exc()}")
            return None

    # =========================================================================
    # Analysis and Task Creation Methods
    # =========================================================================

    # =============================================================================
    # EMPLOYEE SYNC TWO-PHASE EMPLOYEE SYNC APPROACH
    # =============================================================================
    #
    # Phase 1: _sync_employee_persons()
    #   - Synchronize Person objects based on all_imported_employee_data
    #   - Creates ADD/UPD/DEACT tasks for Person records
    #
    # Phase 2: _sync_employee_proprelations()
    #   - For each ACTIVE employee in database
    #   - Sync PropRelation objects based on all_imported_employee_assignments
    #   - Creates ADD/UPD/DEACT tasks for PropRelation records
    #
    # =============================================================================
    def _sync_employees(
            self,
            all_imported_employee_data: Dict[str, str],
            all_imported_employee_assignments: Dict[str, str]
    ) -> bool:
        """
        Main employee synchronization method - two phase approach.

        Phase 1: Sync Person objects (ADD/UPD/DEACT)
        Phase 1b: Sync Odoo Users for new/updated persons
        Phase 2: Sync PPSBR PropRelation objects for active employees
        Phase 2b: Sync Odoo Group memberships based on roles
        """
        procedure_name = '_sync_employees'
        self._create_sys_event("BETASK-001", f"{procedure_name} started")

        try:
            # =====================================================
            # PHASE 1: Sync Person Objects
            # =====================================================
            self._create_sys_event("BETASK-001", "Phase 1: Syncing Person objects")

            if not self._sync_employee_persons(all_imported_employee_data, all_imported_employee_assignments):
                self._create_sys_error("BETASK-900", f"{procedure_name}: Error in Phase 1 (Person sync)")
                return False

            # Process DB-EMPLOYEE tasks
            # self._process_betasks('DB', 'EMPLOYEE', 'ADD')
            # self._process_betasks('DB', 'EMPLOYEE', 'UPD')
            # self._process_betasks('DB', 'EMPLOYEE', 'DEACT')

            # =====================================================
            # PHASE 1b: Sync Odoo Users (NEW!)
            # =====================================================
            self._create_sys_event("BETASK-001", "Phase 1b: Syncing Odoo Users")

            # Process ODOO-PERSON tasks (creates res.users and hr.employee)
            # self._process_betasks('ODOO', 'PERSON', 'ADD')
            # self._process_betasks('ODOO', 'PERSON', 'UPD')
            # self._process_betasks('ODOO', 'PERSON', 'DEACT')

            # =====================================================
            # PHASE 2: Sync PPSBR PropRelation Objects
            # =====================================================
            self._create_sys_event("BETASK-001", "Phase 2: Syncing PPSBR PropRelation objects")

            if not self._sync_employee_proprelations(all_imported_employee_assignments):
                self._create_sys_error("BETASK-900", f"{procedure_name}: Error in Phase 2 (PPSBR sync)")
                return False

            # Process DB-PROPRELATION tasks
            # self._process_betasks('DB', 'PROPRELATION', 'ADD')
            # self._process_betasks('DB', 'PROPRELATION', 'UPD')
            # self._process_betasks('DB', 'PROPRELATION', 'DEACT')

            # =====================================================
            # PHASE 2b: Sync Odoo Group Memberships (NEW!)
            # =====================================================
            self._create_sys_event("BETASK-001", "Phase 2b: Syncing Odoo Group memberships")

            # Process ODOO-GROUPMEMBER tasks (adds/removes users from groups)
            self._process_betasks('ODOO', 'GROUPMEMBER', 'ADD')
            self._process_betasks('ODOO', 'GROUPMEMBER', 'REMOVE')

            self._create_sys_event("BETASK-001", f"{procedure_name} completed successfully")
            return True

        except Exception as e:
            self._create_sys_error("BETASK-900", f"{procedure_name}: {traceback.format_exc()}")
            return False

    # =========================================================================
    # PHASE 1: Person Synchronization
    # =========================================================================

    def _sync_employee_persons(
            self,
            all_imported_employee_data: Dict[str, str],
            all_imported_employee_assignments: Dict[str, str] = None
    ) -> bool:
        """
        Phase 1: Synchronize Person objects based on imported employee data.

        Logic:
        - Loop through imported employees
        - For each unique person (by sap_person_uuid):
          - If not in DB and pension_date OK: CREATE (ADD task)
          - If in DB: compare and UPDATE if changed (UPD task)
          - If in DB but should be deactivated: DEACT task
        - For persons in DB but not in import: DEACT task

        @param all_imported_employee_data: Dict with personId&instNr as key, employee JSON as value
        @param all_imported_employee_assignments: Dict with personId&instNr&assignmentId as key, assignment JSON as value
        @return: True if successful
        """
        procedure_name = '_sync_employee_persons'

        if not all_imported_employee_data:
            self._create_sys_error("BETASK-900", f"{procedure_name}: parameter is empty")
            return False

        self._create_sys_event("BETASK-001", f"{procedure_name} started")

        try:
            Person = self.env['myschool.person']
            PersonDetails = self.env['myschool.person.details']

            today = datetime.now().date()

            # Track processed person UUIDs to detect persons to deactivate
            processed_person_uuids = set()

            # Track persons added in this run (to handle multiple instNrs)
            added_persons = {}  # {person_uuid: first_inst_nr}

            # =====================================================
            # Process each imported employee
            # =====================================================
            for employee_key, employee_value in all_imported_employee_data.items():

                # Parse key: personId&instNr
                key_parts = employee_key.split('&')
                if len(key_parts) != 2:
                    self._create_sys_event("BETASK-900", f"Invalid key format: {employee_key}")
                    continue

                person_uuid = key_parts[0]
                inst_nr = key_parts[1]

                # Parse employee JSON
                employee_json = json.loads(employee_value)
                employee_json['instNr'] = inst_nr

                # Include assignments for this person and instNr
                if all_imported_employee_assignments:
                    person_assignments = []
                    for assign_key, assign_value in all_imported_employee_assignments.items():
                        # Key format: personId&instNr&assignmentId
                        assign_parts = assign_key.split('&')
                        if len(assign_parts) >= 2:
                            if assign_parts[0] == person_uuid and assign_parts[1] == inst_nr:
                                person_assignments.append(json.loads(assign_value))
                    if person_assignments:
                        employee_json['assignments'] = person_assignments
                        self._create_sys_event("BETASK-001", f"Added {len(person_assignments)} assignments for {person_uuid} at {inst_nr}")
                else:
                    self._create_sys_event("BETASK-001", f"No assignments dict available for {person_uuid}")

                # Get key fields
                is_active_import = employee_json.get('isActive', True)
                pension_date = self._parse_date_safe(employee_json.get('pensioendatum'))
                is_overleden = employee_json.get('isOverleden', False)

                # Track this person UUID
                processed_person_uuids.add(person_uuid)

                # Check if person exists in database
                person_in_db = Person.search([('sap_person_uuid', '=', person_uuid)], limit=1)

                # =====================================================
                # SCENARIO 1: Person NOT in database
                # =====================================================
                if not person_in_db:
                    # Check if pension date allows creation
                    pension_ok = pension_date is None or pension_date > today

                    if pension_ok and is_active_import and not is_overleden:
                        # Check if already added in this run (for another instNr)
                        if person_uuid not in added_persons:
                            # CREATE: New person
                            self._create_betask(
                                'DB', 'EMPLOYEE', 'ADD',
                                json.dumps(employee_json),
                                None
                            )
                            added_persons[person_uuid] = inst_nr
                            self._create_sys_event("BETASK-001", f"ADD task created for new person: {person_uuid}")
                        else:
                            # Person already added, just need to create PersonDetails
                            # This will be handled by the UPD task with ADD-DETAILS action
                            data2 = {'action': 'ADD-DETAILS', 'instNr': inst_nr}
                            self._create_betask(
                                'DB', 'EMPLOYEE', 'UPD',
                                json.dumps(employee_json),
                                json.dumps(data2)
                            )
                    continue

                # =====================================================
                # SCENARIO 2: Person EXISTS in database
                # =====================================================
                person_is_active_db = person_in_db.is_active

                # Check for PersonDetails for this instNr
                person_details = PersonDetails.search([
                    ('person_id', '=', person_in_db.id),
                    ('extra_field_1', '=', inst_nr)
                ], limit=1)

                # -----------------------------------------------------
                # SCENARIO 2a: Should DEACTIVATE
                # -----------------------------------------------------
                should_deactivate = (
                        (not is_active_import) or
                        (is_overleden) or
                        (pension_date and pension_date <= today)
                )

                if should_deactivate and person_is_active_db:
                    self._create_betask(
                        'DB', 'EMPLOYEE', 'DEACT',
                        json.dumps(employee_json),
                        None
                    )
                    self._create_sys_event("BETASK-001", f"DEACT task created for: {person_uuid}")
                    continue

                # -----------------------------------------------------
                # SCENARIO 2b: Should REACTIVATE
                # -----------------------------------------------------
                should_reactivate = (
                        not person_is_active_db and
                        is_active_import and
                        not is_overleden and
                        (pension_date is None or pension_date > today)
                )

                if should_reactivate:
                    data2 = {'action': 'REACTIVATE'}
                    self._create_betask(
                        'DB', 'EMPLOYEE', 'UPD',
                        json.dumps(employee_json),
                        json.dumps(data2)
                    )
                    self._create_sys_event("BETASK-001", f"REACTIVATE task created for: {person_uuid}")
                    continue

                # -----------------------------------------------------
                # SCENARIO 2c: No PersonDetails for this instNr - ADD-DETAILS
                # -----------------------------------------------------
                if not person_details:
                    data2 = {'action': 'ADD-DETAILS', 'instNr': inst_nr}
                    self._create_betask(
                        'DB', 'EMPLOYEE', 'UPD',
                        json.dumps(employee_json),
                        json.dumps(data2)
                    )
                    self._create_sys_event("BETASK-001",
                                           f"ADD-DETAILS task created for: {person_uuid}, instNr: {inst_nr}")
                    continue

                # -----------------------------------------------------
                # SCENARIO 2d: Compare and UPDATE if changed
                # -----------------------------------------------------
                if person_details and person_details.full_json_string:
                    try:
                        current_json = json.loads(person_details.full_json_string)
                        # Remove fields that shouldn't trigger update
                        compare_current = {k: v for k, v in current_json.items()
                                           if k not in ['instNr', 'assignments']}
                        compare_new = {k: v for k, v in employee_json.items()
                                       if k not in ['instNr', 'assignments']}

                        if compare_current != compare_new:
                            data2 = {'action': 'UPDATE'}
                            self._create_betask(
                                'DB', 'EMPLOYEE', 'UPD',
                                json.dumps(employee_json),
                                json.dumps(data2)
                            )
                            self._create_sys_event("BETASK-001", f"UPDATE task created for: {person_uuid}")
                    except json.JSONDecodeError:
                        # If we can't parse, update anyway
                        data2 = {'action': 'UPDATE'}
                        self._create_betask(
                            'DB', 'EMPLOYEE', 'UPD',
                            json.dumps(employee_json),
                            json.dumps(data2)
                        )

            # =====================================================
            # Check for persons to DEACTIVATE (in DB but not in import)
            # =====================================================
            # Only check employees that are synced automatically
            active_synced_persons = Person.search([
                ('is_active', '=', True),
                ('automatic_sync', '=', True),
                ('person_type_id.name', '=', 'EMPLOYEE')  # Only employees
            ])

            for person in active_synced_persons:
                if person.sap_person_uuid and person.sap_person_uuid not in processed_person_uuids:
                    # Person is in DB but not in import - deactivate
                    deact_data = {
                        'personId': person.sap_person_uuid,
                        'reason': 'Not in import'
                    }
                    self._create_betask(
                        'DB', 'EMPLOYEE', 'DEACT',
                        json.dumps(deact_data),
                        None
                    )
                    self._create_sys_event("BETASK-001",
                                           f"DEACT task created for person not in import: {person.sap_person_uuid}")

            self._create_sys_event("BETASK-001", f"{procedure_name} completed")
            return True

        except Exception as e:
            self._create_sys_error("BETASK-900", f"{procedure_name}: {traceback.format_exc()}")
            return False

    # =========================================================================
    # PHASE 2: PropRelation Synchronization
    # =========================================================================

    # =========================================================================
    # PropRelation Type Constants (add to class level)
    # =========================================================================

    PROPRELATION_TYPE_PERSON_TREE = 'PERSON-TREE'
    PROPRELATION_TYPE_PPSBR = 'PPSBR'
    PROPRELATION_TYPE_SR_BR = 'SR-BR'
    PROPRELATION_TYPE_BRSO = 'BRSO'
    PROPRELATION_TYPE_ORG_TREE = 'ORG-TREE'

    def _get_non_administrative_parent_org(self, org):
        """
        Find the parent non-administrative org for a given org.

        If the org is administrative, traverse up the ORG-TREE until we find
        a non-administrative org. Returns the original org if it's not administrative.

        @param org: The org to check
        @return: The non-administrative parent org, or the original org if not administrative
        """
        if not org or not org.is_administrative:
            return org

        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        org_tree_type = PropRelationType.search([
            ('name', '=', self.PROPRELATION_TYPE_ORG_TREE)
        ], limit=1)

        if not org_tree_type:
            return org

        current_org = org
        visited = set()  # Prevent infinite loops

        while current_org and current_org.is_administrative and current_org.id not in visited:
            visited.add(current_org.id)

            # Find parent via ORG-TREE relation (current_org is the child)
            org_tree_relation = PropRelation.search([
                ('proprelation_type_id', '=', org_tree_type.id),
                ('id_org_child', '=', current_org.id),
                ('is_active', '=', True)
            ], limit=1)

            if org_tree_relation and org_tree_relation.id_org_parent:
                current_org = org_tree_relation.id_org_parent
            else:
                # No parent found, return current
                break

        return current_org

    # =========================================================================
    # PHASE 2: PropRelation Synchronization (UPDATED)
    # =========================================================================

    def _sync_employee_proprelations(self, all_imported_employee_assignments: Dict[str, str]) -> bool:
        """
        Phase 2: Synchronize PropRelation objects (PPSBR) for active employees.

        Creates PPSBR (Person-Period-School-BackendRole) records based on assignments.
        The BeTask processor will then determine the PERSON-TREE position.

        Logic:
        - Get all ACTIVE employees from database
        - For each active employee:
          - Get their assignments from the import
          - Compare with existing PPSBR PropRelations
          - CREATE new PPSBR for new assignments
          - DEACTIVATE PPSBR for removed assignments

        @param all_imported_employee_assignments: Dict with personId&instNr as key, assignment JSON as value
        @return: True if successful
        """
        procedure_name = '_sync_employee_proprelations'

        self._create_sys_event("BETASK-001", f"{procedure_name} started")

        try:
            Person = self.env['myschool.person']
            PropRelation = self.env['myschool.proprelation']
            PropRelationType = self.env['myschool.proprelation.type']
            Org = self.env['myschool.org']
            Role = self.env['myschool.role']
            Period = self.env['myschool.period']

            # -----------------------------------------------------------------
            # Get PropRelation types
            # -----------------------------------------------------------------

            # PPSBR: Person-Period-School-BackendRole
            ppsbr_type = PropRelationType.search([
                ('name', '=', self.PROPRELATION_TYPE_PPSBR)
            ], limit=1)

            if not ppsbr_type:
                self._create_sys_event("BETASK-001", f"Creating PPSBR PropRelationType")
                ppsbr_type = PropRelationType.create({
                    'name': self.PROPRELATION_TYPE_PPSBR,
                    'usage': 'Person-Period-School-BackendRole relation',
                    'is_active': True
                })

            # SR-BR: SapRole to BackendRole mapping
            sr_br_type = PropRelationType.search([
                ('name', '=', self.PROPRELATION_TYPE_SR_BR)
            ], limit=1)

            # BRSO: BackendRole to School Org mapping
            brso_type = PropRelationType.search([
                ('name', '=', self.PROPRELATION_TYPE_BRSO)
            ], limit=1)

            # Get current active period
            current_period = Period.search([('is_active', '=', True)], limit=1)

            # -----------------------------------------------------------------
            # Build lookup dict for assignments by personId
            # Structure: {personId: {instNr: [assignment1, assignment2, ...]}}
            # -----------------------------------------------------------------
            assignments_by_person = {}

            if all_imported_employee_assignments:
                for assignment_key, assignment_value in all_imported_employee_assignments.items():
                    key_parts = assignment_key.split('&')
                    # Key format: personId&instNr&assignmentId (3 parts)
                    if len(key_parts) < 2:
                        continue

                    person_uuid = key_parts[0]
                    inst_nr = key_parts[1]

                    assignment_json = json.loads(assignment_value)
                    assignment_json['instNr'] = inst_nr

                    if person_uuid not in assignments_by_person:
                        assignments_by_person[person_uuid] = {}

                    if inst_nr not in assignments_by_person[person_uuid]:
                        assignments_by_person[person_uuid][inst_nr] = []

                    assignments_by_person[person_uuid][inst_nr].append(assignment_json)

            self._create_sys_event("BETASK-001",
                                   f"Loaded assignments for {len(assignments_by_person)} persons")

            # -----------------------------------------------------------------
            # Process each ACTIVE employee in database
            # -----------------------------------------------------------------
            active_employees = Person.search([
                ('is_active', '=', True),
                ('automatic_sync', '=', True),
                ('person_type_id.name', '=', 'EMPLOYEE')
            ])

            self._create_sys_event("BETASK-001",
                                   f"Processing {len(active_employees)} active employees")

            for person in active_employees:
                person_uuid = person.sap_person_uuid

                if not person_uuid:
                    continue

                # Get imported assignments for this person
                imported_assignments = assignments_by_person.get(person_uuid, {})

                # Get existing active PPSBR PropRelations for this person
                existing_ppsbr = PropRelation.search([
                    ('id_person', '=', person.id),
                    ('proprelation_type_id', '=', ppsbr_type.id),
                    ('is_active', '=', True),
                    ('automatic_sync', '=', True)
                ])

                # Track which PPSBR we've processed (to detect ones to deactivate)
                processed_ppsbr_keys = set()

                # -----------------------------------------------------
                # Process imported assignments
                # -----------------------------------------------------
                for inst_nr, assignments in imported_assignments.items():
                    # Find the school org for this instNr
                    school_org = Org.search([
                        ('inst_nr', '=', inst_nr),
                        ('is_active', '=', True),
                        ('org_type_id.name', '=', 'SCHOOL')
                    ], limit=1)

                    if not school_org:
                        school_org = Org.search([
                            ('inst_nr', '=', inst_nr),
                            ('is_active', '=', True)
                        ], limit=1)

                    # If school_org is administrative, get the parent non-administrative org
                    # for role lookups (roles are typically defined at the parent level)
                    role_lookup_org = self._get_non_administrative_parent_org(school_org)

                    for assignment in assignments:
                        # Get role info from assignment
                        hoofd_ambt_code = assignment.get('ambtCode', '')
                        hoofd_ambt_name = assignment.get('ambt', '')

                        if not hoofd_ambt_code:
                            continue

                        # Find the SAP Role
                        sap_role = Role.search([('shortname', '=', hoofd_ambt_code)], limit=1)

                        # Find Backend Role via SR-BR relation
                        be_role = None
                        if sap_role and sr_br_type:
                            sr_br_relation = PropRelation.search([
                                ('id_role', '=', sap_role.id),
                                ('proprelation_type_id', '=', sr_br_type.id),
                                ('is_active', '=', True)
                            ], limit=1)

                            if sr_br_relation and sr_br_relation.id_role_parent:
                                be_role = sr_br_relation.id_role_parent

                        # If no backend role found via SR-BR, check BRSO with parent org
                        # (roles might be defined at parent org level for administrative orgs)
                        if not be_role and role_lookup_org and brso_type:
                            brso_relation = PropRelation.search([
                                ('proprelation_type_id', '=', brso_type.id),
                                ('id_org', '=', role_lookup_org.id),
                                ('is_active', '=', True)
                            ], limit=1)
                            if brso_relation and brso_relation.id_role:
                                be_role = brso_relation.id_role
                                self._create_sys_event(
                                    "BETASK-001",
                                    f"Found role via BRSO for parent org {role_lookup_org.name}: {be_role.name}"
                                )

                        # Use Backend Role if found, otherwise SAP Role
                        role_to_use = be_role if be_role else sap_role

                        if not role_to_use:
                            self._create_sys_event(
                                "BETASK-001",
                                f"No role found for ambtCode {hoofd_ambt_code} at org {inst_nr} - skipping"
                            )
                            continue

                        # Create unique key for this PPSBR
                        # Key: person_id + org_id + role_id + period_id
                        period_id = current_period.id if current_period else ''
                        ppsbr_key = f"{person.id}_{school_org.id if school_org else ''}_{role_to_use.id}_{period_id}"
                        processed_ppsbr_keys.add(ppsbr_key)

                        # Check if PPSBR already exists
                        search_domain = [
                            ('id_person', '=', person.id),
                            ('proprelation_type_id', '=', ppsbr_type.id),
                            ('id_role', '=', role_to_use.id),
                            ('is_active', '=', True)
                        ]
                        if school_org:
                            search_domain.append(('id_org', '=', school_org.id))
                        if current_period:
                            search_domain.append(('id_period', '=', current_period.id))

                        existing_ppsbr_record = PropRelation.search(search_domain, limit=1)

                        if not existing_ppsbr_record:
                            # CREATE new PPSBR via BeTask
                            proprel_data = {
                                'personId': person_uuid,
                                'person_db_id': person.id,
                                'instNr': inst_nr,
                                'orgId': school_org.id if school_org else None,
                                'roleCode': hoofd_ambt_code,
                                'roleName': hoofd_ambt_name,
                                'roleId': role_to_use.id,
                                'sapRoleId': sap_role.id if sap_role else None,
                                'beRoleId': be_role.id if be_role else None,
                                'periodId': current_period.id if current_period else None,
                                'assignment': assignment
                            }
                            self._create_betask(
                                'DB', 'PROPRELATION', 'ADD',
                                json.dumps(proprel_data),
                                None
                            )
                            self._create_sys_event("BETASK-001",
                                                   f"PPSBR ADD task for {person.name} - {hoofd_ambt_code} - {inst_nr}")

                # -----------------------------------------------------
                # Deactivate PPSBR not in import
                # -----------------------------------------------------
                for ppsbr in existing_ppsbr:
                    # Build key from existing record
                    period_id = ppsbr.id_period.id if ppsbr.id_period else ''
                    existing_key = f"{ppsbr.id_person.id}_{ppsbr.id_org.id if ppsbr.id_org else ''}_{ppsbr.id_role.id if ppsbr.id_role else ''}_{period_id}"

                    if existing_key not in processed_ppsbr_keys:
                        # This PPSBR is no longer in import - deactivate
                        deact_data = {
                            'proprelation_id': ppsbr.id,
                            'personId': person_uuid,
                            'reason': 'Assignment removed from import'
                        }
                        self._create_betask(
                            'DB', 'PROPRELATION', 'DEACT',
                            json.dumps(deact_data),
                            None
                        )
                        self._create_sys_event("BETASK-001",
                                               f"PPSBR DEACT task for {person.name}, ppsbr_id: {ppsbr.id}")

            self._create_sys_event("BETASK-001", f"{procedure_name} completed")
            return True

        except Exception as e:
            self._create_sys_error("BETASK-900", f"{procedure_name}: {traceback.format_exc()}")
            return False

    # =========================================================================
    # Helper: Safe Date Parsing
    # =========================================================================

    def _parse_date_safe(self, date_string: str):
        """
        Safely parse a date string trying multiple formats.

        @param date_string: Date string to parse
        @return: date object or None if parsing fails
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
                return datetime.strptime(date_string, fmt).date()
            except (ValueError, TypeError):
                continue

        _logger.warning(f"Could not parse date: {date_string}")
        return None

# =============================================================================
# UPDATE execute_sync() TO USE NEW METHOD
# =============================================================================
#
# Replace the call to _analyze_informat_data_and_create_employee_db_tasks with:
#
#     # =====================================================
#     # PHASE 1 & 2: Employee Processing (two-phase approach)
#     # =====================================================
#
#     # Get Employee related information
#     all_imported_employees = self._get_employees_from_informat('', dev_mode)
#     all_imported_employee_assignments = self._get_employee_assignments_from_informat(dev_mode)
#
#     if all_imported_employees is None:
#         self._create_sys_error("SAPSYNC-900", "Error in getEmployeesFromInformat")
#         return False
#
#     if all_imported_employee_assignments is None:
#         self._create_sys_error("SAPSYNC-900", "Error in getEmployeeAssignmentsFromInformat")
#         return False
#
#     # Two-phase employee sync
#     if not self._sync_employees(all_imported_employees, all_imported_employee_assignments):
#         self._create_sys_error("SAPSYNC-900", "Error in _sync_employees")
#         return False
#
# =============================================================================

# =============================================================================
# BETASK TYPES NEEDED
# =============================================================================
#
# Make sure these BeTaskTypes exist in your database:
#
# | Target | Object       | Action |
# |--------|--------------|--------|
# | DB     | EMPLOYEE     | ADD    |
# | DB     | EMPLOYEE     | UPD    |
# | DB     | EMPLOYEE     | DEACT  |
# | DB     | PROPRELATION | ADD    |
# | DB     | PROPRELATION | UPD    |
# | DB     | PROPRELATION | DEACT  |
#
# =============================================================================








    def _analyze_student_data_and_create_org_tasks(self, all_registrations: Dict[str, str]) -> bool:
        """
        Analyze imported registration data and create Org (class group) tasks.
        
        Equivalent to Java: AnalyzeStudentInformatDataAndCreateOrgDbTasks()
        
        @param all_registrations: Dict with registration data
        @return: True if successful
        """
        procedure_name = '_analyze_student_data_and_create_org_tasks'
        
        if not all_registrations:
            self._create_sys_error("BETASK-900", f"{procedure_name}: parameter is empty")
            return False
        
        try:
            self._create_sys_event("SAPSYNC-001", "Start analysing Registrations for ORG Betask creation")
            
            # Get current period
            Period = self.env['myschool.period']
            PeriodType = self.env['myschool.period.type']
            
            school_year_type = PeriodType.search([('name', '=', 'SCHOOLJAAR')], limit=1)
            current_period = Period.search([
                ('is_active', '=', True),
                ('period_type_id', '=', school_year_type.id)
            ], limit=1)
            
            # Get org types
            OrgType = self.env['myschool.org.type']
            org_type_group = OrgType.search([('name', '=', 'GROUP')], limit=1)
            
            Org = self.env['myschool.org']
            checked_classes: List[str] = []
            
            for persoon_id, registration_json in all_registrations.items():
                registration = json.loads(registration_json)
                
                self._create_sys_event("SAPSYNC-001", f"Processing registration for {persoon_id}")
                
                # Process inschrKlassen (class registrations)
                inschr_klassen = registration.get('inschrklassen', []) or registration.get('inschrKlassen', [])
                inst_nr = registration.get('instelnr', '')
                
                for klas in inschr_klassen:
                    klas_code = klas.get('klasCode', '')
                    this_class = f"{klas_code}-{inst_nr}"
                    task_action = ''
                    
                    # Skip if already checked
                    if this_class in checked_classes:
                        continue
                    
                    # Check if class exists in database
                    existing_classes = Org.search([
                        ('name_short', '=', klas_code),
                        ('period_id', '=', current_period.id),
                        ('org_type_id', '=', org_type_group.id),
                        ('is_active', '=', True)
                    ])
                    
                    if not existing_classes:
                        task_action = 'ADD'
                        checked_classes.append(this_class)
                    else:
                        # Check if class exists for this institution
                        class_found = False
                        for org in existing_classes:
                            if org.inst_nr == inst_nr:
                                class_found = True
                                checked_classes.append(this_class)
                                break
                        
                        if not class_found:
                            task_action = 'ADD'
                            checked_classes.append(this_class)
                    
                    # Create task if needed
                    if task_action:
                        task_data = {
                            'orgtype': 'GROUP',
                            'isadm': 'false',
                            'name': klas_code,
                            'instnr': inst_nr,
                            'period': current_period.id
                        }
                        self._create_betask('DB', 'ORG', task_action, json.dumps(task_data), '')
            
            # Check for classes to deactivate
            all_active_classes = Org.search([
                ('period_id', '=', current_period.id),
                ('org_type_id', '=', org_type_group.id),
                ('is_active', '=', True)
            ])
            
            for org in all_active_classes:
                class_key = f"{org.name_short}-{org.inst_nr}"
                if class_key not in checked_classes:
                    task_data = {
                        'orgId': org.id,
                        'name': org.name_short,
                        'instnr': org.inst_nr,
                        'period': current_period.id
                    }
                    self._create_betask('DB', 'ORG', 'DEACT', json.dumps(task_data), '')
            
            return True
            
        except Exception as e:
            self._create_sys_error("BETASK-900", f"{procedure_name}: {traceback.format_exc()}")
            return False

    def _analyze_data_and_create_student_tasks(self, all_registrations: Dict[str, str], 
                                                all_students: Dict[str, str]) -> bool:
        """
        Analyze imported data and create Student tasks.
        
        Equivalent to Java: AnalyzeInformatDataAndCreateStudentDbTasks()
        
        @param all_registrations: Dict with registration data
        @param all_students: Dict with student data
        @return: True if successful
        """
        procedure_name = '_analyze_data_and_create_student_tasks'
        
        if not all_registrations and not all_students:
            self._create_sys_error("BETASK-900", f"{procedure_name}: parameters are empty")
            return False
        
        try:
            Person = self.env['myschool.person']
            processed_students: List[str] = []
            
            for persoon_id, registration_json in all_registrations.items():
                registration = json.loads(registration_json)
                
                # Get student details if available
                student_details = {}
                if persoon_id in all_students:
                    student_details = json.loads(all_students[persoon_id])
                
                # Check if person exists in database
                existing_persons = Person.search([('sap_person_uuid', '=', persoon_id)])
                
                if not existing_persons:
                    # Create ADD task
                    action = 'ADD'
                    person_data = self._merge_registration_and_student_data(registration, student_details)
                    self._create_betask('DB', 'STUDENT', 'ADD', json.dumps(person_data), '')
                    
                elif len(existing_persons) == 1:
                    # Check for updates
                    person_in_db = existing_persons[0]
                    
                    # Check for deactivation (new end date)
                    reg_end_date = registration.get('regEndDate')
                    if reg_end_date and not person_in_db.reg_end_date:
                        task_data = {
                            'uuid': person_in_db.sap_person_uuid,
                            'regEndDate': reg_end_date
                        }
                        self._create_betask('DB', 'STUDENT', 'DEACT', json.dumps(task_data), '')
                        continue
                    
                    # Check for reactivation
                    if not reg_end_date and person_in_db.reg_end_date:
                        task_data = {
                            'uuid': person_in_db.sap_person_uuid,
                            'regEndDate': None,
                            'regGroupCode': registration.get('regGroupCode'),
                            'regInstNr': registration.get('regInstNr'),
                            'regStartDate': registration.get('regStartDate')
                        }
                        self._create_betask('DB', 'STUDENT', 'UPD', json.dumps(task_data), '')
                        continue
                    
                    # Check for field updates
                    diff_new, diff_original = self._compare_person_fields(
                        person_in_db, 
                        self._merge_registration_and_student_data(registration, student_details)
                    )
                    
                    if diff_new:
                        diff_new['persoonId'] = person_in_db.sap_person_uuid
                        diff_original['persoonId'] = person_in_db.sap_person_uuid
                        self._create_betask('DB', 'STUDENT', 'UPD', json.dumps(diff_new), json.dumps(diff_original))
                
                processed_students.append(persoon_id)
            
            return True
            
        except Exception as e:
            self._create_sys_error("BETASK-900", f"{procedure_name}: {traceback.format_exc()}")
            return False

    def _analyze_data_and_create_relation_tasks(self, all_students: Dict[str, str]) -> bool:
        """
        Analyze imported student data and create Relation tasks.
        
        Equivalent to Java: AnalyzeInformatDataAndCreateRelationDbTasks()
        
        @param all_students: Dict with student data including relations
        @return: True if successful
        """
        procedure_name = '_analyze_data_and_create_relation_tasks'
        
        if not all_students:
            self._create_sys_error("BETASK-900", f"{procedure_name}: parameter is empty")
            return False
        
        try:
            self._create_sys_event("BETASK-001", f"{procedure_name} started")
            
            Person = self.env['myschool.person']
            
            for persoon_id, student_json in all_students.items():
                student = json.loads(student_json)
                
                # Process relations
                relations = student.get('relaties', [])
                relations_map: Dict[str, str] = {}
                
                for relation in relations:
                    relatie_id = relation.get('relatieId')
                    if relatie_id and relatie_id not in relations_map:
                        relations_map[relatie_id] = json.dumps(relation)
                
                # Analyze and create tasks for each relation
                for relatie_id, relation_json in relations_map.items():
                    existing_persons = Person.search([('sap_person_uuid', '=', relatie_id)])
                    
                    if not existing_persons:
                        # Create ADD task for new relation
                        self._create_betask('DB', 'RELATION', 'ADD', relation_json, 'RELATION')
                    else:
                        # Check for updates
                        relation_data = json.loads(relation_json)
                        person_in_db = existing_persons[0]
                        
                        diff_new, diff_original = self._compare_relation_fields(person_in_db, relation_data)
                        
                        if diff_new:
                            diff_new['persoonId'] = person_in_db.sap_person_uuid
                            diff_original['persoonId'] = person_in_db.sap_person_uuid
                            self._create_betask('DB', 'RELATION', 'UPD', json.dumps(diff_new), json.dumps(diff_original))
            
            return True
            
        except Exception as e:
            self._create_sys_error("BETASK-900", f"{procedure_name}: {traceback.format_exc()}")
            return False

    def _analyze_employee_assignments_and_create_roles(self, all_assignments: Dict[str, str]) -> bool:
        """
        Analyze employee assignments and create new roles if needed.
        
        For informat: just create the SapRoles via a DB-ADD-ROLE Task. When a new role is added, create a sysevent
        informing the admin that a new SAPROLE is create and that is should be linked to a BackendRole


        @param all_assignments: Dict with assignment data
        @return: True if successful
        """
        procedure_name = '_analyze_employee_assignments_and_create_roles'
        
        if not all_assignments:
            self._create_sys_error("BETASK-900", f"{procedure_name}: parameter is empty")
            return False
        
        try:
            Role = self.env['myschool.role']
            BeTask = self.env['myschool.betask.service']
            processed_assignments: List[str] = []
            first_task = True
            
            for assignment_key, assignment_json in all_assignments.items():
                assignment = json.loads(assignment_json)
                
                self._create_sys_event("BETASK-001", f"Processing assignment: {assignment_key}")
                
                # Get HoofdAmbt (main position) details
                hoofd_ambt_name = assignment.get('ambt', '')
                hoofd_ambt_code = assignment.get('ambtCode', '')
                role_type = self.env['myschool.role.type'].search(
                    [('name', '=', 'SAP')], limit=1)
                
                if hoofd_ambt_code not in processed_assignments:
                    # Check if role exists
                    existing_roles = Role.search([('shortname', '=', hoofd_ambt_code)])
                    
                    if not existing_roles:
                        # Create role task
                        task_data = {
                            'name': hoofd_ambt_name,
                            'shortname': hoofd_ambt_code,
                            'automatic_sync': True,
                            'is_active': True,
                            'role_type_id': role_type.id,
                        }
                            # 'createNewBeRole': 'true/false',
                            # 'beRoleName': 'ADAPT',
                            # 'beRoleShortName': 'ADAPT',
                            # 'existingBeRoleId': ''
                        #}
                        #  15.01.26: TODO : remove code after testing
                        # if first_task:
                        #     message = ("A DB-ROLE-ADD task has been created. Please update the field in the JSON String "
                        #               "to reflect the new name and position in the Org Structure. "
                        #               "Set The Status to COMPLETED_OK when done")
                        #     # self._create_betask('ALL', 'ROLE', 'MANUAL', message, '')
                        #     BeTask.create_task('ALL', 'ROLE', 'MANUAL', message, '')
                        #     first_task = False
                        #
                        self._create_betask('DB', 'ROLE', 'ADD', json.dumps(task_data), '')
                        self._create_sys_event("BETASK-001", f"a New SapRole is create. Link manual to a BackendRole and link this BR to one or moge Orgs: {assignment_key}")

                    # elif len(existing_roles) > 1:
                    #     # self._create_sys_error("ROLE-ADD",
                    #     #     f"{len(existing_roles)} relations for {hoofd_ambt_name} found. Please correct")
                    #     return False
                
                processed_assignments.append(hoofd_ambt_code)
            
            return True
            
        except Exception as e:
            self._create_sys_error("BETASK-900", f"{procedure_name}: {traceback.format_exc()}")
            return False

    def _analyze_employee_assignments_and_create_role_org_relations(self, all_assignments: Dict[str, str]) -> bool:
        """
        Analyze employee assignments and create role-org relations.
        
        Equivalent to Java: AnalyzeInformatEmployeeAssignmentsAndCreateEmployeeRoleOrgRelations()
        
        @param all_assignments: Dict with assignment data
        @return: True if successful
        """
        procedure_name = '_analyze_employee_assignments_and_create_role_org_relations'
        
        if not all_assignments:
            self._create_sys_error("BETASK-900", f"{procedure_name}: parameter is empty")
            return False
        
        try:
            Role = self.env['myschool.role']
            Org = self.env['myschool.org']
            PropRelation = self.env['myschool.proprelation']
            
            processed_assignments: List[str] = []
            first_task = True
            
            for assignment_key, assignment_json in all_assignments.items():
                assignment = json.loads(assignment_json)
                
                self._create_sys_event("BETASK-001", f"Processing assignment: {assignment_key}")
                
                # Extract institution number from key
                assignment_inst_nr = assignment_key.split('&')[1] if '&' in assignment_key else ''
                
                # Get HoofdAmbt details
                hoofd_ambt_name = assignment.get('ambt', '')
                hoofd_ambt_code = assignment.get('ambtCode', '')
                hoofd_ambt_inst_nr = f"{hoofd_ambt_code}&{assignment_inst_nr}"
                
                if hoofd_ambt_inst_nr not in processed_assignments:
                    # Find SAP role
                    sap_role = Role.search([('shortname', '=', hoofd_ambt_code)], limit=1)
                    
                    if sap_role:
                        # Find role relations
                        role_relations = PropRelation.search([
                            ('role_id', '=', sap_role.id),
                            ('prop_relation_type_id.name', '=', 'PtSapRoleBeRole')
                        ])
                        
                        # Find school org
                        school_org = Org.search([
                            ('inst_nr', '=', assignment_inst_nr),
                            ('is_active', '=', True),
                            ('org_type_id.name', '=', 'SCHOOL')
                        ], limit=1)
                        
                        if len(role_relations) == 1:
                            be_role = role_relations[0].role_parent_id
                            
                            task_data = {
                                'beRoleId': be_role.id if be_role else '',
                                'schoolOrgId': school_org.id if school_org else '',
                                'linkToOrg': 'true (caution: false will require later manual linking)',
                                'useExistingOrg': 'true/false',
                                'existingOrgId': 'ADAPT',
                                'newOrgParentOrgId': 'ADAPT',
                                'newOrgName': 'ADAPT',
                                'hasOU': 'TRUEFALSE',
                                'hasComGroup': 'TRUEFALSE',
                                'hasSecGroup': 'TRUEFALSE'
                            }
                            
                            if first_task:
                                message = ("A ALL-ROLE-UPD task has been created. Please update the field in the JSON String "
                                          "to reflect the new name and position in the Org Structure. "
                                          "Set The Status to COMPLETED_OK when done")
                                self._create_betask('ALL', 'ROLE', 'MANUAL', message, '')
                                first_task = False
                            
                            self._create_betask('ALL', 'ROLE', 'UPD', json.dumps(task_data), '')
                        
                        elif len(role_relations) > 1:
                            self._create_sys_error("ROLE-ADD", 
                                f"{len(role_relations)} relations for {hoofd_ambt_name} found. Please correct")
                
                processed_assignments.append(hoofd_ambt_inst_nr)
            
            return True
            
        except Exception as e:
            self._create_sys_error("BETASK-900", f"{procedure_name}: {traceback.format_exc()}")
            return False

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _check_blocking_tasks(self) -> bool:
        """Check for system blocking tasks."""
        BeTask = self.env.get(self.BETASK_MODEL)
        BeTaskType = self.env.get(self.BETASK_TYPE_MODEL)
        
        if not self.BETASK_MODEL or self.BETASK_TYPE_MODEL in self.env:
            _logger.warning(f"BeTask model '{self.BETASK_MODEL}' or BeTaskType model '{self.BETASK_TYPE_MODEL}' not found")
            return False

        blocking_task_type = BeTaskType.search([
            (self.BETASKTYPE_TARGET_FIELD, '=', 'SYSTEM'),
            (self.BETASKTYPE_OBJECT_FIELD, '=', 'BLOCKINGMESSAGE'),
            (self.BETASKTYPE_ACTION_FIELD, '=', 'MANUAL')
        ], limit=1)
        
        if blocking_task_type:
            blocking_tasks = BeTask.search([
                (self.BETASK_TYPE_FIELD, '=', blocking_task_type.id),
                (self.BETASK_STATUS_FIELD, '=', self.STATUS_NEW)
            ])
            
            if blocking_tasks:
                self._create_sys_error("SAPSYNC-900", 
                    "A System Blocking Task is found. Please check, correct and set status to COMPLETED_OK")
                return True
        
        return False

    def _check_manual_role_tasks(self) -> bool:
        """Check for manual role tasks."""
        BeTask = self.env.get(self.BETASK_MODEL)
        BeTaskType = self.env.get(self.BETASK_TYPE_MODEL)

        manual_task_type = BeTaskType.search([
            (self.BETASKTYPE_TARGET_FIELD, '=', 'ALL'),
            (self.BETASKTYPE_OBJECT_FIELD, '=', 'ROLE'),
            (self.BETASKTYPE_ACTION_FIELD, '=', 'MANUAL')
        ], limit=1)
        
        if manual_task_type:
            manual_tasks = BeTask.search([
                (self.BETASK_TYPE_FIELD, '=', manual_task_type.id),
                (self.BETASK_STATUS_FIELD, '=', self.STATUS_NEW)
            ])
            
            if manual_tasks:
                self._create_sys_error("SAPSYNC-900", 
                    "A Manual Role Task is found. Please update the role manual and set status to COMPLETED_OK")
                return True
        
        return False

    ## LOOT VIA TASKPROCESSOR
    def _process_betasks(self, target: str, obj: str, action: str) -> None:
        """
        Process BeTasks of a specific type.
        
        @param target: Task target (DB, LDAP, ALL)
        @param obj: Task object (STUDENT, EMPLOYEE, ORG, ROLE, etc.)
        @param action: Task action (ADD, UPD, DEACT, etc.)
        """
        BeTaskProcessor = self.env.get('myschool.betask.processor')
        BeTaskType = self.env.get(self.BETASK_TYPE_MODEL)

        task_type = BeTaskType.search([
            (self.BETASKTYPE_TARGET_FIELD, '=', target),
            (self.BETASKTYPE_OBJECT_FIELD, '=', obj),
            (self.BETASKTYPE_ACTION_FIELD, '=', action)
        ], limit=1)

        if task_type.exists():
            BeTaskProcessor.process_tasks_by_type(task_type)
        elif task_type:
            _logger.info(f"Task type found for {target}-{obj}-{action}, but no processor available")

    def _create_betask(self, target: str, obj: str, action: str, data: str, data2: str) -> Any:
        """
        Create a BeTask record.
        
        @param target: Task target
        @param obj: Task object
        @param action: Task action
        @param data: JSON data for the task
        @param data2: Additional JSON data
        @return: Created BeTask record
        """
        # BeTaskService = self.env.get('myschool.betask.service')
        # if BeTaskService and hasattr(BeTaskService, 'create_betask'):
        #     return BeTaskService.create_betask(target, obj, action, data, data2)
        #
        # # Fallback: create directly
        BeTask = self.env.get(self.BETASK_MODEL)
        BeTaskType = self.env.get(self.BETASK_TYPE_MODEL)
        #
        # if not BeTask or not BeTaskType:
        #     _logger.error(f"BeTask model '{self.BETASK_MODEL}' or BeTaskType model '{self.BETASK_TYPE_MODEL}' not found")
        #     return None
        #
        task_type = BeTaskType.search([
            (self.BETASKTYPE_TARGET_FIELD, '=', target),
            (self.BETASKTYPE_OBJECT_FIELD, '=', obj),
            (self.BETASKTYPE_ACTION_FIELD, '=', action)
        ], limit=1)
        
        if task_type:
            try:

                json_data = json.loads(data)


                if task_type.object == "EMPLOYEE":
                   taskname = action + " " + obj + ": " + json_data["sortName"]
                elif task_type.object == "ROLE":
                    taskname = action + " " + obj + ": " + json_data["name"]
                elif task_type.object == "PROPRELATION":
                    taskname = action + " " + obj + ": " + str(json_data["person_db_id"])   #todo: naam aanpassen

                vals = {
                    self.BETASK_TYPE_FIELD: task_type.id,
                    self.BETASK_STATUS_FIELD: self.STATUS_NEW,
                    self.BETASK_NAME_FIELD: taskname
                }
                # Only add data fields if they exist in the model
                if self.BETASK_DATA_FIELD in BeTask._fields:
                    vals[self.BETASK_DATA_FIELD] = data
                if data2 and self.BETASK_DATA2_FIELD in BeTask._fields:
                    vals[self.BETASK_DATA2_FIELD] = data2
                    
                return BeTask.create(vals)
            except Exception as e:
                _logger.error(f"Error creating BeTask: {e}")
                return None
        else:
            _logger.warning(f"BeTaskType not found for: {target}-{obj}-{action}")
        
        return None

    def _create_sys_event(self, code: str, message: str) -> None:
        """Create a system event log entry."""
        _logger.info(f"{code}: {message}")

        if 'myschool.sys.event.service' in self.env:
            self.env['myschool.sys.event.service'].create_sys_event(code, message, True)

        # SysEvent = self.env.get('myschool.sys.event.service')
        # if SysEvent:
        #     SysEvent.create_sys_event(code, message, True)

    def _create_sys_error(self, code: str, message: str, error_type: str = 'ERROR-BLOCKING') -> None:
        """Create a system error log entry."""
        _logger.error(f"{code}: {message}")
        
        SysEvent = self.env.get('myschool.sys.event.service')
        if SysEvent:
            SysEvent.create_sys_error(code, message, error_type, True)

    def _read_json_file(self, file_path: str) -> Optional[List[Dict]]:
        """
        Read and parse a JSON file.
        
        @param file_path: Path to the JSON file
        @return: Parsed JSON data or None if file doesn't exist
        """
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return None
        except Exception as e:
            _logger.error(f"Error reading JSON file {file_path}: {e}")
            return None

    def _write_json_file(self, file_path: str, content: str) -> bool:
        """
        Write content to a JSON file.
        
        @param file_path: Path to the JSON file
        @param content: Content to write
        @return: True if successful
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            _logger.error(f"Error writing JSON file {file_path}: {e}")
            return False

    def _merge_registration_and_student_data(self, registration: Dict, student: Dict) -> Dict:
        """
        Merge registration and student data into a single dict.
        
        @param registration: Registration data
        @param student: Student details data
        @return: Merged data dict
        """
        merged = {}
        
        # Add registration fields
        merged.update(registration)
        
        # Add/override with student fields
        if student:
            for key, value in student.items():
                if key not in merged or merged[key] is None:
                    merged[key] = value
        
        return merged

    def _compare_person_fields(self, person_in_db: Any, new_data: Dict) -> tuple:
        """
        Compare person fields and return differences.
        
        @param person_in_db: Person record from database
        @param new_data: New data from import
        @return: Tuple of (new_values_dict, original_values_dict)
        """
        skip_fields = ['id', 'person_type', 'sap_ref', 'sap_person_uuid', 
                       'reg_inst_nr', 'reg_group_code', 'reg_end_date', 'reg_start_date']
        
        diff_new = {}
        diff_original = {}
        
        # Map of Python field names to JSON field names
        field_mapping = {
            'first_name': 'firstName',
            'last_name': 'lastName',
            'birth_date': 'birthDate',
            'gender': 'gender',
            'nationality': 'nationality',
            # Add more field mappings as needed
        }
        
        for py_field, json_field in field_mapping.items():
            if py_field in skip_fields:
                continue
            
            db_value = getattr(person_in_db, py_field, None)
            new_value = new_data.get(json_field)
            
            # Handle date comparisons
            if isinstance(db_value, (datetime,)):
                db_value = db_value.strftime('%Y-%m-%d') if db_value else None
            
            if db_value != new_value:
                if db_value is None and new_value is not None:
                    diff_new[json_field] = new_value
                    diff_original[json_field] = 'null'
                elif db_value is not None and new_value is None:
                    diff_new[json_field] = 'null'
                    diff_original[json_field] = db_value
                elif db_value != new_value:
                    diff_new[json_field] = new_value
                    diff_original[json_field] = db_value
        
        return diff_new, diff_original

    def _compare_relation_fields(self, person_in_db: Any, new_data: Dict) -> tuple:
        """
        Compare relation fields and return differences.
        
        @param person_in_db: Person record from database
        @param new_data: New relation data from import
        @return: Tuple of (new_values_dict, original_values_dict)
        """
        diff_new = {}
        diff_original = {}
        
        # Define fields to compare for relations
        relation_fields = ['firstName', 'lastName', 'relatieType', 'phone', 'email']
        
        for field in relation_fields:
            db_value = getattr(person_in_db, self._json_to_python_field(field), None)
            new_value = new_data.get(field)
            
            if db_value != new_value:
                if new_value is not None and db_value is None:
                    diff_new[field] = new_value
                    diff_original[field] = None
                elif new_value is None and db_value is not None:
                    diff_new[field] = None
                    diff_original[field] = db_value
                elif new_value != db_value:
                    diff_new[field] = new_value
                    diff_original[field] = db_value
        
        return diff_new, diff_original

    def _json_to_python_field(self, json_field: str) -> str:
        """Convert camelCase JSON field to snake_case Python field."""
        import re
        return re.sub(r'(?<!^)(?=[A-Z])', '_', json_field).lower()
