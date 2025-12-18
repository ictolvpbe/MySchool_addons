# -*- coding: utf-8 -*-
"""
Backend Task Type Service
Converted from BeTaskTypeServiceImpl.java

This module provides the service layer for managing backend task types.

Java Methods Implemented:
- findById(String id) -> find_by_id(type_id)
- findAll() -> find_all()
- registerOrUpdateBeTaskType(BeTaskType) -> register_or_update(vals)
- createBeTaskType(String target, String object, String action) -> create_task_type(target, obj, action)
- findBeTaskTypeByTargetAndObjectAndAction(...) -> find_by_target_object_action(...)
"""

from odoo import models, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class BeTaskTypeService(models.AbstractModel):
    """
    Service class for Backend Task Type operations
    Equivalent to BeTaskTypeServiceImpl.java + BeTaskTypeDao.java
    
    Usage:
        service = self.env['myschool.betask.type.service']
        task_type = service.find_by_target_object_action('DB', 'ORG', 'ADD')
    """
    _name = 'myschool.betask.type.service'
    _description = 'Backend Task Type Service'
    
    # =========================================================================
    # DAO Methods (from BeTaskTypeDao.java)
    # =========================================================================
    
    @api.model
    def find_by_id(self, type_id):
        """
        Find task type by ID
        Equivalent to: findBeTaskTypeById(String id)
        
        :param type_id: Task type ID
        :return: Task type record or empty recordset
        """
        if not type_id:
            return self.env['myschool.betask.type']
        return self.env['myschool.betask.type'].browse(type_id).exists()
    
    @api.model
    def find_by_name(self, name):
        """
        Find task type by name
        Equivalent to: findBeTaskTypeByName(String name)
        
        :param name: Name of the task type
        :return: Task type record (empty recordset if not found)
        """
        if not name:
            return self.env['myschool.betask.type']
        result = self.env['myschool.betask.type'].search([('name', '=', name)], limit=1)
        return result
    
    @api.model
    def find_by_action(self, action):
        """
        Find task type by action
        Equivalent to: findBeTaskTypeByAction(String action)
        
        :param action: Action (ADD, UPD, DEL, etc.)
        :return: Task type record (empty recordset if not found)
        """
        if not action:
            return self.env['myschool.betask.type']
        return self.env['myschool.betask.type'].search([('action', '=', action)], limit=1)
    
    @api.model
    def find_by_target(self, target):
        """
        Find task type by target
        Equivalent to: findBeTaskTypeByTarget(String target)
        
        :param target: Target (DB, AD, CLOUD, etc.)
        :return: Task type record (empty recordset if not found)
        """
        if not target:
            return self.env['myschool.betask.type']
        return self.env['myschool.betask.type'].search([('target', '=', target)], limit=1)
    
    @api.model
    def find_by_target_object_action(self, target, obj, action):
        """
        Find task type by target, object, and action combination
        Equivalent to: findBeTaskTypeByTargetAndObjectAndAction(String target, String object, String action)
        
        :param target: Target system (DB, AD, CLOUD, etc.)
        :param obj: Object type (ORG, PERSON, ROLE, etc.)
        :param action: Action (ADD, UPD, DEL, etc.)
        :return: Task type record (empty recordset if not found)
        """
        if not all([target, obj, action]):
            return self.env['myschool.betask.type']
        
        return self.env['myschool.betask.type'].search([
            ('target', '=', target),
            ('object', '=', obj),
            ('action', '=', action)
        ], limit=1)
    
    @api.model
    def find_all_by_target_object_action(self, target, obj, action):
        """
        Find all task types matching criteria
        Equivalent to: findBeTasksTypeByTargetAndObjectAndAction(...)
        
        :return: Recordset of matching task types
        """
        domain = []
        if target:
            domain.append(('target', '=', target))
        if obj:
            domain.append(('object', '=', obj))
        if action:
            domain.append(('action', '=', action))
        
        return self.env['myschool.betask.type'].search(domain)
    
    @api.model
    def find_all(self):
        """
        Find all task types
        Equivalent to: findAll()
        
        :return: Recordset of all task types
        """
        return self.env['myschool.betask.type'].search([])
    
    @api.model
    def find_all_active(self):
        """
        Find all active task types
        
        :return: Recordset of all active task types
        """
        return self.env['myschool.betask.type'].search([('active', '=', True)])
    
    @api.model
    def find_auto_process_types(self):
        """
        Find all task types that should be auto-processed
        
        :return: Recordset of auto-process task types, ordered by priority
        """
        return self.env['myschool.betask.type'].search([
            ('active', '=', True),
            ('auto_process', '=', True)
        ], order='priority')
    
    # =========================================================================
    # Service Methods (from BeTaskTypeServiceImpl.java)
    # =========================================================================
    
    @api.model
    def register_or_update(self, vals):
        """
        Register a new task type or update existing one
        Equivalent to: registerOrUpdateBeTaskType(BeTaskType pbeTaskType)
        
        :param vals: Dictionary with task type values
        :return: Task type record
        """
        TaskType = self.env['myschool.betask.type']
        
        if isinstance(vals, models.BaseModel):
            return vals
        
        if not isinstance(vals, dict):
            raise ValidationError(_('Invalid task type data provided'))
        
        # Try to find existing by target/object/action combination
        if all(k in vals for k in ['target', 'object', 'action']):
            existing = self.find_by_target_object_action(
                vals['target'], vals['object'], vals['action']
            )
            if existing:
                existing.write(vals)
                _logger.info(f'Updated BeTaskType: {existing.name}')
                return existing
        
        # Try to find by ID
        if vals.get('id'):
            existing = TaskType.browse(vals['id']).exists()
            if existing:
                update_vals = {k: v for k, v in vals.items() if k != 'id'}
                existing.write(update_vals)
                _logger.info(f'Updated BeTaskType by ID: {existing.name}')
                return existing
        
        # Create new
        new_type = TaskType.create(vals)
        _logger.info(f'Created new BeTaskType: {new_type.name}')
        return new_type
    
    @api.model
    def create_task_type(self, target, obj, action, description=None):
        """
        Create a new task type
        Equivalent to: createBeTaskType(String pTarget, String pObject, String pAction)
        
        :param target: Target system (DB, AD, CLOUD, etc.)
        :param obj: Object type (ORG, PERSON, ROLE, etc.)
        :param action: Action (ADD, UPD, DEL, etc.)
        :param description: Optional description
        :return: Created task type record
        """
        # Check if already exists
        existing = self.find_by_target_object_action(target, obj, action)
        if existing:
            _logger.info(f'BeTaskType already exists: {existing.name}')
            return existing
        
        # Create new (name is auto-generated in model)
        vals = {
            'target': target,
            'object': obj,
            'action': action,
            'description': description or f'Task type for {target} {obj} {action}',
        }
        
        task_type = self.env['myschool.betask.type'].create(vals)
        _logger.info(f'Created BeTaskType: {task_type.name}')
        return task_type
    
    @api.model
    def get_or_create(self, target, obj, action, **kwargs):
        """
        Get a task type, create if it doesn't exist
        
        :param target: Target system
        :param obj: Object type
        :param action: Action
        :param kwargs: Additional fields (description, auto_process, etc.)
        :return: Task type record
        """
        task_type = self.find_by_target_object_action(target, obj, action)
        if not task_type:
            vals = {
                'target': target,
                'object': obj,
                'action': action,
                **kwargs
            }
            task_type = self.env['myschool.betask.type'].create(vals)
            _logger.info(f'Created BeTaskType: {task_type.name}')
        return task_type
    
    @api.model
    def ensure_standard_types(self):
        """
        Ensure all standard task types exist
        Call this during module installation or upgrade
        """
        standard_types = [
            # Database operations
            ('DB', 'ORG', 'ADD', 'Add organization to database'),
            ('DB', 'ORG', 'UPDATE', 'Update organization in database'),
            ('DB', 'ORG', 'DEL', 'Delete organization from database'),
            ('DB', 'PERSON', 'ADD', 'Add person to database'),
            ('DB', 'PERSON', 'UPDATE', 'Update person in database'),
            ('DB', 'STUDENT', 'ADD', 'Add student to database'),
            ('DB', 'STUDENT', 'UPDATE', 'Update student in database'),
            ('DB', 'EMPLOYEE', 'ADD', 'Add employee to database'),
            ('DB', 'EMPLOYEE', 'UPD', 'Update employee in database'),
            ('DB', 'ROLE', 'ADD', 'Add role to database'),
            ('DB', 'RELATION', 'ADD', 'Add relation to database'),
            
            # LDAP/AD operations
            ('LDAP', 'ORG', 'ADD', 'Add organization to LDAP'),
            ('LDAP', 'STUDENT', 'ADD', 'Add student to LDAP'),
            ('LDAP', 'EMPLOYEE', 'ADD', 'Add employee to LDAP'),
            ('LDAP', 'EMPLOYEE', 'UPD', 'Update employee in LDAP'),
            
            # All systems
            ('ALL', 'ROLE', 'UPD', 'Update role in all systems'),
            
            # Manual tasks
            ('MANUAL', 'CONFIG', 'MANUAL', 'Manual configuration task'),
        ]
        
        created = []
        for target, obj, action, desc in standard_types:
            task_type = self.get_or_create(target, obj, action, description=desc)
            created.append(task_type)
        
        _logger.info(f'Ensured {len(created)} standard BeTaskTypes exist')
        return created
