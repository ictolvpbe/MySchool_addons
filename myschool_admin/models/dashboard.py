# -*- coding: utf-8 -*-
"""
Dashboard — Backend data provider for the OWL dashboard component.
"""

from odoo import models, fields, api
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class Dashboard(models.TransientModel):
    _name = 'myschool.dashboard'
    _description = 'MySchool Dashboard'

    name = fields.Char(default='Dashboard')

    @api.model
    def get_dashboard_data(self):
        """Return all dashboard data in a single RPC call."""
        return {
            'kpis': self._get_kpis(),
            'hero_stats': self._get_hero_stats(),
            'recent_tasks': self._get_recent_tasks(),
            'system_events': self._get_system_events(),
            'recent_activity': self._get_recent_activity(),
        }

    # ------------------------------------------------------------------
    # KPI cards
    # ------------------------------------------------------------------

    def _get_kpis(self):
        result = {
            'active_students': 0,
            'active_employees': 0,
            'organizations': 0,
            'classgroups': 0,
            'pending_tasks': 0,
            'error_tasks': 0,
        }

        if 'myschool.person' in self.env:
            Person = self.env['myschool.person']
            PersonType = self.env['myschool.person.type']

            student_type = PersonType.search([('name', '=', 'STUDENT')], limit=1)
            employee_type = PersonType.search([('name', '=', 'EMPLOYEE')], limit=1)

            if student_type:
                result['active_students'] = Person.search_count([
                    ('person_type_id', '=', student_type.id),
                    ('is_active', '=', True),
                ])
            if employee_type:
                result['active_employees'] = Person.search_count([
                    ('person_type_id', '=', employee_type.id),
                    ('is_active', '=', True),
                ])

        if 'myschool.org' in self.env:
            Org = self.env['myschool.org']
            result['organizations'] = Org.search_count([('is_active', '=', True)])

            if 'myschool.org.type' in self.env:
                OrgType = self.env['myschool.org.type']
                cg_type = OrgType.search([('name', '=ilike', 'CLASSGROUP')], limit=1)
                if cg_type:
                    result['classgroups'] = Org.search_count([
                        ('org_type_id', '=', cg_type.id),
                        ('is_active', '=', True),
                    ])

        if 'myschool.betask' in self.env:
            BeTask = self.env['myschool.betask']
            result['pending_tasks'] = BeTask.search_count([
                ('status', 'in', ['new', 'processing']),
            ])
            result['error_tasks'] = BeTask.search_count([
                ('status', '=', 'error'),
            ])

        if 'myschool.role' in self.env:
            result['active_roles'] = self.env['myschool.role'].search_count([
                ('is_active', '=', True),
            ])

        return result

    def _get_hero_stats(self):
        stats = {
            'organizations': 0,
            'persons': 0,
            'roles': 0,
        }
        if 'myschool.org' in self.env:
            stats['organizations'] = self.env['myschool.org'].search_count([
                ('is_active', '=', True),
            ])
        if 'myschool.person' in self.env:
            stats['persons'] = self.env['myschool.person'].search_count([
                ('is_active', '=', True),
            ])
        if 'myschool.role' in self.env:
            stats['roles'] = self.env['myschool.role'].search_count([
                ('is_active', '=', True),
            ])
        return stats

    # ------------------------------------------------------------------
    # Recent backend tasks
    # ------------------------------------------------------------------

    def _get_recent_tasks(self, limit=8):
        if 'myschool.betask' not in self.env:
            return []

        BeTask = self.env['myschool.betask']
        tasks = BeTask.search([], order='create_date desc', limit=limit)

        result = []
        for task in tasks:
            status_map = {
                'new': 'pending',
                'processing': 'processing',
                'completed_ok': 'done',
                'error': 'error',
            }
            result.append({
                'id': task.id,
                'name': task.name or task.display_name or '',
                'type': task.task_type_name or '',
                'status': status_map.get(task.status, task.status),
                'created': self._format_relative_time(task.create_date),
            })
        return result

    # ------------------------------------------------------------------
    # System events
    # ------------------------------------------------------------------

    def _get_system_events(self, limit=5):
        if 'myschool.sys.event' not in self.env:
            return []

        SysEvent = self.env['myschool.sys.event']
        events = SysEvent.search([], order='create_date desc', limit=limit)

        result = []
        for ev in events:
            severity = 'info'
            if ev.is_error:
                severity = 'error'
            elif ev.priority == '1':
                severity = 'warning'

            result.append({
                'id': ev.id,
                'name': ev.name or ev.display_name or '',
                'severity': severity,
                'time': self._format_relative_time(ev.create_date),
            })
        return result

    # ------------------------------------------------------------------
    # Recent activity (merged from tasks + events)
    # ------------------------------------------------------------------

    def _get_recent_activity(self, limit=6):
        activity = []

        if 'myschool.betask' in self.env:
            BeTask = self.env['myschool.betask']
            tasks = BeTask.search([], order='create_date desc', limit=limit)
            for task in tasks:
                status = 'info'
                if task.status == 'completed_ok':
                    status = 'success'
                elif task.status == 'error':
                    status = 'error'
                activity.append({
                    'text': task.name or task.display_name or '',
                    'status': status,
                    'time': self._format_relative_time(task.create_date),
                    'date': task.create_date,
                })

        if 'myschool.sys.event' in self.env:
            SysEvent = self.env['myschool.sys.event']
            events = SysEvent.search([], order='create_date desc', limit=limit)
            for ev in events:
                status = 'info'
                if ev.is_error:
                    status = 'error'
                else:
                    status = 'success'
                activity.append({
                    'text': ev.name or ev.display_name or '',
                    'status': status,
                    'time': self._format_relative_time(ev.create_date),
                    'date': ev.create_date,
                })

        # Sort by date descending, take top N
        activity.sort(key=lambda x: x['date'] or datetime.min, reverse=True)
        for item in activity:
            del item['date']
        return activity[:limit]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_relative_time(self, dt):
        if not dt:
            return ''
        now = fields.Datetime.now()
        diff = now - dt
        seconds = diff.total_seconds()

        if seconds < 60:
            return 'Just now'
        elif seconds < 3600:
            mins = int(seconds // 60)
            return f'{mins} min ago'
        elif seconds < 86400:
            hours = int(seconds // 3600)
            return f'{hours}h ago'
        elif seconds < 172800:
            return 'Yesterday'
        else:
            days = int(seconds // 86400)
            return f'{days} days ago'
