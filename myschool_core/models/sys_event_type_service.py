# -*- coding: utf-8 -*-
"""
System Event Type Service/Logic
Converted from SysEventTypeServiceImpl.java

This module provides the service layer for managing system event types,
equivalent to the Java Spring Boot service pattern.

Java Interface Methods Implemented:
- findById(String id) -> find_by_id(event_type_id)
- findAll() -> find_all()
- registerOrUpdateSysEventType(SysEventType) -> register_or_update(vals)
- createSysEventType(String name, Integer priority) -> create_event_type(name, priority)
- findSysEventTypeByName(String name) -> find_by_name(name) [from DAO]
"""

from odoo import models, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class SysEventTypeService(models.AbstractModel):
    """
    Service class for System Event Type operations
    Equivalent to SysEventTypeServiceImpl.java + SysEventTypeDao.java
    
    Usage:
        service = self.env['myschool.sys.event.type.service']
        event_type = service.find_by_name('ERROR-BLOCKING')
    """
    _name = 'myschool.sys.event.type.service'
    _description = 'System Event Type Service'
    
    # =========================================================================
    # DAO Methods (from SysEventTypeDao.java)
    # =========================================================================
    
    @api.model
    def find_by_id(self, event_type_id):
        """
        Find event type by ID
        Equivalent to: findSysEventTypeById(String id)
        
        :param event_type_id: Event type ID (int)
        :return: Event type record or empty recordset
        """
        if not event_type_id:
            return self.env['myschool.sys.event.type']
        return self.env['myschool.sys.event.type'].browse(event_type_id).exists()
    
    @api.model
    def find_by_name(self, name):
        """
        Find event type by name
        Equivalent to: findSysEventTypeByName(String name)
        
        :param name: Name of the event type (e.g., 'EVENT', 'ERROR-BLOCKING')
        :return: Event type record (empty recordset if not found)
        """
        if not name:
            return self.env['myschool.sys.event.type']
        return self.env['myschool.sys.event.type'].search([('name', '=', name)], limit=1)
    
    @api.model
    def find_by_code(self, code):
        """
        Find event type by code
        
        :param code: Code of the event type
        :return: Event type record (empty recordset if not found)
        """
        if not code:
            return self.env['myschool.sys.event.type']
        return self.env['myschool.sys.event.type'].search([('code', '=', code)], limit=1)
    
    @api.model
    def find_all(self):
        """
        Find all event types
        Equivalent to: findAll()
        
        :return: Recordset of all event types
        """
        return self.env['myschool.sys.event.type'].search([])
    
    @api.model
    def find_all_active(self):
        """
        Find all active event types
        
        :return: Recordset of all active event types
        """
        return self.env['myschool.sys.event.type'].search([('active', '=', True)])
    
    # =========================================================================
    # Service Methods (from SysEventTypeServiceImpl.java)
    # =========================================================================
    
    @api.model
    def register_or_update(self, vals):
        """
        Register a new event type or update existing one
        Equivalent to: registerOrUpdateSysEventType(SysEventType sysEventType)
        
        In Java, this uses saveAndFlush which creates or updates based on ID.
        
        :param vals: Dictionary with event type values or record
        :return: Event type record
        """
        EventType = self.env['myschool.sys.event.type']
        
        if isinstance(vals, models.BaseModel):
            # Already a record, just return it
            return vals
        
        if not isinstance(vals, dict):
            raise ValidationError(_('Invalid event type data provided'))
        
        # If ID is provided, try to update existing
        if vals.get('id'):
            existing = EventType.browse(vals['id']).exists()
            if existing:
                update_vals = {k: v for k, v in vals.items() if k != 'id'}
                existing.write(update_vals)
                _logger.info(f'Updated SysEventType: {existing.name}')
                return existing
        
        # Try to find by name (for upsert behavior)
        if vals.get('name'):
            existing = self.find_by_name(vals['name'])
            if existing:
                existing.write(vals)
                _logger.info(f'Updated existing SysEventType by name: {existing.name}')
                return existing
        
        # Create new
        new_type = EventType.create(vals)
        _logger.info(f'Created new SysEventType: {new_type.name}')
        return new_type
    
    @api.model
    def create_event_type(self, name, priority=2, code=None, description=None):
        """
        Create a new event type
        Equivalent to: createSysEventType(String name, Integer priority)
        
        :param name: Name of the event type
        :param priority: Default priority (0-3), defaults to 2
        :param code: Unique code (auto-generated from name if not provided)
        :param description: Description of the event type
        :return: Created event type record
        """
        # Convert priority to string selection
        priority_str = str(priority) if priority in [0, 1, 2, 3] else '2'
        
        vals = {
            'name': name,
            'code': code or name.replace(' ', '_').replace('-', '_').upper(),
            'priority': priority_str,
            'description': description or f'Event type: {name}',
        }
        
        event_type = self.env['myschool.sys.event.type'].create(vals)
        _logger.info(f'Created SysEventType: {event_type.name} with priority {priority_str}')
        return event_type
    
    @api.model
    def get_or_create(self, name, code=None, priority=2, description=None):
        """
        Get an event type by name, create if it doesn't exist
        Helper method to ensure event types exist (used by SysEventService)
        
        :param name: Name of the event type
        :param code: Code for the event type
        :param priority: Default priority for new events of this type
        :param description: Description of the event type
        :return: Event type record
        """
        event_type = self.find_by_name(name)
        if not event_type:
            event_type = self.create_event_type(
                name=name,
                priority=priority,
                code=code,
                description=description
            )
        return event_type
    
    @api.model
    def ensure_standard_types(self):
        """
        Ensure all standard event types exist
        Call this during module installation or upgrade
        
        Standard types (matching Java application):
        - EVENT: General system events
        - ERROR-BLOCKING: Blocking errors that require immediate attention
        - ERROR-NONBLOCKING: Non-blocking errors that can be processed later
        """
        standard_types = [
            {
                'name': 'EVENT',
                'code': 'EVENT',
                'priority': '3',
                'description': 'General system event for logging and monitoring'
            },
            {
                'name': 'ERROR-BLOCKING',
                'code': 'ERROR_BLOCKING',
                'priority': '1',
                'description': 'Blocking error that requires immediate attention and stops processing'
            },
            {
                'name': 'ERROR-NONBLOCKING',
                'code': 'ERROR_NONBLOCKING',
                'priority': '2',
                'description': 'Non-blocking error that is logged but allows processing to continue'
            },
        ]
        
        created = []
        for type_vals in standard_types:
            event_type = self.get_or_create(
                name=type_vals['name'],
                code=type_vals['code'],
                priority=int(type_vals['priority']),
                description=type_vals['description']
            )
            created.append(event_type)
        
        _logger.info(f'Ensured {len(created)} standard SysEventTypes exist')
        return created
    
    @api.model
    def delete_event_type(self, event_type_id):
        """
        Delete an event type (if no events are linked)
        
        :param event_type_id: ID of the event type to delete
        :return: True if deleted, False otherwise
        """
        event_type = self.find_by_id(event_type_id)
        if not event_type:
            return False
        
        if event_type.event_count > 0:
            raise ValidationError(
                _('Cannot delete event type "%s" because it has %d associated events.') 
                % (event_type.name, event_type.event_count)
            )
        
        name = event_type.name
        event_type.unlink()
        _logger.info(f'Deleted SysEventType: {name}')
        return True
