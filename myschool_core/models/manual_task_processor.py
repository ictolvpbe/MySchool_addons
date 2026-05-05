# -*- coding: utf-8 -*-
"""
Manual Task Processor
=====================
Extends betask.processor with handlers for MANUAL target tasks.

These handlers perform the same ORM operations that the wizards and
object_browser used to do directly, but via the betask system for
audit trail and queued processing support.
"""

from odoo import models, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)


def _build_proprelation_name(proprelation_type_name, **kwargs):
    """Build a standardized proprelation name from records.

    Lightweight copy of the function from wizards.py / betask_processor.py
    so the processor doesn't depend on myschool_admin.
    """
    field_map = {
        'id_org': ('Or', 'name_tree', 'name'),
        'id_org_parent': ('OrP', 'name_tree', 'name'),
        'id_org_child': ('OrC', 'name_tree', 'name'),
        'id_period': ('Pd', 'name', 'name'),
        'id_role': ('Ro', 'name', 'name'),
        'id_role_parent': ('RoP', 'name', 'name'),
        'id_role_child': ('RoC', 'name', 'name'),
        'id_person': ('Pn', 'name', 'name'),
        'id_person_parent': ('PnP', 'name', 'name'),
        'id_person_child': ('PnC', 'name', 'name'),
    }
    field_order = [
        'id_role', 'id_role_parent', 'id_role_child',
        'id_org_parent', 'id_org', 'id_org_child',
        'id_person', 'id_person_parent', 'id_person_child',
        'id_period',
    ]
    parts = []
    for field_name in field_order:
        if field_name in kwargs and kwargs[field_name]:
            record = kwargs[field_name]
            abbr, primary_field, fallback_field = field_map[field_name]
            value = None
            if hasattr(record, primary_field) and getattr(record, primary_field):
                value = getattr(record, primary_field)
            elif hasattr(record, fallback_field) and getattr(record, fallback_field):
                value = getattr(record, fallback_field)
            elif hasattr(record, 'name'):
                value = record.name
            if value:
                parts.append(f"{abbr}={value}")
    type_prefix = proprelation_type_name.upper() if proprelation_type_name else 'UNKNOWN'
    if parts:
        return f"{type_prefix}:{','.join(parts)}"
    return type_prefix


