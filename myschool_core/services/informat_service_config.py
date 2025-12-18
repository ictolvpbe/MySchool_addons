# -*- coding: utf-8 -*-
"""
Informat Service Configuration
==============================

Configuration model for Informat synchronization service.
Equivalent to Java: servicepropertiesSyncSap.java

This model stores configuration parameters that can be
managed through the Odoo interface.
"""

import os

from odoo import api, fields, models, _


class InformatServiceConfig(models.Model):
    """
    Configuration settings for Informat Service.
    Accessible through Settings > Technical > Informat Service Configuration
    """
    _name = 'myschool.informat.service.config'
    _description = 'Informat Service Configuration'
    _rec_name = 'name'
    
    name = fields.Char(
        string='Configuration Name',
        required=True,
        default='Default Configuration'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )
    
    # API Configuration
    identity_server_url = fields.Char(
        string='Identity Server URL',
        default='https://www.identityserver.be/connect/token',
        help='OAuth2 token endpoint URL'
    )
    
    students_api_url = fields.Char(
        string='Students API URL',
        default='https://leerlingenapi.informatsoftware.be/1/students',
        help='Informat Students API base URL'
    )
    
    employees_api_url = fields.Char(
        string='Employees API URL',
        default='https://personeelsapi.informatsoftware.be/employees',
        help='Informat Employees API base URL'
    )
    
    employee_assignments_api_url = fields.Char(
        string='Employee Assignments API URL',
        default='https://personeelsapi.informatsoftware.be/employees/assignments',
        help='Informat Employee Assignments API URL'
    )
    
    api_version = fields.Char(
        string='API Version',
        default='2',
        help='API version header value'
    )
    
    # Storage Configuration
    storage_path_dev = fields.Char(
        string='Development Storage Path',
        default='storage/sapimport/dev',
        help='Path for development mode JSON files'
    )
    
    storage_path_prod = fields.Char(
        string='Production Storage Path',
        default='storage/sapimport/prod',
        help='Path for production mode JSON files'
    )
    
    # Sync Configuration
    dev_mode = fields.Boolean(
        string='Development Mode',
        default=False,
        help='If enabled, use local files instead of API calls'
    )
    
    sync_days_back = fields.Integer(
        string='Sync Days Back',
        default=15,
        help='Number of days to look back for changes during sync'
    )
    
    retry_count = fields.Integer(
        string='Retry Count',
        default=2,
        help='Number of retries for failed operations'
    )
    
    timeout_seconds = fields.Integer(
        string='API Timeout (seconds)',
        default=60,
        help='Timeout for API requests in seconds'
    )
    
    # Organization Reference
    default_org_short_name = fields.Char(
        string='Default Organization Short Name',
        default='olvp',
        help='Default organization short name for config lookups'
    )
    
    # Last Sync Information
    last_sync_timestamp = fields.Datetime(
        string='Last Sync Timestamp',
        readonly=True,
        help='Timestamp of the last successful sync'
    )
    
    last_sync_status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
        ('running', 'Running'),
        ('not_run', 'Not Run Yet')
    ], string='Last Sync Status', default='not_run', readonly=True)
    
    last_sync_message = fields.Text(
        string='Last Sync Message',
        readonly=True
    )
    
    # Statistics
    last_students_processed = fields.Integer(
        string='Last Students Processed',
        readonly=True
    )
    
    last_employees_processed = fields.Integer(
        string='Last Employees Processed',
        readonly=True
    )
    
    last_tasks_created = fields.Integer(
        string='Last Tasks Created',
        readonly=True
    )
    
    @api.model
    def get_config(self):
        """
        Get the active configuration record.
        Creates default if none exists.
        """
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            config = self.create({'name': 'Default Configuration'})
        return config
    
    def update_sync_status(self, status: str, message: str = '', 
                          students: int = 0, employees: int = 0, tasks: int = 0):
        """
        Update the sync status after a sync operation.
        
        @param status: 'success', 'error', or 'running'
        @param message: Status message
        @param students: Number of students processed
        @param employees: Number of employees processed
        @param tasks: Number of tasks created
        """
        self.write({
            'last_sync_timestamp': fields.Datetime.now(),
            'last_sync_status': status,
            'last_sync_message': message,
            'last_students_processed': students,
            'last_employees_processed': employees,
            'last_tasks_created': tasks
        })
    
    def action_run_sync(self):
        """
        Action to manually trigger sync from UI.
        """
        self.update_sync_status('running', 'Sync started manually')
        
        try:
            service = self.env['myschool.informat.service']
            result = service.execute_sync(dev_mode=self.dev_mode)
            
            if result:
                self.update_sync_status('success', 'Sync completed successfully')
            else:
                self.update_sync_status('error', 'Sync completed with errors')
                
        except Exception as e:
            self.update_sync_status('error', f'Sync failed: {str(e)}')
            raise
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync Complete'),
                'message': _('Informat sync has completed. Check the status for details.'),
                'type': 'success' if self.last_sync_status == 'success' else 'warning',
                'sticky': False,
            }
        }
    
    def action_run_diff_sync(self):
        """
        Action to manually trigger differential sync from UI.
        """
        self.update_sync_status('running', 'Differential sync started manually')
        
        try:
            service = self.env['myschool.informat.service']
            result = service.execute_diff_sync(dev_mode=self.dev_mode)
            
            if result:
                self.update_sync_status('success', 'Differential sync completed successfully')
            else:
                self.update_sync_status('error', 'Differential sync completed with errors')
                
        except Exception as e:
            self.update_sync_status('error', f'Differential sync failed: {str(e)}')
            raise
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Differential Sync Complete'),
                'message': _('Differential sync has completed. Check the status for details.'),
                'type': 'success' if self.last_sync_status == 'success' else 'warning',
                'sticky': False,
            }
        }

    def action_create_storage_directories(self):
        """
        Action to create storage directories from UI.
        Creates both dev and prod directories based on current configuration.
        """
        service = self.env['myschool.informat.service']
        result = service.action_create_storage_directories()
        
        notification_type = 'success' if result.get('success') else 'danger'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Storage Directories'),
                'message': result.get('message', 'Operation completed'),
                'type': notification_type,
                'sticky': True,
            }
        }

    def action_show_storage_paths(self):
        """
        Action to display current storage paths.
        Useful for debugging and verification.
        """
        service = self.env['myschool.informat.service']
        
        dev_path = service._get_storage_path(dev_mode=True)
        prod_path = service._get_storage_path(dev_mode=False)
        students_dev_path = service._get_storage_path_for_students(dev_mode=True)
        
        dev_exists = os.path.exists(dev_path)
        prod_exists = os.path.exists(prod_path)
        students_dev_exists = os.path.exists(students_dev_path)
        
        message = (
            f"Development Path: {dev_path} ({'✓ exists' if dev_exists else '✗ missing'})\n"
            f"Students Dev Path: {students_dev_path} ({'✓ exists' if students_dev_exists else '✗ missing'})\n"
            f"Production Path: {prod_path} ({'✓ exists' if prod_exists else '✗ missing'})"
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Storage Paths'),
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }


class InformatServiceConfigSettings(models.TransientModel):
    """
    Settings wizard for Informat Service configuration.
    Accessible through Settings menu.
    """
    _name = 'myschool.informat.service.config.settings'
    _inherit = 'res.config.settings'
    _description = 'Informat Service Settings'
    
    informat_config_id = fields.Many2one(
        'myschool.informat.service.config',
        string='Configuration',
        default=lambda self: self.env['myschool.informat.service.config'].get_config()
    )
    
    dev_mode = fields.Boolean(
        related='informat_config_id.dev_mode',
        readonly=False
    )
    
    sync_days_back = fields.Integer(
        related='informat_config_id.sync_days_back',
        readonly=False
    )
    
    timeout_seconds = fields.Integer(
        related='informat_config_id.timeout_seconds',
        readonly=False
    )
    
    default_org_short_name = fields.Char(
        related='informat_config_id.default_org_short_name',
        readonly=False
    )
