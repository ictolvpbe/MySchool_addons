# -*- coding: utf-8 -*-
"""
Log Viewer Controller
=====================

Provides HTTP endpoints for real-time log viewing.
"""

from odoo import http
from odoo.http import request
import json


class LogViewerController(http.Controller):
    
    @http.route('/myschool/logviewer/refresh', type='jsonrpc', auth='user', methods=['POST'])
    def refresh_log(self, log_file, num_lines=100, filter_level='all', search_text=''):
        """
        AJAX endpoint for real-time log refresh.
        Called by JavaScript at regular intervals.
        """
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