class ManualTaskProcessor(models.AbstractModel):
    """Extends betask processor with MANUAL task handlers."""

    _inherit = 'myschool.betask.processor'

    # ------------------------------------------------------------------
    # Override generic router to add MANUAL entries
    # ------------------------------------------------------------------

    @api.model
    def _process_task_generic(self, task):
        target = task.betasktype_id.target
        obj = task.betasktype_id.object
        action = task.betasktype_id.action

        manual_handlers = {
            ('MANUAL', 'PERSON', 'ADD'):         self.process_manual_person_add,
            ('MANUAL', 'PERSON', 'UPD'):         self.process_manual_person_upd,
            ('MANUAL', 'PERSON', 'DEACT'):       self.process_manual_person_deact,
            ('MANUAL', 'PERSON', 'DEL'):         self.process_manual_person_del,
            ('MANUAL', 'ORG', 'ADD'):            self.process_manual_org_add,
            ('MANUAL', 'ORG', 'UPD'):            self.process_manual_org_upd,
            ('MANUAL', 'ORG', 'DEL'):            self.process_manual_org_del,
            ('MANUAL', 'PROPRELATION', 'ADD'):   self.process_manual_proprelation_add,
            ('MANUAL', 'PROPRELATION', 'UPD'):   self.process_manual_proprelation_upd,
            ('MANUAL', 'PROPRELATION', 'DEACT'): self.process_manual_proprelation_deact,
        }

        handler = manual_handlers.get((target, obj, action))
        if handler:
            return handler(task)

        # Fall through to parent implementation for non-MANUAL tasks
        return super()._process_task_generic(task)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @api.model
    def _get_manual_data(self, task):
        """Parse and return the JSON data dict from the task."""
        data = self._parse_task_data(task.data)
        if not data or not isinstance(data, dict):
            return None
        return data

    def _get_or_create_proprelation_type(self, name, usage=''):
        """Get or create a proprelation type by name."""
        PrType = self.env['myschool.proprelation.type']
        rel_type = PrType.search([('name', '=', name)], limit=1)
        if not rel_type:
            vals = {'name': name, 'is_active': True}
            if usage:
                vals['usage'] = usage
            rel_type = PrType.create(vals)
        return rel_type

    # ==================================================================
    # PERSON handlers
    # ==================================================================

    @api.model
    def process_manual_person_add(self, task):
        """Create a person, PERSON-TREE relation, and optionally Odoo user + roles."""
        data = self._get_manual_data(task)
        if not data:
            return {'success': False, 'error': 'No data in task'}

        changes = []
        Person = self.env['myschool.person']
        PropRelation = self.env['myschool.proprelation']

        # Build person vals
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        composite_name = data.get('name') or (
            f"{last_name}, {first_name}".strip(', ') if (last_name or first_name) else '')
        person_vals = {
            'first_name': first_name,
            'last_name': last_name,
            'name': composite_name,
            'is_active': True,
        }
        if data.get('email_cloud'):
            person_vals['email_cloud'] = data['email_cloud']
        if data.get('email_private'):
            person_vals['email_private'] = data['email_private']
        if data.get('sap_ref'):
            person_vals['sap_ref'] = data['sap_ref']
        if data.get('abbreviation'):
            person_vals['abbreviation'] = data['abbreviation']

        # Person type
        if data.get('person_type_name'):
            PersonType = self.env['myschool.person.type']
            pt = PersonType.search([('name', '=ilike', data['person_type_name'])], limit=1)
            if pt:
                person_vals['person_type_id'] = pt.id

        # Odoo user
        user = None
        if data.get('create_user'):
            login = data.get('user_login') or data.get('email_cloud')
            if login:
                existing_user = self.env['res.users'].search([('login', '=', login)], limit=1)
                if existing_user:
                    return {'success': False, 'error': f"User with login '{login}' already exists"}
                user = self.env['res.users'].create({
                    'name': f"{first_name} {last_name}".strip(),
                    'login': login,
                    'email': data.get('email_cloud') or login,
                })
                changes.append(f"Created Odoo user: {user.login}")

                # HR employee for employees
                if data.get('create_employee') and 'hr.employee' in self.env:
                    self.env['hr.employee'].create({
                        'name': user.name,
                        'user_id': user.id,
                        'work_email': data.get('email_cloud') or login,
                    })
                    changes.append("Created HR employee")
        elif data.get('link_user_id'):
            user = self.env['res.users'].browse(data['link_user_id']).exists()

        if user and 'user_id' in Person._fields:
            person_vals['user_id'] = user.id

        person = Person.create(person_vals)
        changes.append(f"Created person: {person.first_name} {person.name} (ID: {person.id})")

        # PERSON-TREE relation
        org_id = data.get('org_id')
        org = None
        school_org = None
        if org_id:
            org = self.env['myschool.org'].browse(org_id).exists()
            if org:
                pt_type = self._get_or_create_proprelation_type('PERSON-TREE')
                rel_name = _build_proprelation_name('PERSON-TREE', id_person=person, id_org=org)
                PropRelation.create({
                    'name': rel_name,
                    'proprelation_type_id': pt_type.id,
                    'id_person': person.id,
                    'id_org': org.id,
                    'is_active': True,
                })
                changes.append(f"Created PERSON-TREE relation to {org.name_tree or org.name}")

                # Resolve the parent SCHOOL — needed for backend role PPSBR
                # and LDAP provisioning. Use the existing helper from the
                # backend processor to walk up the ORG-TREE.
                processor = self.env['myschool.betask.processor']
                if hasattr(processor, '_resolve_parent_school_from_org'):
                    school_org = processor._resolve_parent_school_from_org(org)

                # Auto-complete email_cloud + LDAP DN fields. The helper
                # uses the target org's ou_fqdn_internal/external; the
                # school is the most reliable container for that.
                # Use the directly-linked org (not the school) so the
                # OU-FQDN of the leaf (department/class) is reflected in
                # person_fqdn_internal/external. The CN-build and UPN/
                # email_cloud generation walk up to the school internally
                # for the per-school CI and domain values.
                if org and hasattr(processor, '_populate_person_account_fields'):
                    try:
                        processor._populate_person_account_fields(person, org)
                        if person.person_fqdn_internal:
                            changes.append(
                                f"Set person_fqdn_internal: {person.person_fqdn_internal}")
                        if person.person_fqdn_external:
                            changes.append(
                                f"Set person_fqdn_external: {person.person_fqdn_external}")
                    except Exception as e:
                        changes.append(f"WARN: FQDN auto-complete failed: {e}")

        # ---------------------------------------------------------------
        # Backend role PPSBR (STUDENT or EMPLOYEE) at school level
        # ---------------------------------------------------------------
        person_type_name = (data.get('person_type_name') or '').upper().strip()
        ppsbr_role_name = None
        if person_type_name == 'EMPLOYEE':
            ppsbr_role_name = 'EMPLOYEE'
        elif person_type_name == 'STUDENT':
            ppsbr_role_name = 'STUDENT'

        if ppsbr_role_name and school_org:
            Role = self.env['myschool.role']
            PropRelationType = self.env['myschool.proprelation.type']
            backend_role = Role.search([('name', '=', ppsbr_role_name)], limit=1)
            ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
            if backend_role and ppsbr_type:
                # Avoid duplicate
                exists = PropRelation.search([
                    ('proprelation_type_id', '=', ppsbr_type.id),
                    ('id_person', '=', person.id),
                    ('id_org', '=', school_org.id),
                    ('id_role', '=', backend_role.id),
                    ('is_active', '=', True),
                ], limit=1)
                if not exists:
                    ppsbr_name = _build_proprelation_name(
                        'PPSBR', id_person=person, id_role=backend_role, id_org=school_org)
                    new_ppsbr = PropRelation.create({
                        'name': ppsbr_name,
                        'proprelation_type_id': ppsbr_type.id,
                        'id_person': person.id,
                        'id_role': backend_role.id,
                        'id_org': school_org.id,
                        'is_active': True,
                        'is_organisational': True,
                        'automatic_sync': True,
                    })
                    changes.append(
                        f"Created {ppsbr_role_name} PPSBR at {school_org.name}")
                    # Same cascade the sync flow runs after a PPSBR is
                    # added: queue LDAP/GROUP/ADD + LDAP/GROUPMEMBER/ADD
                    # for every BRSO target_org with has_comgroup /
                    # has_secgroup. Without this, manually-added persons
                    # land in the OU but never enter their role's groups.
                    grp_changes = self._cascade_ppsbr_group_membership(
                        new_ppsbr, action='ADD')
                    if grp_changes:
                        changes.extend(grp_changes)
                    # And re-sync the DB-side persongroup memberships so
                    # PG-P relations populate for the new PPSBR.
                    try:
                        self._sync_persongroup_memberships(person)
                    except Exception as e:
                        _logger.warning(
                            '[MANUAL-ADD] persongroup sync failed for %s: %s',
                            person.name, e)
            elif not backend_role:
                changes.append(
                    f"WARN: backend role '{ppsbr_role_name}' not found — PPSBR skipped")

        # ---------------------------------------------------------------
        # LDAP/USER/ADD betask — only when the resolved school is set up
        # for LDAP/AD provisioning (has_ou flag on the school or its
        # OU-for-classes/groups parent).
        # ---------------------------------------------------------------
        if org and school_org:
            wants_ldap = bool(
                getattr(school_org, 'has_ou', False)
                or getattr(org, 'has_ou', False)
            )
            if wants_ldap:
                label = f"LDAP/USER/ADD for {person.first_name} {person.name}"
                changes.append(f"Queued {label}")
                self._create_and_run_task('LDAP', 'USER', 'ADD', {
                    'person_id': person.id,
                    'org_id': org.id,
                }, changes, label=label)

        return {'success': True, 'changes': '\n'.join(changes)}

    @api.model
    def process_manual_person_upd(self, task):
        """Update person: move to different org (PERSON-TREE) or update fields."""
        data = self._get_manual_data(task)
        if not data:
            return {'success': False, 'error': 'No data in task'}

        person_id = data.get('person_id')
        if not person_id:
            return {'success': False, 'error': 'person_id required'}

        # Generic field update mode
        update_vals = data.get('vals')
        if update_vals:
            Person = self.env['myschool.person']
            person = Person.browse(person_id).exists()
            if not person:
                return {'success': False, 'error': f'Person {person_id} not found'}
            person.write(update_vals)
            changes = [f"Updated person {person.name}: {update_vals}"]
            # Cascade: any change to LDAP-relevant attributes (display name,
            # email, abbreviation, etc.) needs to be reflected in AD.
            ldap_attrs = {
                'first_name', 'last_name', 'name', 'short_name', 'abbreviation',
                'email_cloud', 'email_private',
            }
            if any(k in update_vals for k in ldap_attrs):
                self._emit_ldap_user_task(person, 'UPD', changes)
            return {'success': True, 'changes': '\n'.join(changes)}

        # Move mode (legacy)
        new_org_id = data.get('new_org_id')
        if not new_org_id:
            return {'success': False, 'error': 'new_org_id or vals required'}

        Person = self.env['myschool.person']
        Org = self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']

        person = Person.browse(person_id).exists()
        new_org = Org.browse(new_org_id).exists()
        if not person:
            return {'success': False, 'error': f'Person {person_id} not found'}
        if not new_org:
            return {'success': False, 'error': f'Org {new_org_id} not found'}

        pt_type = self._get_or_create_proprelation_type('PERSON-TREE')

        # Capture the old PERSON-TREE org(s) BEFORE deactivation so we can
        # detect whether the school changed and clean up old PPSBRs.
        old_rels = PropRelation.search([
            ('id_person', '=', person_id),
            ('id_org', '!=', False),
            ('is_active', '=', True),
            ('proprelation_type_id', '=', pt_type.id),
        ])
        old_orgs = old_rels.mapped('id_org')

        # Deactivate old PERSON-TREE relations
        if old_rels:
            old_rels.write({'is_active': False})

        # Create new
        rel_name = _build_proprelation_name('PERSON-TREE', id_person=person, id_org=new_org)
        PropRelation.create({
            'name': rel_name,
            'proprelation_type_id': pt_type.id,
            'id_person': person_id,
            'id_org': new_org_id,
            'is_active': True,
        })

        changes = [
            f"Moved person {person.first_name} {person.name} to "
            f"{new_org.name_tree or new_org.name}"
        ]

        # ---------------------------------------------------------------
        # Cascade: re-sync school-level PPSBR + LDAP user when the school
        # changes (e.g. moving from one school's department to another).
        # ---------------------------------------------------------------
        processor = self.env['myschool.betask.processor']
        new_school = (processor._resolve_parent_school_from_org(new_org)
                      if hasattr(processor, '_resolve_parent_school_from_org')
                      else None)
        old_schools = self.env['myschool.org']
        if hasattr(processor, '_resolve_parent_school_from_org'):
            for o in old_orgs:
                s = processor._resolve_parent_school_from_org(o)
                if s:
                    old_schools |= s

        # Schools that are no longer the active school: deactivate the
        # backend role PPSBR (EMPLOYEE/STUDENT) at those schools.
        ppsbr_role_name = self._get_person_backend_role_name(person)
        if ppsbr_role_name:
            stale_schools = old_schools - (new_school or self.env['myschool.org'])
            ppsbr_changes = self._cleanup_school_ppsbr(
                person, stale_schools, ppsbr_role_name)
            changes.extend(ppsbr_changes)

            # Make sure the new school has an active PPSBR.
            if new_school:
                created = self._ensure_school_ppsbr(person, new_school, ppsbr_role_name)
                if created:
                    changes.append(
                        f"Created {ppsbr_role_name} PPSBR at {new_school.name}")

        # LDAP cascade: emit USER/UPD so the AD account is moved/updated.
        if new_school and self._school_wants_ldap(new_school, new_org):
            label = f"LDAP/USER/UPD for {person.first_name} {person.name}"
            changes.append(f"Queued {label}")
            self._create_and_run_task('LDAP', 'USER', 'UPD', {
                'person_id': person.id,
                'org_id': new_org.id,
            }, changes, label=label)

        return {'success': True, 'changes': '\n'.join(changes)}

    # ------------------------------------------------------------------
    # Cascade helpers
    # ------------------------------------------------------------------

    @api.model
    def _get_person_backend_role_name(self, person):
        """Return 'EMPLOYEE' / 'STUDENT' / None based on person_type."""
        if not person or not person.person_type_id:
            return None
        ptn = (person.person_type_id.name or '').upper().strip()
        if ptn in ('EMPLOYEE', 'STUDENT'):
            return ptn
        return None

    @api.model
    def _school_wants_ldap(self, school_org, child_org=None):
        """Heuristic: this school is configured for LDAP if either it or
        the child org carries the has_ou flag."""
        candidates = [school_org]
        if child_org and child_org.id != school_org.id:
            candidates.append(child_org)
        return any(
            getattr(o, 'has_ou', False)
            for o in candidates if o
        )

    @api.model
    def _ensure_school_ppsbr(self, person, school_org, role_name):
        """Create a PPSBR for the given backend role at school if it doesn't
        exist yet. Returns True if a relation was created, False if one was
        already active."""
        Role = self.env['myschool.role']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        backend_role = Role.search([('name', '=', role_name)], limit=1)
        ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
        if not backend_role or not ppsbr_type:
            return False
        existing = PropRelation.search([
            ('proprelation_type_id', '=', ppsbr_type.id),
            ('id_person', '=', person.id),
            ('id_org', '=', school_org.id),
            ('id_role', '=', backend_role.id),
            ('is_active', '=', True),
        ], limit=1)
        if existing:
            return False
        PropRelation.create({
            'name': _build_proprelation_name(
                'PPSBR', id_person=person, id_role=backend_role, id_org=school_org),
            'proprelation_type_id': ppsbr_type.id,
            'id_person': person.id,
            'id_role': backend_role.id,
            'id_org': school_org.id,
            'is_active': True,
            'is_organisational': True,
            'automatic_sync': True,
        })
        return True

    @api.model
    def _cleanup_school_ppsbr(self, person, schools, role_name):
        """Deactivate any active PPSBR for `role_name` linking this person
        to one of the given schools. Returns a list of change-log lines."""
        Role = self.env['myschool.role']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        changes = []
        if not schools:
            return changes
        backend_role = Role.search([('name', '=', role_name)], limit=1)
        ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
        if not backend_role or not ppsbr_type:
            return changes
        stale = PropRelation.search([
            ('proprelation_type_id', '=', ppsbr_type.id),
            ('id_person', '=', person.id),
            ('id_org', 'in', schools.ids),
            ('id_role', '=', backend_role.id),
            ('is_active', '=', True),
        ])
        if stale:
            stale.write({'is_active': False})
            for r in stale:
                changes.append(
                    f"Deactivated stale {role_name} PPSBR at {r.id_org.name}")
        return changes

    @api.model
    def process_manual_person_deact(self, task):
        """Deactivate a person and all related proprelations."""
        data = self._get_manual_data(task)
        if not data:
            return {'success': False, 'error': 'No data in task'}

        person_id = data.get('person_id')
        if not person_id:
            return {'success': False, 'error': 'person_id required'}

        Person = self.env['myschool.person']
        person = Person.browse(person_id).exists()
        if not person:
            return {'success': False, 'error': f'Person {person_id} not found'}

        changes = []
        person_name = f"{person.first_name} {person.name}" if person.first_name else person.name

        # LDAP cascade — emit BEFORE we deactivate, so the handler still
        # has access to the person record.
        self._emit_ldap_user_task(person, 'DEACT', changes)

        person.write({'is_active': False, 'automatic_sync': False})
        changes.append(f"Deactivated person: {person_name}")
        changes.append("Set automatic_sync=False (manual deactivation)")

        # Deactivate related proprelations
        PropRelation = self.env['myschool.proprelation']
        relations = PropRelation.search([
            '|', '|',
            ('id_person', '=', person_id),
            ('id_person_parent', '=', person_id),
            ('id_person_child', '=', person_id),
            ('is_active', '=', True),
        ])
        if relations:
            relations.write({'is_active': False})
            changes.append(f"Deactivated {len(relations)} proprelations")

        return {'success': True, 'changes': '\n'.join(changes)}

    @api.model
    def _create_and_run_task(self, target, obj, action, data, changes, label=None):
        """Create a betask AND immediately try to process it.

        Cascade tasks generated from inside a manual task should not be
        left dangling for the user to start manually — they must run as
        part of the same logical operation. We catch processing errors so
        a downstream LDAP failure doesn't roll back the parent operation;
        the failing task stays in the betask list with status='error' so
        it can be inspected/retried.
        """
        service = self.env['myschool.betask.service']
        processor = self.env['myschool.betask.processor']
        task = service.create_task(target, obj, action, data=data, auto_sync=True)
        prefix = label or f"{target}/{obj}/{action}"
        try:
            processor.process_single_task(task)
        except Exception as e:
            _logger.exception('Cascade task %s failed', prefix)
            changes.append(f"  {prefix} task FAILED: {e}")
            return task
        if task.status == 'completed_ok':
            changes.append(f"  {prefix} → completed_ok")
        else:
            changes.append(f"  {prefix} → {task.status}: {task.error_description or task.changes or ''}")
        return task

    @api.model
    def _emit_ldap_user_task(self, person, action, changes):
        """Queue *and run* an LDAP/USER/<action> betask if any of the
        person's active PERSON-TREE orgs is in an LDAP-enabled school.
        Skips silently when no LDAP school is found."""
        if not person:
            return
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        pt_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        if not pt_type:
            return
        pt_rel = PropRelation.search([
            ('proprelation_type_id', '=', pt_type.id),
            ('id_person', '=', person.id),
            ('id_org', '!=', False),
            ('is_active', '=', True),
        ], limit=1)
        org = pt_rel.id_org if pt_rel else False
        if not org:
            return
        processor = self.env['myschool.betask.processor']
        school = (processor._resolve_parent_school_from_org(org)
                  if hasattr(processor, '_resolve_parent_school_from_org')
                  else None)
        if not school or not self._school_wants_ldap(school, org):
            return
        label = f"LDAP/USER/{action} for {person.first_name} {person.name}"
        changes.append(f"Queued {label}")
        self._create_and_run_task('LDAP', 'USER', action, {
            'person_id': person.id,
            'org_id': org.id,
        }, changes, label=label)

    @api.model
    def _emit_ldap_group_renames(self, org, old_name, new_name, kind, changes):
        """Emit LDAP/GROUP/UPD when a COM/SEC group's name has changed on
        the org. The handler is expected to perform the AD modifyDN/rename.
        kind: 'COM' or 'SEC'.
        """
        if not old_name or not new_name or old_name == new_name:
            return
        processor = self.env['myschool.betask.processor']
        school = (processor._resolve_parent_school_from_org(org)
                  if hasattr(processor, '_resolve_parent_school_from_org')
                  else None)
        if not school or not self._school_wants_ldap(school, org):
            return
        label = f"LDAP/GROUP/UPD ({kind}: {old_name} -> {new_name})"
        changes.append(f"Queued {label}")
        self._create_and_run_task('LDAP', 'GROUP', 'UPD', {
            'org_id': org.id,
            'group_kind': kind,
            'old_name': old_name,
            'new_name': new_name,
        }, changes, label=label)

    @api.model
    def _emit_ldap_group_del_for_org(self, org, changes):
        """Emit LDAP/GROUP/DEL for any COM/SEC group attached to the org
        when its parent school is LDAP-enabled. Skip silently otherwise."""
        if not org:
            return
        processor = self.env['myschool.betask.processor']
        school = (processor._resolve_parent_school_from_org(org)
                  if hasattr(processor, '_resolve_parent_school_from_org')
                  else None)
        if not school or not self._school_wants_ldap(school, org):
            return
        com_name = org.com_group_name if 'com_group_name' in org._fields else None
        sec_name = org.sec_group_name if 'sec_group_name' in org._fields else None
        for group_name, kind in ((com_name, 'COM'), (sec_name, 'SEC')):
            if group_name:
                label = f"LDAP/GROUP/DEL ({kind}: {group_name})"
                changes.append(f"Queued {label}")
                self._create_and_run_task('LDAP', 'GROUP', 'DEL', {
                    'org_id': org.id,
                    'group_name': group_name,
                    'group_kind': kind,
                }, changes, label=label)

    @api.model
    def process_manual_person_del(self, task):
        """Delete a person and all related proprelations."""
        data = self._get_manual_data(task)
        if not data:
            return {'success': False, 'error': 'No data in task'}

        person_id = data.get('person_id')
        if not person_id:
            return {'success': False, 'error': 'person_id required'}

        Person = self.env['myschool.person']
        person = Person.browse(person_id).exists()
        if not person:
            return {'success': False, 'error': f'Person {person_id} not found'}

        changes = []
        person_name = f"{person.first_name} {person.name}" if person.first_name else person.name

        # LDAP cascade — emit BEFORE we delete the proprelations so the
        # handler can still resolve the person's org context. The actual
        # AD account removal will run when the LDAP betask is processed.
        self._emit_ldap_user_task(person, 'DEL', changes)

        # Delete proprelations first
        PropRelation = self.env['myschool.proprelation']
        relations = PropRelation.search([
            '|', '|',
            ('id_person', '=', person_id),
            ('id_person_parent', '=', person_id),
            ('id_person_child', '=', person_id),
        ])
        if relations:
            count = len(relations)
            relations.unlink()
            changes.append(f"Deleted {count} proprelations")

        person.with_context(skip_manual_audit=True).unlink()
        changes.append(f"Deleted person: {person_name}")

        return {'success': True, 'changes': '\n'.join(changes)}

    # ==================================================================
    # ORG handlers
    # ==================================================================

    @api.model
    def process_manual_org_add(self, task):
        """Create a new org (or attach existing) under a parent via ORG-TREE."""
        data = self._get_manual_data(task)
        if not data:
            return {'success': False, 'error': 'No data in task'}

        changes = []
        Org = self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']

        parent_org_id = data.get('parent_org_id')
        if not parent_org_id:
            return {'success': False, 'error': 'parent_org_id required'}

        parent_org = Org.browse(parent_org_id).exists()
        if not parent_org:
            return {'success': False, 'error': f'Parent org {parent_org_id} not found'}

        # Either use an existing org or create a new one
        existing_org_id = data.get('existing_org_id')
        if existing_org_id:
            child_org = Org.browse(existing_org_id).exists()
            if not child_org:
                return {'success': False, 'error': f'Existing org {existing_org_id} not found'}
            changes.append(f"Using existing org: {child_org.name}")
        else:
            org_vals = {
                'name': data.get('name', ''),
                'name_short': data.get('name_short', ''),
                'is_active': True,
            }
            for key in ('inst_nr', 'ou_fqdn_internal', 'ou_fqdn_external',
                        'com_group_name', 'com_group_email',
                        'com_group_fqdn_internal', 'com_group_fqdn_external',
                        'sec_group_name', 'sec_group_fqdn_internal', 'sec_group_fqdn_external',
                        'domain_internal', 'domain_external',
                        'name_tree', 'has_ou', 'has_comgroup', 'has_secgroup'):
                if data.get(key) is not None:
                    org_vals[key] = data[key]
            if data.get('org_type_id'):
                org_vals['org_type_id'] = data['org_type_id']
            child_org = Org.create(org_vals)
            changes.append(f"Created org: {child_org.name} (ID: {child_org.id})")

        if child_org.id == parent_org.id:
            return {'success': False, 'error': 'An organization cannot be its own parent'}

        # ORG-TREE type
        org_tree_type = self._get_or_create_proprelation_type('ORG-TREE', 'Organization hierarchy relationship')

        # Check already linked
        existing = PropRelation.search([
            ('id_org', '=', child_org.id),
            ('id_org_parent', '=', parent_org.id),
            ('proprelation_type_id', '=', org_tree_type.id),
            ('is_active', '=', True),
        ], limit=1)
        if existing:
            return {'success': False, 'error': f'{child_org.name} is already a child of {parent_org.name}'}

        # Deactivate any old parent relation
        old_parent = PropRelation.search([
            ('id_org', '=', child_org.id),
            ('id_org_parent', '!=', False),
            ('proprelation_type_id', '=', org_tree_type.id),
            ('is_active', '=', True),
        ])
        if old_parent:
            old_parent.write({'is_active': False})
            changes.append(f"Deactivated {len(old_parent)} old parent relation(s)")

        rel_name = _build_proprelation_name('ORG-TREE', id_org=child_org, id_org_parent=parent_org)
        PropRelation.create({
            'name': rel_name,
            'proprelation_type_id': org_tree_type.id,
            'id_org': child_org.id,
            'id_org_parent': parent_org.id,
            'is_active': True,
        })
        changes.append(f"Created ORG-TREE relation: {child_org.name} under {parent_org.name}")

        # If PERSONGROUP, create PG-P relations for members
        org_type_name = data.get('org_type_name')
        if org_type_name == 'PERSONGROUP' and data.get('member_ids'):
            pg_p_type = self._get_or_create_proprelation_type('PG-P', 'Persongroup-Person membership')
            for person_id in data['member_ids']:
                person = self.env['myschool.person'].browse(person_id).exists()
                if person:
                    existing = PropRelation.search([
                        ('proprelation_type_id', '=', pg_p_type.id),
                        ('id_org', '=', child_org.id),
                        ('id_person', '=', person_id),
                        ('is_active', '=', True),
                    ], limit=1)
                    if not existing:
                        rel_name = _build_proprelation_name('PG-P', id_org=child_org, id_person=person)
                        PropRelation.create({
                            'name': rel_name,
                            'proprelation_type_id': pg_p_type.id,
                            'id_org': child_org.id,
                            'id_person': person_id,
                            'is_active': True,
                        })
                        changes.append(f"Added member {person.name} to persongroup")

        # Auto-sync persongroup if org has has_comgroup
        if child_org.has_comgroup:
            self._sync_org_persongroup(child_org)
            changes.append(f"Synced persongroup for {child_org.name}")

        # LDAP cascade — provision the OU container in AD so subsequent
        # user/group creations in this org succeed without _ensure_ou_path
        # having to backfill.
        self._emit_ldap_org_add(child_org, changes)

        return {'success': True, 'changes': '\n'.join(changes)}

    @api.model
    def _emit_ldap_org_add(self, org, changes):
        """Queue *and run* an LDAP/ORG/ADD task for the org if its parent
        school is LDAP-enabled and the org has either an
        ``ou_fqdn_internal`` (regular org → OU) or a group FQDN
        (persongroup → AD group)."""
        if not org:
            return
        org_type_name = (org.org_type_id.name or '').upper()
        is_persongroup = org_type_name == 'PERSONGROUP'
        has_target_dn = (
            bool(getattr(org, 'ou_fqdn_internal', '')) if not is_persongroup
            else (bool(getattr(org, 'com_group_fqdn_internal', ''))
                  or bool(getattr(org, 'sec_group_fqdn_internal', '')))
        )
        if not has_target_dn:
            return
        processor = self.env['myschool.betask.processor']
        school = (processor._resolve_parent_school_from_org(org)
                  if hasattr(processor, '_resolve_parent_school_from_org')
                  else None)
        if not school or not self._school_wants_ldap(school, org):
            return
        label = f"LDAP/ORG/ADD for {org.name}"
        changes.append(f"Queued {label}")
        self._create_and_run_task('LDAP', 'ORG', 'ADD', {
            'org_id': org.id,
        }, changes, label=label)

    @api.model
    def process_manual_org_upd(self, task):
        """Update org: move to new parent (re-parent) or update fields."""
        data = self._get_manual_data(task)
        if not data:
            return {'success': False, 'error': 'No data in task'}

        org_id = data.get('org_id')
        if not org_id:
            return {'success': False, 'error': 'org_id required'}

        # Generic field update mode
        update_vals = data.get('vals')
        if update_vals:
            Org = self.env['myschool.org']
            org = Org.browse(org_id).exists()
            if not org:
                return {'success': False, 'error': f'Org {org_id} not found'}

            # Snapshot LDAP-relevant attributes BEFORE write so we know
            # which AD groups must be renamed.
            old_com_name = org.com_group_name if 'com_group_name' in org._fields else None
            old_sec_name = org.sec_group_name if 'sec_group_name' in org._fields else None
            old_name = org.name

            org.write(update_vals)
            changes = [f"Updated org {org.name}: {update_vals}"]

            # Cascade: COM/SEC group renames in AD.
            new_com_name = org.com_group_name if 'com_group_name' in org._fields else None
            new_sec_name = org.sec_group_name if 'sec_group_name' in org._fields else None
            self._emit_ldap_group_renames(
                org, old_com_name, new_com_name, 'COM', changes)
            self._emit_ldap_group_renames(
                org, old_sec_name, new_sec_name, 'SEC', changes)
            return {'success': True, 'changes': '\n'.join(changes)}

        # Move mode (legacy)
        new_parent_id = data.get('new_parent_id')
        move_to_root = data.get('move_to_root', False)

        Org = self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']

        org = Org.browse(org_id).exists()
        if not org:
            return {'success': False, 'error': f'Org {org_id} not found'}

        org_tree_type = self._get_or_create_proprelation_type(
            'ORG-TREE', 'Organization hierarchy relationship')

        if move_to_root:
            existing = PropRelation.search([
                ('id_org', '=', org_id),
                ('id_org_parent', '!=', False),
                ('proprelation_type_id', '=', org_tree_type.id),
                ('is_active', '=', True),
            ])
            if existing:
                existing.write({'is_active': False})
            return {'success': True, 'changes': f"Moved org {org.name} to root"}

        if not new_parent_id:
            return {'success': False, 'error': 'new_parent_id required (or move_to_root=True)'}

        new_parent = Org.browse(new_parent_id).exists()
        if not new_parent:
            return {'success': False, 'error': f'Parent org {new_parent_id} not found'}

        # Cycle check
        if org_id == new_parent_id:
            return {'success': False, 'error': 'An org cannot be its own parent'}
        current = new_parent_id
        visited = set()
        while current and current not in visited:
            visited.add(current)
            if current == org_id:
                return {'success': False, 'error': 'Cannot move: would create circular reference'}
            rel = PropRelation.search([
                ('id_org', '=', current),
                ('id_org_parent', '!=', False),
                ('proprelation_type_id', '=', org_tree_type.id),
                ('is_active', '=', True),
            ], limit=1)
            current = rel.id_org_parent.id if rel else None

        changes = []

        # Update or create ORG-TREE relation
        rel_name = _build_proprelation_name('ORG-TREE', id_org=org, id_org_parent=new_parent)
        existing = PropRelation.search([
            ('id_org', '=', org_id),
            ('id_org_parent', '!=', False),
            ('proprelation_type_id', '=', org_tree_type.id),
            ('is_active', '=', True),
        ], limit=1)
        if existing:
            existing.write({
                'name': rel_name,
                'id_org_parent': new_parent_id,
            })
        else:
            PropRelation.create({
                'name': rel_name,
                'proprelation_type_id': org_tree_type.id,
                'id_org': org_id,
                'id_org_parent': new_parent_id,
                'is_active': True,
            })
        changes.append(f"Moved org {org.name} under {new_parent.name}")

        # Update FQDN fields
        org_short = org.name_short if hasattr(org, 'name_short') and org.name_short else org.name
        if hasattr(new_parent, 'ou_fqdn_internal') and new_parent.ou_fqdn_internal:
            org.write({'ou_fqdn_internal': f"ou={org_short.lower()},{new_parent.ou_fqdn_internal.lower()}"})
        if hasattr(new_parent, 'ou_fqdn_external') and new_parent.ou_fqdn_external:
            org.write({'ou_fqdn_external': f"ou={org_short.lower()},{new_parent.ou_fqdn_external.lower()}"})

        # Update name_tree from new FQDN
        if hasattr(org, 'ou_fqdn_internal') and org.ou_fqdn_internal:
            components = org.ou_fqdn_internal.lower().split(',')
            dc_parts, ou_parts = [], []
            for comp in components:
                comp = comp.strip()
                if comp.startswith('dc='):
                    dc_parts.append(comp[3:])
                elif comp.startswith('ou='):
                    ou_parts.append(comp[3:])
            dc_parts.reverse()
            ou_parts.reverse()
            name_tree = '.'.join(dc_parts + ou_parts)
            if name_tree and org.name_tree != name_tree:
                org.write({'name_tree': name_tree})
                changes.append(f"Updated name_tree: {name_tree}")

        return {'success': True, 'changes': '\n'.join(changes)}

    @api.model
    def process_manual_org_del(self, task):
        """Delete an org and all its proprelations."""
        data = self._get_manual_data(task)
        if not data:
            return {'success': False, 'error': 'No data in task'}

        org_id = data.get('org_id')
        if not org_id:
            return {'success': False, 'error': 'org_id required'}

        Org = self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']

        org = Org.browse(org_id).exists()
        if not org:
            return {'success': False, 'error': f'Org {org_id} not found'}

        changes = []
        org_name = org.name

        # LDAP cascade — emit GROUP/DEL betasks BEFORE unlink so the
        # handler can still resolve the org context when the AD groups
        # are deleted. Captures both COM and SEC group names if present.
        self._emit_ldap_group_del_for_org(org, changes)

        # Delete all proprelations referencing this org
        all_rels = PropRelation.search([
            '|', '|',
            ('id_org', '=', org.id),
            ('id_org_parent', '=', org.id),
            ('id_org_child', '=', org.id),
        ])
        if all_rels:
            count = len(all_rels)
            all_rels.unlink()
            changes.append(f"Deleted {count} proprelation(s)")

        # Clear stored computed tree_org_id on persons referencing this org
        Person = self.env['myschool.person'].with_context(active_test=False)
        persons = Person.search([('tree_org_id', '=', org.id)])
        if persons:
            persons.write({'tree_org_id': False})
            changes.append(f"Cleared tree_org_id on {len(persons)} person(s)")

        # Delete the org itself
        org.with_context(skip_pg_flag_handling=True).unlink()
        changes.append(f"Deleted org: {org_name} (ID: {org_id})")

        return {'success': True, 'changes': '\n'.join(changes)}

    # ==================================================================
    # PROPRELATION handlers
    # ==================================================================

    @api.model
    def process_manual_proprelation_add(self, task):
        """Create a proprelation (PERSON-TREE, PPSBR, SRBR, or BRSO)."""
        data = self._get_manual_data(task)
        if not data:
            return {'success': False, 'error': 'No data in task'}

        rel_type_name = data.get('type')
        if not rel_type_name:
            return {'success': False, 'error': "'type' key required in data"}

        PropRelation = self.env['myschool.proprelation']
        rel_type = self._get_or_create_proprelation_type(rel_type_name)

        # Build proprelation vals from data
        proprel_vals = {
            'proprelation_type_id': rel_type.id,
            'is_active': True,
        }

        # Map optional foreign key fields
        fk_fields = {
            'person_id': ('id_person', 'myschool.person'),
            'org_id': ('id_org', 'myschool.org'),
            'org_parent_id': ('id_org_parent', 'myschool.org'),
            'role_id': ('id_role', 'myschool.role'),
            'role_parent_id': ('id_role_parent', 'myschool.role'),
        }
        name_kwargs = {}
        for data_key, (field_name, model_name) in fk_fields.items():
            record_id = data.get(data_key)
            if record_id:
                record = self.env[model_name].browse(record_id).exists()
                if not record:
                    return {'success': False, 'error': f'{model_name} with id {record_id} not found'}
                proprel_vals[field_name] = record_id
                name_kwargs[field_name] = record

        # Check for existing active relation (avoid duplicates)
        dup_domain = [
            ('proprelation_type_id', '=', rel_type.id),
            ('is_active', '=', True),
        ]
        for data_key, (field_name, _) in fk_fields.items():
            if data.get(data_key):
                dup_domain.append((field_name, '=', data[data_key]))
        existing = PropRelation.search(dup_domain, limit=1)
        if existing:
            # Check for inactive relation and reactivate
            inactive_domain = []
            for d in dup_domain:
                if d == ('is_active', '=', True):
                    inactive_domain.append(('is_active', '=', False))
                else:
                    inactive_domain.append(d)
            inactive = PropRelation.search(inactive_domain, limit=1)
            if inactive:
                inactive.write({'is_active': True})
                return {'success': True, 'changes': f"Reactivated {rel_type_name} relation (ID: {inactive.id})"}
            return {'success': False, 'error': f'{rel_type_name} relation already exists'}

        # Build name
        proprel_vals['name'] = _build_proprelation_name(rel_type_name, **name_kwargs)

        new_rel = PropRelation.create(proprel_vals)
        changes = [f"Created {rel_type_name} relation: {proprel_vals['name']}"]

        # BRSO setup-intent: when the wizard ticks "this role gets a
        # COM/SEC group at this org" or "accounts here", we *promote*
        # those flags onto the **target org**. The org-flag-flip handler
        # (``_handle_persongroup_flags``) then provisions the persongroup
        # + AD groups. No more BRSO-level flags.
        if rel_type_name == 'BRSO' and new_rel.id_org:
            target_promote = {}
            if data.get('has_comgroup') or data.get('has_ldap_com_group') \
                    or data.get('has_odoo_group'):
                if not new_rel.id_org.has_comgroup:
                    target_promote['has_comgroup'] = True
            if data.get('has_secgroup') or data.get('has_ldap_sec_group'):
                if not new_rel.id_org.has_secgroup:
                    target_promote['has_secgroup'] = True
            if data.get('has_odoo_group') and not new_rel.id_org.has_odoo_group:
                target_promote['has_odoo_group'] = True
            if target_promote:
                new_rel.id_org.write(target_promote)
                changes.append(
                    f"Promoted setup intent to {new_rel.id_org.name}: "
                    f"{list(target_promote)}")

        # Cascade for PPSBR (person-role-school link): if the role has any
        # COM/SEC LDAP groups attached at this school via BRSO, emit
        # GROUPMEMBER/ADD tasks so the AD groups get the new member.
        if rel_type_name == 'PPSBR':
            grp_changes = self._cascade_ppsbr_group_membership(new_rel, action='ADD')
            if grp_changes:
                changes.extend(grp_changes)

        return {'success': True, 'changes': '\n'.join(changes)}

    @api.model
    def _cascade_ppsbr_group_membership(self, ppsbr, action='ADD'):
        """When a PPSBR is (de)activated, queue LDAP/GROUPMEMBER tasks for
        every COM/SEC group that exists for the same role at the same
        school (or any ORG-TREE ancestor of the PPSBR's org) via an
        active BRSO with has_ldap_com_group / has_ldap_sec_group.
        action: 'ADD' or 'REMOVE'.
        """
        changes = []
        if not ppsbr.id_person or not ppsbr.id_role or not ppsbr.id_org:
            return changes
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
        if not brso_type:
            return changes
        # BRSOs are typically defined on a koepel/parent school while
        # PPSBRs live at the concrete sub-school. Match against the
        # entire ORG-TREE chain so a PPSBR at SO2 finds the BRSO that's
        # registered at SO.
        org_ancestors = self._collect_org_ancestor_ids(ppsbr.id_org)
        if not org_ancestors:
            org_ancestors = [ppsbr.id_org.id]
        brso = PropRelation.search([
            ('proprelation_type_id', '=', brso_type.id),
            ('id_role', '=', ppsbr.id_role.id),
            ('id_org_parent', 'in', org_ancestors),
            ('is_active', '=', True),
        ], limit=1)
        if not brso or not brso.id_org:
            return changes
        # Source of truth = the target org's group-flags (post-migration).
        target_org = brso.id_org
        for org_flag, kind in (('has_comgroup', 'COM'),
                               ('has_secgroup', 'SEC')):
            if getattr(target_org, org_flag, False):
                lbl = (f"LDAP/GROUPMEMBER/{action} ({kind}) for "
                       f"{ppsbr.id_person.name}")
                changes.append(f"Queued {lbl}")
                self._create_and_run_task(
                    'LDAP', 'GROUPMEMBER', action,
                    {
                        'person_id': ppsbr.id_person.id,
                        'brso_id': brso.id,
                        'org_id': target_org.id,
                        'group_kind': kind,
                    },
                    changes, label=lbl)
        return changes

    @api.model
    def process_manual_proprelation_upd(self, task):
        """Update proprelation fields (is_master, automatic_sync, name, etc.).

        For PPSBR records whose `id_role` or `id_org` change, this also
        emits LDAP/GROUPMEMBER REMOVE on the old role/org context and ADD
        on the new one — effectively a member-move in the AD groups.
        """
        data = self._get_manual_data(task)
        if not data:
            return {'success': False, 'error': 'No data in task'}

        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
        changes = []

        proprelation_id = data.get('proprelation_id')
        proprelation_ids = data.get('proprelation_ids')
        update_vals = data.get('vals', {})

        if not update_vals:
            return {'success': False, 'error': 'No vals to update'}

        # Determine whether the update will move a PPSBR member between
        # groups (changes id_role or id_org).
        relation_move_keys = {'id_role', 'id_org'}
        is_member_move = bool(set(update_vals.keys()) & relation_move_keys)

        target_ids = []
        if proprelation_id:
            target_ids.append(proprelation_id)
        if proprelation_ids:
            target_ids.extend(proprelation_ids)

        if not target_ids:
            return {'success': False, 'error': 'No proprelations specified'}

        rels = PropRelation.browse(target_ids).exists()
        if not rels:
            return {'success': False, 'error': 'No proprelations found to update'}

        # Snapshot old PPSBRs before write so we can emit REMOVE for the
        # old role+org combination.
        old_ppsbrs = []
        if is_member_move and ppsbr_type:
            for r in rels.filtered(lambda x: x.proprelation_type_id.id == ppsbr_type.id):
                old_ppsbrs.append({
                    'id': r.id,
                    'person_id': r.id_person.id if r.id_person else None,
                    'role_id': r.id_role.id if r.id_role else None,
                    'org_id': r.id_org.id if r.id_org else None,
                })
            for snap in old_ppsbrs:
                # Build a virtual ppsbr-like browse record with old fields by
                # browsing the relation and emitting cascade based on its
                # current values (still old before write).
                ppsbr_rec = PropRelation.browse(snap['id'])
                grp_changes = self._cascade_ppsbr_group_membership(
                    ppsbr_rec, action='REMOVE')
                changes.extend(grp_changes)

        rels.write(update_vals)
        changes.append(f"Updated {len(rels)} proprelation(s): {update_vals}")

        # After write, emit ADD for the new role+org context on the same
        # PPSBR records.
        if is_member_move and ppsbr_type:
            for r in rels.filtered(lambda x: x.proprelation_type_id.id == ppsbr_type.id):
                grp_changes = self._cascade_ppsbr_group_membership(r, action='ADD')
                changes.extend(grp_changes)

        return {'success': True, 'changes': '\n'.join(changes)}

    def process_manual_proprelation_deact(self, task):
        """Deactivate proprelations (by IDs or by person+org)."""
        data = self._get_manual_data(task)
        if not data:
            return {'success': False, 'error': 'No data in task'}

        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
        changes = []

        # Capture PPSBRs we'll deactivate so we can emit LDAP cascades
        # BEFORE the records are written inactive.
        affected_ppsbrs = self.env['myschool.proprelation']

        # Mode 1: explicit IDs
        proprelation_ids = data.get('proprelation_ids')
        if proprelation_ids:
            rels = PropRelation.browse(proprelation_ids).exists()
            if rels:
                if ppsbr_type:
                    affected_ppsbrs |= rels.filtered(
                        lambda r: r.proprelation_type_id.id == ppsbr_type.id)
                # Emit LDAP cascade BEFORE deactivation.
                for ppsbr in affected_ppsbrs:
                    grp_changes = self._cascade_ppsbr_group_membership(
                        ppsbr, action='REMOVE')
                    changes.extend(grp_changes)
                rels.write({'is_active': False})
                changes.append(f"Deactivated {len(rels)} proprelation(s) by ID")

        # Mode 2: person + org (deactivate by type or default PERSON-TREE)
        person_id = data.get('person_id')
        org_id = data.get('org_id')
        rel_type_name = data.get('type', 'PERSON-TREE')
        if person_id and org_id:
            rel_type = self._get_or_create_proprelation_type(rel_type_name)
            rels = PropRelation.search([
                ('id_person', '=', person_id),
                ('id_org', '=', org_id),
                ('proprelation_type_id', '=', rel_type.id),
                ('is_active', '=', True),
            ])
            if rels:
                # Cascade for PPSBR before deactivation
                if rel_type_name == 'PPSBR':
                    for ppsbr in rels:
                        grp_changes = self._cascade_ppsbr_group_membership(
                            ppsbr, action='REMOVE')
                        changes.extend(grp_changes)
                rels.write({'is_active': False})
                changes.append(f"Deactivated {len(rels)} {rel_type_name} relation(s) for person {person_id} in org {org_id}")

        if not changes:
            return {'success': False, 'error': 'No proprelations found to deactivate'}

        return {'success': True, 'changes': '\n'.join(changes)}

    # =========================================================================
    # BRSO GROUP HELPERS
    # =========================================================================

    @api.model
    def _build_org_tree_group_names(self, org, school_org=None):
        """Build COM and SEC group names from the org's name_tree.

        Uses the name_tree field (e.g. 'test.olvp.baple.pers.adm') to derive
        the group name following the existing convention:
          grp-{org}-{parent}-...-{school}  /  bgrp-{org}-{parent}-...-{school}

        Example:
          org.name_tree  = 'test.olvp.baple.pers.adm'
          school name_tree = 'test.olvp.baple'
          → grp-adm-pers-baple / bgrp-adm-pers-baple

        Returns:
            Tuple (com_name, sec_name) or (None, None) on failure.
        """
        _logger.info('[BRSO-GRP] Building group names for org=%s (id=%s, name_tree=%s), school=%s (name_tree=%s)',
                     org.name, org.id, org.name_tree,
                     school_org.name if school_org else None,
                     school_org.name_tree if school_org else None)

        if not org.name_tree:
            _logger.warning('[BRSO-GRP] Org %s has no name_tree', org.name)
            return None, None

        # Resolve school name_tree prefix
        school_tree = ''
        if school_org and school_org.name_tree:
            school_tree = school_org.name_tree

        org_tree = org.name_tree

        if school_tree and org_tree.startswith(school_tree):
            # Strip school prefix, get sub-path parts
            sub_path = org_tree[len(school_tree):].strip('.')
            school_short = school_tree.split('.')[-1]
            if sub_path:
                sub_parts = sub_path.split('.')
                name_parts = list(reversed(sub_parts)) + [school_short]
            else:
                # Org IS the school
                name_parts = [school_short]
        else:
            # No school prefix match: extract OU parts from name_tree
            # name_tree = 'dc1.dc2.school.parent.org' → take from school onwards
            # Find the school short in the parts to split correctly
            org_parts = org_tree.split('.')
            school_short = None
            if school_org:
                school_short = (school_org.name_short or '').lower()
            if school_short and school_short in org_parts:
                idx = org_parts.index(school_short)
                ou_parts = org_parts[idx:]  # from school to org
                name_parts = list(reversed(ou_parts))
            else:
                # Last resort: skip first 2 parts (domain) and reverse
                ou_parts = org_parts[2:] if len(org_parts) > 2 else org_parts
                name_parts = list(reversed(ou_parts))

        if not name_parts:
            return None, None

        joined = '-'.join(name_parts)
        _logger.info('[BRSO-GRP] Built group names: grp-%s / bgrp-%s', joined, joined)
        return f'grp-{joined}', f'bgrp-{joined}'

    @api.model
    def _find_persons_in_ou(self, org):
        """Find all person IDs placed in the given org via PERSON-TREE."""
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        pt_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        if not pt_type:
            return []

        rels = PropRelation.search([
            ('proprelation_type_id', '=', pt_type.id),
            ('id_org', '=', org.id),
            ('is_active', '=', True),
            ('id_person', '!=', False),
        ])
        return list(set(r.id_person.id for r in rels))

    @api.model
    def _find_role_persons_at_school(self, role, school_org):
        """Find all person IDs with a given role at a school (via active PPSBR)."""
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        Org = self.env['myschool.org']

        ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
        if not ppsbr_type:
            return []

        school_org_ids = {school_org.id}
        if school_org.inst_nr:
            same_inst = Org.search([
                ('inst_nr', '=', school_org.inst_nr),
                ('is_active', '=', True),
            ])
            school_org_ids.update(same_inst.ids)

        ppsbr_rels = PropRelation.search([
            ('proprelation_type_id', '=', ppsbr_type.id),
            ('id_role', '=', role.id),
            ('id_org_parent', 'in', list(school_org_ids)),
            ('is_active', '=', True),
            ('id_person', '!=', False),
        ])
        return list(set(r.id_person.id for r in ppsbr_rels))

    @api.model
    def _get_brso_member_ids(self, brso_rel):
        """Get the person IDs covered by a BRSO: every person that has
        an active PPSBR for the BRSO's role at the BRSO's school.

        The old has_accounts split (OU-scoped vs role-scoped) is gone;
        the role-scoped reading is the right default — everyone with
        the role belongs in the resulting group/tree position.
        """
        org = brso_rel.id_org
        role = brso_rel.id_role
        school_org = brso_rel.id_org_parent
        if not org or not role or not school_org:
            return []

        processor = self.env['myschool.betask.processor']
        school_org = processor._resolve_school_org(school_org)
        return self._find_role_persons_at_school(role, school_org)


    @api.model
    def _delete_persongroup_by_name(self, group_name, school_org, changes):
        """Find and delete a persongroup org by name under the school's OuForGroups."""
        if not school_org:
            return

        processor = self.env['myschool.betask.processor']
        ou_value, ou_org = processor._resolve_ou_for_groups_org(school_org)
        if not ou_org:
            return

        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        Org = self.env['myschool.org']
        OrgType = self.env['myschool.org.type']

        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)
        pg_type = OrgType.search([('name', '=', 'PERSONGROUP')], limit=1)
        if not org_tree_type or not pg_type:
            return

        # Find children of OuForGroups
        child_rels = PropRelation.search([
            ('proprelation_type_id', '=', org_tree_type.id),
            ('id_org_parent', '=', ou_org.id),
            ('is_active', '=', True),
        ])
        child_org_ids = [r.id_org.id for r in child_rels if r.id_org]
        if not child_org_ids:
            return

        pg = Org.search([
            ('id', 'in', child_org_ids),
            ('name_short', '=ilike', group_name.lower()),
            ('org_type_id', '=', pg_type.id),
        ], limit=1)

        if pg:
            # Deactivate PG-P members
            pg_p_type = PropRelationType.search([('name', '=', 'PG-P')], limit=1)
            if pg_p_type:
                pg_p_rels = PropRelation.search([
                    ('proprelation_type_id', '=', pg_p_type.id),
                    ('id_org', '=', pg.id),
                    ('is_active', '=', True),
                ])
                if pg_p_rels:
                    pg_p_rels.write({'is_active': False})

            # Deactivate ORG-TREE for this persongroup
            tree_rels = PropRelation.search([
                ('proprelation_type_id', '=', org_tree_type.id),
                ('id_org', '=', pg.id),
                ('is_active', '=', True),
            ])
            if tree_rels:
                tree_rels.write({'is_active': False})

            # Deactivate the persongroup org
            pg.write({'is_active': False})
            changes.append(f'Deactivated persongroup: {pg.name} (ID: {pg.id})')

    # =========================================================================
    # PERSON TREE POSITION
    # =========================================================================

    @api.model
    def _update_person_tree_position(self, person):
        """Update a person's PERSON-TREE and FQDN fields based on role assignments.

        ``manual_task_processor`` extends ``myschool.betask.processor``
        via ``_inherit`` (single model, two files), so the canonical
        priority-driven resolver lives in ``betask_processor`` and we
        reach it with ``super()``. Calling
        ``self.env['myschool.betask.processor']._update_person_tree_position``
        would re-enter this very override and recurse.
        """
        super()._update_person_tree_position(person)

        # Pull the resulting target org back off the active PERSON-TREE
        # so we can recompute the FQDN strings against it.
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        pt_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        if not pt_type:
            return
        existing_pt = PropRelation.search([
            ('proprelation_type_id', '=', pt_type.id),
            ('id_person', '=', person.id),
            ('is_active', '=', True),
        ], limit=1)
        target_org = existing_pt.id_org if existing_pt else None
        if not target_org:
            return

        # Update FQDN fields
        email_account = person.email_cloud.split('@')[0] if person.email_cloud and '@' in person.email_cloud else ''
        person_vals = {}
        if email_account and target_org.ou_fqdn_internal:
            person_vals['person_fqdn_internal'] = f"cn={email_account},{target_org.ou_fqdn_internal}".lower()
        if email_account and target_org.ou_fqdn_external:
            person_vals['person_fqdn_external'] = f"cn={email_account},{target_org.ou_fqdn_external}".lower()
        if person_vals:
            person.write(person_vals)
            _logger.info(f'[TREE] Updated FQDN for {person.name}: {person_vals}')

    @api.model
    def _update_tree_positions_for_brso(self, brso_rel):
        """Recompute PERSON-TREE for all persons covered by this BRSO."""
        person_ids = self._get_brso_member_ids(brso_rel)
        Person = self.env['myschool.person']
        for pid in person_ids:
            person = Person.browse(pid)
            if person.exists():
                self._update_person_tree_position(person)
