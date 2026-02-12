# -*- coding: utf-8 -*-
"""
SAP Sync Test Runner
====================

Runs employee test sets sequentially against the SAP sync process.
Each test set is a folder containing JSON files that are copied to the
dev import directory before triggering a sync + task processing cycle.
"""

import os
import re
import json
import shutil
import glob as globmod
import logging

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SyncTestRunner(models.TransientModel):
    """Transient model for running SAP sync test sets."""

    _name = 'myschool.sync.test.runner'
    _description = 'SAP Sync Test Runner'

    name = fields.Char(string='Name', default='SAP Sync Test Runner')

    testsets_path = fields.Char(
        string='Test Sets Path',
        required=True,
        help='Absolute path to the directory containing numbered test set folders',
    )

    test_person_uuid = fields.Char(
        string='Test Person UUID',
        required=True,
        help='UUID (sap_person_uuid) of the test person to track',
    )

    result = fields.Html(
        string='Test Results',
        readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        """Set defaults from the myschool_core module path."""
        res = super().default_get(fields_list)
        module_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        default_testsets = os.path.join(
            module_path, 'myschool_core', 'storage', 'sapimport',
            'dev - testsets', 'employees'
        )
        if 'testsets_path' in fields_list and 'testsets_path' not in res:
            res['testsets_path'] = default_testsets
        if 'test_person_uuid' in fields_list and 'test_person_uuid' not in res:
            res['test_person_uuid'] = '2dc5c533-5a7a-4b2f-9020-7372345a53bc'
        return res

    # =========================================================================
    # Main action
    # =========================================================================

    def action_run_tests(self):
        """Run all test sets sequentially and display results."""
        self.ensure_one()

        if not os.path.isdir(self.testsets_path):
            raise UserError(f'Test sets path does not exist: {self.testsets_path}')

        dev_dir = self._get_dev_dir()
        testsets = self._get_sorted_testsets()

        if not testsets:
            raise UserError(f'No numbered test set folders found in: {self.testsets_path}')

        lines = []
        lines.append('<h3>SAP Sync Test Runner</h3>')
        lines.append(f'<p><b>Test sets path:</b> {self.testsets_path}<br/>')
        lines.append(f'<b>Test person UUID:</b> {self.test_person_uuid}<br/>')
        lines.append(f'<b>Found {len(testsets)} test set(s)</b></p>')

        # Cleanup
        cleanup_lines = self._cleanup_test_person()
        lines.append('<h4>Cleanup</h4><pre>' + '\n'.join(cleanup_lines) + '</pre>')

        # Run each test
        for num, name, path in testsets:
            test_lines = self._run_single_test(num, name, path, dev_dir)
            lines.append('\n'.join(test_lines))

        self.result = '\n'.join(lines)

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # =========================================================================
    # Helpers
    # =========================================================================

    def _get_dev_dir(self):
        """Get the dev import directory path."""
        service = self.env['myschool.informat.service']
        return service._get_storage_path(dev_mode=True)

    def _get_sorted_testsets(self):
        """Get test set directories sorted by leading number."""
        dirs = []
        for entry in os.listdir(self.testsets_path):
            full = os.path.join(self.testsets_path, entry)
            if os.path.isdir(full):
                match = re.match(r'^(\d+)', entry)
                if match:
                    dirs.append((int(match.group(1)), entry, full))
        dirs.sort(key=lambda x: x[0])
        return dirs

    def _clean_dev_dir(self, dev_dir):
        """Remove employee/assignment JSON files from dev dir."""
        for f in globmod.glob(os.path.join(dev_dir, 'dev-employees-*.json')):
            os.remove(f)
        for f in globmod.glob(os.path.join(dev_dir, 'dev-employeeassignments-*.json')):
            os.remove(f)

    def _copy_testset(self, testset_path, dev_dir):
        """Copy JSON files from a test set folder to the dev dir."""
        for f in globmod.glob(os.path.join(testset_path, '*.json')):
            shutil.copy2(f, dev_dir)

    def _cleanup_test_person(self):
        """Remove the test person and all related data to start clean."""
        lines = []
        uuid = self.test_person_uuid
        Person = self.env['myschool.person'].with_context(
            active_test=False, skip_manual_audit=True)
        person = Person.search([('sap_person_uuid', '=', uuid)], limit=1)

        if person:
            # Proprelations
            PropRelation = self.env['myschool.proprelation'].with_context(active_test=False)
            proprels = PropRelation.search([
                '|', '|',
                ('id_person', '=', person.id),
                ('id_person_parent', '=', person.id),
                ('id_person_child', '=', person.id),
            ])
            if proprels:
                lines.append(f'Deleted {len(proprels)} proprelation(s)')
                proprels.unlink()

            # Person details
            if person.person_details_set:
                lines.append(f'Deleted {len(person.person_details_set)} person detail(s)')
                person.person_details_set.unlink()

            # HR employee
            if person.odoo_employee_id:
                emp = person.odoo_employee_id.with_context(active_test=False)
                lines.append(f'Deleted HR employee: {emp.name}')
                person.write({'odoo_employee_id': False})
                emp.with_context(active_test=False).write({'active': True})
                emp.unlink()

            # Odoo user
            if person.odoo_user_id:
                user = person.odoo_user_id.with_context(active_test=False)
                lines.append(f'Deleted Odoo user: {user.login}')
                person.write({'odoo_user_id': False})
                user.with_context(active_test=False).write({'active': True})
                user.unlink()

            lines.append(f'Deleted person: {person.name}')
            person.unlink()

        # Clean related betasks
        BeTask = self.env['myschool.betask']
        tasks = BeTask.search([
            '|',
            ('data', 'like', uuid),
            ('name', 'like', 'DEMEYER'),
        ])
        if tasks:
            lines.append(f'Deleted {len(tasks)} related betask(s)')
            tasks.unlink()

        self.env.cr.commit()
        if not lines:
            lines.append('Nothing to clean up.')
        return lines

    def _get_person_state(self):
        """Get current state of the test person as a dict."""
        Person = self.env['myschool.person'].with_context(active_test=False)
        person = Person.search(
            [('sap_person_uuid', '=', self.test_person_uuid)], limit=1)

        if not person:
            return None

        state = {
            'name': person.name,
            'is_active': person.is_active,
            'person_type': person.person_type_id.name if person.person_type_id else None,
            'email_cloud': person.email_cloud,
            'odoo_user': person.odoo_user_id.login if person.odoo_user_id else None,
            'odoo_user_active': person.odoo_user_id.active if person.odoo_user_id else None,
            'odoo_employee': person.odoo_employee_id.name if person.odoo_employee_id else None,
            'odoo_employee_active': (
                person.odoo_employee_id.active if person.odoo_employee_id else None),
        }

        # Person details
        details = []
        for d in person.person_details_set:
            inst = getattr(d, 'institution_nr', None) or getattr(d, 'inst_nr', '?')
            details.append({
                'inst_nr': inst,
                'is_active': d.is_active if hasattr(d, 'is_active') else None,
            })
        state['details'] = details

        # Proprelations
        PropRelation = self.env['myschool.proprelation'].with_context(active_test=False)
        proprels = PropRelation.search([
            '|', '|',
            ('id_person', '=', person.id),
            ('id_person_parent', '=', person.id),
            ('id_person_child', '=', person.id),
        ])
        rels = []
        for pr in proprels:
            rels.append({
                'name': pr.name if hasattr(pr, 'name') else str(pr.id),
                'is_active': pr.is_active if hasattr(pr, 'is_active') else None,
            })
        state['proprelations'] = rels

        return state

    def _run_single_test(self, num, name, path, dev_dir):
        """Run a single test set and return HTML lines."""
        lines = []
        lines.append(f'<h4>Test {num}: {name}</h4>')

        # File summary
        files = sorted(os.listdir(path))
        file_summaries = []
        for f in files:
            if not f.endswith('.json'):
                continue
            fpath = os.path.join(path, f)
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                if isinstance(data, list) and len(data) == 0:
                    file_summaries.append(f'{f}: empty []')
                elif isinstance(data, list):
                    for item in data:
                        if 'isActive' in item:
                            file_summaries.append(
                                f'{f}: isActive={item.get("isActive")}, '
                                f'hoofdAmbt={item.get("hoofdAmbt")}, '
                                f'pensioendatum={item.get("pensioendatum", "N/A")}')
                        else:
                            file_summaries.append(f'{f}: assignment data')
            except Exception as e:
                file_summaries.append(f'{f}: error: {e}')

        lines.append('<pre>Files:\n  ' + '\n  '.join(file_summaries) + '</pre>')

        # Copy files and run sync
        self._clean_dev_dir(dev_dir)
        self._copy_testset(path, dev_dir)

        BeTask = self.env['myschool.betask']
        before_count = BeTask.search_count([])

        service = self.env['myschool.informat.service']
        try:
            sync_result = service.execute_sync(dev_mode=True)
        except Exception as e:
            lines.append(f'<pre style="color:red">SYNC ERROR: {e}</pre>')
            self.env.cr.rollback()
            return lines

        self.env.cr.commit()

        # New betasks
        after_count = BeTask.search_count([])
        new_count = after_count - before_count

        task_lines = []
        if new_count > 0:
            new_tasks = BeTask.search([], order='id desc', limit=new_count)
            for task in reversed(new_tasks):
                task_lines.append(f'[{task.status}] {task.name}')

        lines.append(f'<pre>Sync result: {sync_result}\n'
                      f'New betasks: {new_count}')
        if task_lines:
            lines.append('  ' + '\n  '.join(task_lines))
        lines.append('</pre>')

        # Process pending
        pending = BeTask.search([('status', '=', 'new')])
        if pending:
            processor = self.env['myschool.betask.processor']
            try:
                proc_result = processor.process_all_pending()
            except Exception as e:
                lines.append(f'<pre style="color:red">PROCESSING ERROR: {e}</pre>')
                self.env.cr.rollback()
                return lines

            self.env.cr.commit()

            result_lines = []
            for task in pending:
                task.invalidate_recordset()
            pending = BeTask.search([('id', 'in', pending.ids)])
            all_ok = True
            for task in pending:
                icon = '&#10004;' if task.status == 'completed_ok' else '&#10008;'
                if task.status != 'completed_ok':
                    all_ok = False
                result_lines.append(f'{icon} [{task.status}] {task.name}')
                if task.changes:
                    for line in task.changes.split('\n')[:5]:
                        result_lines.append(f'    {line}')

            color = 'green' if all_ok else 'red'
            lines.append(f'<pre style="color:{color}">Processing '
                          f'{len(pending)} task(s):\n'
                          + '\n'.join(result_lines) + '</pre>')
        else:
            lines.append('<pre>No pending tasks.</pre>')

        # Person state
        state = self._get_person_state()
        if state:
            active_style = 'color:green' if state['is_active'] else 'color:red'
            state_lines = [
                f'Name: {state["name"]}',
                f'Active: {state["is_active"]}',
                f'Type: {state["person_type"]}',
                f'Odoo user: {state["odoo_user"]} '
                f'(active={state["odoo_user_active"]})',
                f'Odoo employee: {state["odoo_employee"]} '
                f'(active={state["odoo_employee_active"]})',
            ]
            if state['details']:
                active_count = sum(1 for d in state['details'] if d['is_active'])
                state_lines.append(
                    f'Person details: {len(state["details"])} '
                    f'({active_count} active)')
            if state['proprelations']:
                active_rels = sum(1 for r in state['proprelations'] if r['is_active'])
                state_lines.append(
                    f'Proprelations: {len(state["proprelations"])} '
                    f'({active_rels} active)')
                for r in state['proprelations']:
                    icon = '&#10004;' if r['is_active'] else '&#10008;'
                    state_lines.append(f'  {icon} {r["name"]}')

            lines.append(f'<pre style="{active_style}">Person state:\n  '
                          + '\n  '.join(state_lines) + '</pre>')
        else:
            lines.append('<pre>Person not found after test.</pre>')

        return lines
