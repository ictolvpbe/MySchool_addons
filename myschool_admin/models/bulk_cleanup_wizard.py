# -*- coding: utf-8 -*-
"""Bulk cleanup wizard — delete every student / class under a school
through the manual betask pipeline, so the LDAP + Workspace cascades
fire for each removal.

Two-step UX:
  1. Preview — counts of students and classes in scope.
  2. Commit — queues one ``MANUAL/PERSON/DEL`` per student followed by
     one ``MANUAL/ORG/DEL`` per class. Order matters: AD + Google
     refuse to delete an OU that still contains users, so we drain the
     persons first.

Each MANUAL task creates its own cascade (LDAP/USER/DEL,
CLOUD/USER/DEL, LDAP/GROUP/DEL, LDAP/ORG/DEL, CLOUD/GROUP/DEL,
CLOUD/ORG/DEL) — see ``manual_task_processor.py``.
"""

import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BulkCleanupWizard(models.TransientModel):
    _name = 'myschool.bulk.cleanup.wizard'
    _description = 'Bulk delete students / classes (AD + Workspace cascade)'

    # ------------------------------------------------------------------
    # Scope + options
    # ------------------------------------------------------------------

    scope_org_id = fields.Many2one(
        'myschool.org',
        string='Scope (SCHOOL of SCHOOLBOARD)',
        required=True,
        domain="[('org_type_id.name', 'in', ['SCHOOL', 'SCHOOLBOARD'])]",
        help='Cleanup wordt toegepast op deze org en al haar '
             'descendants via ORG-TREE.')

    delete_students = fields.Boolean(
        string='Delete all STUDENT persons in scope', default=True,
        help='Iedere actieve persoon met person_type=STUDENT onder de '
             'scope wordt verwijderd via MANUAL/PERSON/DEL — cascade '
             'queue\'t LDAP/USER/DEL en CLOUD/USER/DEL.')

    delete_classes = fields.Boolean(
        string='Delete all CLASSGROUP orgs in scope', default=True,
        help='Iedere CLASSGROUP-org onder de scope wordt verwijderd '
             'via MANUAL/ORG/DEL — cascade queue\'t LDAP/GROUP/DEL, '
             'CLOUD/GROUP/DEL, LDAP/ORG/DEL en CLOUD/ORG/DEL. '
             'PERSONGROUP-orgs die als ORG-TREE-descendant onder een '
             'CLASSGROUP hangen worden automatisch eerst verwijderd '
             '(zodat het AD/Workspace OU leeg is wanneer het wordt '
             'opgeruimd).')

    # ------------------------------------------------------------------
    # State + preview
    # ------------------------------------------------------------------

    state = fields.Selection(
        [('draft', 'Draft'), ('preview', 'Preview'), ('committed', 'Committed')],
        default='draft', required=True)

    preview_text = fields.Text(string='Preview', readonly=True)
    student_count = fields.Integer(string='Studenten in scope', readonly=True)
    class_count = fields.Integer(string='Klassen in scope', readonly=True)

    # ------------------------------------------------------------------
    # Scope resolution
    # ------------------------------------------------------------------

    def _resolve_scope_orgs(self):
        """Return scope org + all its ORG-TREE descendants (BFS)."""
        self.ensure_one()
        Org = self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        org_tree_type = PropRelationType.search(
            [('name', '=', 'ORG-TREE')], limit=1)
        if not org_tree_type:
            return self.scope_org_id

        result_ids = {self.scope_org_id.id}
        frontier = {self.scope_org_id.id}
        while frontier:
            children = PropRelation.search([
                ('proprelation_type_id', '=', org_tree_type.id),
                ('id_org_parent', 'in', list(frontier)),
                ('is_active', '=', True),
            ])
            new_ids = set()
            for rel in children:
                if rel.id_org and rel.id_org.id not in result_ids:
                    new_ids.add(rel.id_org.id)
                if rel.id_org_child and rel.id_org_child.id not in result_ids:
                    new_ids.add(rel.id_org_child.id)
            new_ids -= result_ids
            result_ids.update(new_ids)
            frontier = new_ids
        return Org.browse(list(result_ids))

    def _resolve_students_in_scope(self, scope_orgs):
        """Active persons with type=STUDENT reachable via active
        PERSON-TREE in any scope org."""
        if not scope_orgs:
            return self.env['myschool.person']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        PersonType = self.env['myschool.person.type']
        pt_type = PropRelationType.search(
            [('name', '=', 'PERSON-TREE')], limit=1)
        student_type = PersonType.search([('name', '=', 'STUDENT')], limit=1)
        if not pt_type or not student_type:
            return self.env['myschool.person']
        rels = PropRelation.search([
            ('proprelation_type_id', '=', pt_type.id),
            ('id_org', 'in', scope_orgs.ids),
            ('is_active', '=', True),
            ('id_person', '!=', False),
            ('id_person.person_type_id', '=', student_type.id),
            ('id_person.is_active', '=', True),
        ])
        return rels.mapped('id_person')

    def _resolve_classes_in_scope(self, scope_orgs):
        """Active CLASSGROUP-type orgs in scope."""
        return scope_orgs.filtered(
            lambda o: o.is_active and o.org_type_id
            and o.org_type_id.name == 'CLASSGROUP')

    def _resolve_class_persongroups(self, class_orgs):
        """PERSONGROUP-type orgs that are ORG-TREE descendants of any
        org in ``class_orgs``. These typically hang off a classgroup
        (one persongroup per class for AD/Google groups) and need to
        disappear together with the class — otherwise the AD/Google
        groups stay dangling after the class OU is removed.

        BFS walk so deeper nestings (e.g. ``class → groups → pg``)
        are also caught.
        """
        if not class_orgs:
            return self.env['myschool.org']
        Org = self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        org_tree_type = PropRelationType.search(
            [('name', '=', 'ORG-TREE')], limit=1)
        if not org_tree_type:
            return Org.browse()

        visited = set(class_orgs.ids)
        frontier = set(class_orgs.ids)
        descendant_ids = set()
        while frontier:
            children = PropRelation.search([
                ('proprelation_type_id', '=', org_tree_type.id),
                ('id_org_parent', 'in', list(frontier)),
                ('is_active', '=', True),
            ])
            new_ids = set()
            for rel in children:
                if rel.id_org and rel.id_org.id not in visited:
                    new_ids.add(rel.id_org.id)
                if rel.id_org_child and rel.id_org_child.id not in visited:
                    new_ids.add(rel.id_org_child.id)
            new_ids -= visited
            visited.update(new_ids)
            descendant_ids.update(new_ids)
            frontier = new_ids

        if not descendant_ids:
            return Org.browse()
        return Org.search([
            ('id', 'in', list(descendant_ids)),
            ('is_active', '=', True),
            ('org_type_id.name', '=', 'PERSONGROUP'),
        ])

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_preview(self):
        self.ensure_one()
        if not (self.delete_students or self.delete_classes):
            raise UserError(_(
                'Vink minstens één van de opties aan (studenten of klassen).'))

        scope_orgs = self._resolve_scope_orgs()
        students = self._resolve_students_in_scope(scope_orgs) \
            if self.delete_students else self.env['myschool.person']
        classes = self._resolve_classes_in_scope(scope_orgs) \
            if self.delete_classes else self.env['myschool.org']
        class_persongroups = self._resolve_class_persongroups(classes) \
            if self.delete_classes else self.env['myschool.org']

        lines = [
            f'Scope: {self.scope_org_id.name} (id={self.scope_org_id.id})',
            f'Orgs in scope (incl. descendants): {len(scope_orgs)}',
            '',
        ]
        if self.delete_students:
            lines.append(f'STUDENT persons to delete: {len(students)}')
            if students:
                sample = ', '.join(
                    f'{p.first_name or ""} {p.name}'.strip()
                    for p in students[:5])
                more = f' …+{len(students) - 5} more' if len(students) > 5 else ''
                lines.append(f'  e.g. {sample}{more}')
        else:
            lines.append('STUDENT persons: SKIP')
        if self.delete_classes:
            lines.append(f'CLASSGROUP orgs to delete: {len(classes)}')
            if classes:
                sample = ', '.join(
                    c.name_short or c.name for c in classes[:8])
                more = f' …+{len(classes) - 8} more' if len(classes) > 8 else ''
                lines.append(f'  e.g. {sample}{more}')
            # Persongroups hanging off the classes — auto-included so
            # the AD/Google groups disappear together with the class.
            lines.append(
                f'PERSONGROUP orgs linked to classes to delete: '
                f'{len(class_persongroups)}')
            if class_persongroups:
                sample = ', '.join(
                    pg.name_short or pg.name for pg in class_persongroups[:8])
                more = (f' …+{len(class_persongroups) - 8} more'
                        if len(class_persongroups) > 8 else '')
                lines.append(f'  e.g. {sample}{more}')
        else:
            lines.append('CLASSGROUP orgs: SKIP')
            lines.append('Linked PERSONGROUP orgs: SKIP')
        lines.append('')
        lines.append(
            'Each delete fires through MANUAL/PERSON/DEL or MANUAL/ORG/DEL '
            'which cascades to LDAP + Workspace. Students are processed '
            'first so the OU is empty by the time classes are removed.')

        # ``class_count`` shown in the form includes the linked
        # persongroups — admins reading the preview see the total
        # number of org records that will be unlinked, not just the
        # CLASSGROUP-type ones.
        self.write({
            'state': 'preview',
            'preview_text': '\n'.join(lines),
            'student_count': len(students),
            'class_count': len(classes) + len(class_persongroups),
        })
        return self._reopen()

    def action_commit(self):
        self.ensure_one()
        if self.state != 'preview':
            raise UserError(_('Voer eerst Preview uit voor commit.'))

        scope_orgs = self._resolve_scope_orgs()
        service = self.env['myschool.manual.task.service']
        student_ok = student_err = class_ok = class_err = 0
        errors = []

        # Students first — OUs/persongroups become empty by the time
        # we tackle the classes.
        if self.delete_students:
            students = self._resolve_students_in_scope(scope_orgs)
            for person in students:
                try:
                    task = service.create_manual_task('PERSON', 'DEL', {
                        'person_id': person.id,
                    })
                    if task.status == 'completed_ok':
                        student_ok += 1
                    else:
                        student_err += 1
                        errors.append(
                            f'PERSON {person.name}: {task.error_description or task.status}')
                except Exception as e:
                    student_err += 1
                    errors.append(f'PERSON {person.name}: {e}')

        if self.delete_classes:
            # Re-resolve scope (some descendants may have been cleared
            # by sub-cascades during the person sweep, but the class
            # records themselves are still around).
            scope_orgs = self._resolve_scope_orgs()
            classes = self._resolve_classes_in_scope(scope_orgs)
            # Delete class-linked persongroups BEFORE the classes:
            # AD/Google reject deletion of an OU that still contains
            # groups; processing persongroups first removes the AD
            # groups (LDAP/GROUP/DEL + CLOUD/GROUP/DEL) and then the
            # class OU can be cleanly removed.
            class_persongroups = self._resolve_class_persongroups(classes)
            for pg in class_persongroups:
                if not pg.exists():
                    continue
                try:
                    task = service.create_manual_task('ORG', 'DEL', {
                        'org_id': pg.id,
                        'org_name': pg.name,
                    })
                    if task.status == 'completed_ok':
                        class_ok += 1
                    else:
                        class_err += 1
                        errors.append(
                            f'PG {pg.name}: {task.error_description or task.status}')
                except Exception as e:
                    class_err += 1
                    errors.append(f'PG {pg.name}: {e}')
            for org in classes:
                if not org.exists():
                    continue
                try:
                    task = service.create_manual_task('ORG', 'DEL', {
                        'org_id': org.id,
                        'org_name': org.name,
                    })
                    if task.status == 'completed_ok':
                        class_ok += 1
                    else:
                        class_err += 1
                        errors.append(
                            f'ORG {org.name}: {task.error_description or task.status}')
                except Exception as e:
                    class_err += 1
                    errors.append(f'ORG {org.name}: {e}')

        self.write({'state': 'committed'})

        parts = []
        if self.delete_students:
            parts.append(_('Studenten: %(ok)s OK, %(err)s fout')
                         % {'ok': student_ok, 'err': student_err})
        if self.delete_classes:
            parts.append(_('Klassen: %(ok)s OK, %(err)s fout')
                         % {'ok': class_ok, 'err': class_err})
        msg = ' — '.join(parts)
        if errors:
            detail = '\n'.join(errors[:10])
            if len(errors) > 10:
                detail += f'\n…+{len(errors) - 10} more'
            msg += f'\n\nEerste fouten:\n{detail}'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Bulk cleanup uitgevoerd'),
                'message': msg,
                'type': 'success' if not (student_err or class_err) else 'warning',
                'sticky': True,
            },
        }

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
