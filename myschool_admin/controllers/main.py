# -*- coding: utf-8 -*-
"""
MySchool Admin Controllers
==========================

Provides HTTP endpoints for admin features.
"""

from odoo import http
from odoo.http import request
import json


class MySchoolAdminController(http.Controller):
    
    # =========================================================================
    # Log Viewer Endpoints
    # =========================================================================
    
    @http.route('/myschool/logviewer/refresh', type='jsonrpc', auth='user', methods=['POST'])
    def refresh_log(self, log_file, num_lines=100, filter_level='all', search_text=''):
        """AJAX endpoint for real-time log refresh."""
        try:
            LogViewer = request.env['myschool.log.viewer']
            result = LogViewer.get_log_content_ajax(
                log_file=log_file,
                num_lines=int(num_lines),
                filter_level=filter_level,
                search_text=search_text or ''
            )
            return result
        except Exception as e:
            return {
                'error': str(e),
                'content': f'Error: {str(e)}',
                'timestamp': ''
            }
    
    @http.route('/myschool/logviewer/available_logs', type='jsonrpc', auth='user', methods=['POST'])
    def get_available_logs(self):
        """Get list of available log files."""
        try:
            LogViewer = request.env['myschool.log.viewer']
            logs = LogViewer._get_available_logs()
            return {'logs': logs}
        except Exception as e:
            return {'error': str(e), 'logs': []}
    
    # =========================================================================
    # LDAP Browser Endpoints
    # =========================================================================
    
    @http.route('/myschool/ldap/tree', type='jsonrpc', auth='user', methods=['POST'])
    def get_ldap_tree(self, show_inactive=False, search_text=''):
        """Get LDAP tree structure as JSON."""
        try:
            ObjectBrowser = request.env['myschool.object.browser']
            tree = ObjectBrowser.get_tree_data_ajax(
                show_inactive=show_inactive,
                search_text=search_text or ''
            )
            return tree
        except Exception as e:
            return {
                'id': 'root',
                'name': f'Error: {str(e)}',
                'type': 'root',
                'icon': 'fa-exclamation-triangle',
                'children': []
            }
    
    @http.route('/myschool/ldap/properties', type='jsonrpc', auth='user', methods=['POST'])
    def get_ldap_properties(self, node_type, node_id):
        """Get properties HTML for a selected node."""
        try:
            ObjectBrowser = request.env['myschool.object.browser']
            result = ObjectBrowser.get_node_properties_ajax(
                node_type=node_type,
                node_id=int(node_id) if node_id else 0
            )
            return result
        except Exception as e:
            return {'html': f'<div class="text-danger">Error: {str(e)}</div>'}
    
    @http.route('/myschool/ldap/sync', type='jsonrpc', auth='user', methods=['POST'])
    def sync_to_ldap(self, object_type, object_id):
        """Sync a single object to LDAP."""
        try:
            ObjectBrowser = request.env['myschool.object.browser']
            result = ObjectBrowser.sync_to_ldap_ajax(object_type, int(object_id))
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @http.route('/myschool/object/remove_role', type='jsonrpc', auth='user', methods=['POST'])
    def remove_role(self, proprelation_id):
        """Remove (deactivate) a role assignment."""
        try:
            PropRelation = request.env['myschool.proprelation']
            relation = PropRelation.browse(int(proprelation_id))
            if relation.exists():
                relation.write({'is_active': False})
                return {'success': True}
            else:
                return {'success': False, 'error': 'Relatie niet gevonden'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
