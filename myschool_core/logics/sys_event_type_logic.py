# -*- coding: utf-8 -*-
"""
System Event Type Logic
Converted from SysEventTypeDao methods in SysEventServiceImpl.java

This module contains business logic for managing system event types.
"""

from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class SysEventTypeLogic(models.AbstractModel):
    """
    Logic class for System Event Type operations
    Equivalent to SysEventTypeDao methods
    """
    _name = 'myschool.sys.event.type.logic'
    _description = 'System Event Type Logic'
    
    @api.model
    def find_by_name(self, name):
        """
        Find event type by name
        Equivalent to: findSysEventTypeByName(String name)
        
        :param name: Name of the event type
        :return: Event type record (empty recordset if not found)
        """
        return self.env['myschool.sys.event.type'].search([('name', '=', name)], limit=1)
    
    @api.model
    def find_by_code(self, code):
        """
        Find event type by code
        
        :param code: Code of the event type
        :return: Event type record (empty recordset if not found)
        """
        return self.env['myschool.sys.event.type'].search([('code', '=', code)], limit=1)
    
    @api.model
    def find_all(self):
        """
        Find all event types
        
        :return: Recordset of all event types
        """
        return self.env['myschool.sys.event.type'].search([])
    
    @api.model
    def get_or_create_type(self, name, code=None, description=None):
        """
        Get an event type by name, create if it doesn't exist
        Helper method to ensure event types exist
        
        :param name: Name of the event type
        :param code: Code for the event type (defaults to name if not provided)
        :param description: Description of the event type
        :return: Event type record
        """
        event_type = self.find_by_name(name)
        if not event_type:
            _logger.info(f'Creating new event type: {name}')
            event_type = self.env['myschool.sys.event.type'].create({
                'name': name,
                'code': code or name.replace(' ', '_').upper(),
                'description': description or f'Event type: {name}'
            })
        return event_type
    
    @api.model
    def create_event_type(self, name, code, description=None):
        """
        Create a new event type
        
        :param name: Name of the event type
        :param code: Unique code for the event type
        :param description: Description of the event type
        :return: Created event type record
        """
        return self.env['myschool.sys.event.type'].create({
            'name': name,
            'code': code,
            'description': description or f'Event type: {name}'
        })
    
    @api.model
    def update_event_type(self, event_type_id, vals):
        """
        Update an event type
        
        :param event_type_id: ID of the event type to update
        :param vals: Dictionary of values to update
        :return: Updated event type record
        """
        event_type = self.env['myschool.sys.event.type'].browse(event_type_id)
        if event_type:
            event_type.write(vals)
        return event_type
