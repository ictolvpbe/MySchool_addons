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
        person_vals = {
            'first_name': data.get('first_name', ''),
            'name': data.get('name', ''),
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
                    'name': f"{data.get('first_name', '')} {data.get('name', '')}".strip(),
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
            return {'success': True, 'changes': f"Updated person {person.name}: {update_vals}"}

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

        # Deactivate old PERSON-TREE relations
        old_rels = PropRelation.search([
            ('id_person', '=', person_id),
            ('id_org', '!=', False),
            ('is_active', '=', True),
            ('proprelation_type_id', '=', pt_type.id),
        ])
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

        return {
            'success': True,
            'changes': f"Moved person {person.first_name} {person.name} to {new_org.name_tree or new_org.name}",
        }

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
                        'name_tree', 'has_ou', 'has_role', 'has_comgroup', 'has_secgroup'):
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

        return {'success': True, 'changes': '\n'.join(changes)}

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
            org.write(update_vals)
            return {'success': True, 'changes': f"Updated org {org.name}: {update_vals}"}

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

        # Set group flags from data (BRSO only)
        for bool_field in ('has_accounts', 'has_ldap_com_group', 'has_ldap_sec_group', 'has_odoo_group'):
            if data.get(bool_field):
                proprel_vals[bool_field] = True

        # Build name
        proprel_vals['name'] = _build_proprelation_name(rel_type_name, **name_kwargs)

        new_rel = PropRelation.create(proprel_vals)
        changes = [f"Created {rel_type_name} relation: {proprel_vals['name']}"]

        # Create groups and sync members for BRSO with group flags
        if rel_type_name == 'BRSO':
            group_changes = self._process_brso_groups(new_rel, data)
            if group_changes:
                changes.extend(group_changes)

        return {'success': True, 'changes': '\n'.join(changes)}

    @api.model
    @api.model
    def process_manual_proprelation_upd(self, task):
        """Update proprelation fields (is_master, automatic_sync, name, etc.)."""
        data = self._get_manual_data(task)
        if not data:
            return {'success': False, 'error': 'No data in task'}

        PropRelation = self.env['myschool.proprelation']
        changes = []

        proprelation_id = data.get('proprelation_id')
        proprelation_ids = data.get('proprelation_ids')
        update_vals = data.get('vals', {})

        if not update_vals:
            return {'success': False, 'error': 'No vals to update'}

        if proprelation_id:
            rel = PropRelation.browse(proprelation_id).exists()
            if rel:
                rel.write(update_vals)
                changes.append(f"Updated proprelation {rel.name} (ID: {rel.id}): {update_vals}")

        if proprelation_ids:
            rels = PropRelation.browse(proprelation_ids).exists()
            if rels:
                rels.write(update_vals)
                changes.append(f"Updated {len(rels)} proprelation(s): {update_vals}")

        if not changes:
            return {'success': False, 'error': 'No proprelations found to update'}

        return {'success': True, 'changes': '\n'.join(changes)}

    def process_manual_proprelation_deact(self, task):
        """Deactivate proprelations (by IDs or by person+org)."""
        data = self._get_manual_data(task)
        if not data:
            return {'success': False, 'error': 'No data in task'}

        PropRelation = self.env['myschool.proprelation']
        changes = []

        # Collect affected org IDs for flag update
        affected_org_ids = set()

        # Mode 1: explicit IDs
        proprelation_ids = data.get('proprelation_ids')
        if proprelation_ids:
            rels = PropRelation.browse(proprelation_ids).exists()
            if rels:
                for r in rels:
                    if r.id_org:
                        affected_org_ids.add(r.id_org.id)
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
                rels.write({'is_active': False})
                affected_org_ids.add(org_id)
                changes.append(f"Deactivated {len(rels)} {rel_type_name} relation(s) for person {person_id} in org {org_id}")

        if not changes:
            return {'success': False, 'error': 'No proprelations found to deactivate'}

        # Update org feature flags after BRSO deactivation
        if affected_org_ids:
            orgs = self.env['myschool.org'].browse(list(affected_org_ids)).exists()
            orgs.update_org_flags()

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
        """Get the person IDs for a BRSO based on has_accounts flag.

        has_accounts=True:  persons in the OU ∩ persons with role
                            (accounts live in this org, so OU-scoped)
        has_accounts=False: all persons with the role in school-context
                            (role-based membership, not OU-scoped)
        """
        org = brso_rel.id_org
        role = brso_rel.id_role
        school_org = brso_rel.id_org_parent
        if not org or not role or not school_org:
            return []

        processor = self.env['myschool.betask.processor']
        school_org = processor._resolve_school_org(school_org)

        if brso_rel.has_accounts:
            # OU-scoped: persons in this org WITH the role
            persons_in_ou = set(self._find_persons_in_ou(org))
            persons_with_role = set(self._find_role_persons_at_school(role, school_org))
            return list(persons_in_ou & persons_with_role)
        else:
            # School-context: all persons with the role at the school
            return self._find_role_persons_at_school(role, school_org)

    @api.model
    def _process_brso_groups(self, brso_rel, data):
        """Create LDAP/Odoo groups for a BRSO and add members.

        Uses org.com_group_name and org.sec_group_name for naming.
        Uses com_group_name as Odoo group name.

        Membership strategy (from brso_rel.has_accounts):
          True:  persons in the OU with the role (PERSON-TREE ∩ PPSBR)
          False: persons with the role in school-context (PPSBR)

        Args:
            brso_rel: The BRSO proprelation record.
            data: Dict with flags being enabled (has_ldap_com_group, etc.).

        Returns:
            List of change description strings.
        """
        changes = []

        has_accounts = data.get('has_accounts', False)
        has_ldap_com = data.get('has_ldap_com_group', False)
        has_ldap_sec = data.get('has_ldap_sec_group', False)
        has_odoo = data.get('has_odoo_group', False)

        if not (has_accounts or has_ldap_com or has_ldap_sec or has_odoo):
            return changes

        org = brso_rel.id_org
        role = brso_rel.id_role
        school_org = brso_rel.id_org_parent
        if not org or not role:
            _logger.warning('[BRSO-GRP] Missing org or role on BRSO %s', brso_rel.name)
            return changes

        # Resolve school
        processor = self.env['myschool.betask.processor']
        if school_org:
            school_org = processor._resolve_school_org(school_org)

        # Use org's group name fields; fallback to name_tree-based if not set
        com_name = org.com_group_name
        sec_name = org.sec_group_name
        if not com_name or not sec_name:
            built_com, built_sec = self._build_org_tree_group_names(org, school_org)
            if not com_name:
                com_name = built_com
            if not sec_name:
                sec_name = built_sec
            if not com_name:
                _logger.warning('[BRSO-GRP] No group name for org %s', org.name)
                return changes
            # Persist the computed names
            org.write({'com_group_name': com_name, 'sec_group_name': sec_name})
            changes.append(f'Set org group names: {com_name} / {sec_name}')

        service = self.env['myschool.betask.service']

        # --- Create accounts and update tree positions when has_accounts enabled ---
        if has_accounts:
            person_ids = self._get_brso_member_ids(brso_rel)
            for person_id in person_ids:
                # LDAP account
                service.create_task('LDAP', 'USER', 'ADD', data={
                    'person_id': person_id,
                    'org_id': org.id,
                })
                # Odoo account
                service.create_task('ODOO', 'PERSON', 'ADD', data={
                    'person_id': person_id,
                })
            if person_ids:
                changes.append(f'Queued account creation (LDAP+Odoo) for {len(person_ids)} person(s)')

            # Update PERSON-TREE positions and FQDN fields
            self._update_tree_positions_for_brso(brso_rel)
            changes.append(f'Updated tree positions for persons in {org.name}')

        # --- Create LDAP COM group + persongroup ---
        if has_ldap_com:
            service.create_task('LDAP', 'GROUP', 'ADD', data={
                'group_name': com_name,
                'org_id': org.id,
                'description': f'COM group for role {role.name} at {org.name}',
            })
            changes.append(f'Queued LDAP COM group: {com_name}')

            # Create persongroup with COM naming convention
            pg, pg_created = processor._find_or_create_persongroup(
                com_name, com_name, school_org,
                source_label=f'brso-com:{role.name}',
                group_name_override=com_name)
            if pg:
                pg.write({
                    'has_comgroup': True,
                    'com_group_name': com_name,
                })
                action = 'Created' if pg_created else 'Found'
                changes.append(f'{action} COM persongroup: {pg.name} (ID: {pg.id})')

                # Sync PG-P members
                person_ids = self._get_brso_member_ids(brso_rel)
                if person_ids:
                    result = processor._sync_pg_p_members(pg, person_ids,
                                                          source_label=f'brso-com:{role.name}')
                    changes.append(f'PG-P sync: +{result.get("added", 0)} -{result.get("removed", 0)} members')
            else:
                changes.append(f'WARNING: Could not create COM persongroup for {com_name}')

        # --- Create LDAP SEC group + persongroup ---
        if has_ldap_sec:
            service.create_task('LDAP', 'GROUP', 'ADD', data={
                'group_name': sec_name,
                'org_id': org.id,
                'description': f'SEC group for role {role.name} at {org.name}',
            })
            changes.append(f'Queued LDAP SEC group: {sec_name}')

            # Create persongroup with SEC naming convention
            _logger.info(f'[BRSO-GRP] Creating SEC persongroup: name={sec_name}, school={school_org.name}')
            pg, pg_created = processor._find_or_create_persongroup(
                sec_name, sec_name, school_org,
                source_label=f'brso-sec:{role.name}',
                group_name_override=sec_name)
            _logger.info(f'[BRSO-GRP] _find_or_create_persongroup returned: pg={pg}, created={pg_created}')
            if pg:
                # Ensure correct group fields on persongroup
                pg.write({
                    'has_secgroup': True,
                    'sec_group_name': sec_name,
                    'com_group_name': sec_name,
                })
                _logger.info(f'[BRSO-GRP] Updated persongroup {pg.id}: name={pg.name}, '
                             f'name_short={pg.name_short}, com_group_name={pg.com_group_name}, '
                             f'sec_group_name={pg.sec_group_name}')
                action = 'Created' if pg_created else 'Found'
                changes.append(f'{action} persongroup: {pg.name} (ID: {pg.id})')

                # Sync PG-P members for the persongroup
                person_ids = self._get_brso_member_ids(brso_rel)
                if person_ids:
                    result = processor._sync_pg_p_members(pg, person_ids,
                                                          source_label=f'brso-sec:{role.name}')
                    changes.append(f'PG-P sync: +{result.get("added", 0)} -{result.get("removed", 0)} members')
            else:
                changes.append(f'WARNING: Could not create persongroup for {sec_name}')

        # --- Create Odoo group (using COM naming convention) + persongroup ---
        odoo_group = None
        if has_odoo:
            ResGroups = self.env['res.groups']
            odoo_group = ResGroups.search([('name', '=', com_name)], limit=1)
            if not odoo_group:
                odoo_group = ResGroups.create({'name': com_name})
                changes.append(f'Created Odoo group: {com_name}')
            else:
                changes.append(f'Odoo group already exists: {com_name}')

            # Create persongroup with COM naming convention
            pg, pg_created = processor._find_or_create_persongroup(
                com_name, com_name, school_org,
                source_label=f'brso-odoo:{role.name}',
                group_name_override=com_name)
            if pg:
                pg.write({'has_comgroup': True, 'com_group_name': com_name})
                action = 'Created' if pg_created else 'Found'
                changes.append(f'{action} Odoo persongroup: {pg.name} (ID: {pg.id})')

                person_ids = self._get_brso_member_ids(brso_rel)
                if person_ids:
                    result = processor._sync_pg_p_members(pg, person_ids,
                                                          source_label=f'brso-odoo:{role.name}')
                    changes.append(f'PG-P sync: +{result.get("added", 0)} -{result.get("removed", 0)} members')
            else:
                changes.append(f'WARNING: Could not create Odoo persongroup for {com_name}')

        # --- Add members to groups ---
        person_ids = self._get_brso_member_ids(brso_rel)
        strategy = 'OU-based' if brso_rel.has_accounts else 'role-based'
        if person_ids:
            changes.append(f'Found {len(person_ids)} person(s) ({strategy}) for {org.name}')
            for person_id in person_ids:
                if has_ldap_com:
                    service.create_task('LDAP', 'GROUPMEMBER', 'ADD', data={
                        'group_name': com_name,
                        'person_id': person_id,
                        'org_id': org.id,
                    })
                if has_ldap_sec:
                    service.create_task('LDAP', 'GROUPMEMBER', 'ADD', data={
                        'group_name': sec_name,
                        'person_id': person_id,
                        'org_id': org.id,
                    })
                if has_odoo and odoo_group:
                    task = service.create_task('ODOO', 'GROUPMEMBER', 'ADD', data={
                        'person_id': person_id,
                        'group_id': odoo_group.id,
                    })
                    # Execute immediately and mark completed
                    person = self.env['myschool.person'].browse(person_id)
                    if person.exists() and person.odoo_user_id:
                        person.odoo_user_id.write({'groups_id': [(4, odoo_group.id)]})
                        task.write({'status': 'completed_ok', 'changes': f'Added {person.odoo_user_id.login} to {odoo_group.name}'})
        else:
            changes.append(f'No persons found ({strategy}) for {org.name}')

        # Update org feature flags
        org.update_org_flags()

        return changes

    @api.model
    def _remove_brso_groups(self, brso_rel, flags):
        """Delete groups entirely when has_* flags become false on a BRSO.

        Deletes: persongroup org, LDAP group, Odoo res.groups.
        All via betasks, executed immediately and marked completed.

        Args:
            brso_rel: The BRSO proprelation record.
            flags: Dict of flag names being disabled (e.g. {'has_ldap_com_group': True}).

        Returns:
            List of change description strings.
        """
        changes = []

        org = brso_rel.id_org
        role = brso_rel.id_role
        school_org = brso_rel.id_org_parent
        if not org or not role:
            return changes

        processor = self.env['myschool.betask.processor']
        if school_org:
            school_org = processor._resolve_school_org(school_org)

        com_name = org.com_group_name
        sec_name = org.sec_group_name
        if not com_name and not sec_name:
            return changes

        service = self.env['myschool.betask.service']
        Org = self.env['myschool.org']

        # --- Delete COM group (LDAP + persongroup) ---
        if flags.get('has_ldap_com_group') and com_name:
            # Delete LDAP group
            service.create_task('LDAP', 'GROUP', 'DEL', data={
                'group_name': com_name,
                'org_id': org.id,
            })
            changes.append(f'Queued LDAP COM group deletion: {com_name}')

            # Delete persongroup org
            self._delete_persongroup_by_name(com_name, school_org, changes)

        # --- Delete SEC group (LDAP + persongroup) ---
        if flags.get('has_ldap_sec_group') and sec_name:
            service.create_task('LDAP', 'GROUP', 'DEL', data={
                'group_name': sec_name,
                'org_id': org.id,
            })
            changes.append(f'Queued LDAP SEC group deletion: {sec_name}')

            self._delete_persongroup_by_name(sec_name, school_org, changes)

        # --- Delete Odoo group ---
        if flags.get('has_odoo_group') and com_name:
            odoo_group = self.env['res.groups'].search([('name', '=', com_name)], limit=1)
            if odoo_group:
                # Remove all users from group first
                for user in self.env['res.users'].search([('groups_id', 'in', [odoo_group.id])]):
                    user.write({'groups_id': [(3, odoo_group.id)]})
                task = service.create_task('ODOO', 'GROUP', 'DEL', data={
                    'group_name': com_name,
                    'group_id': odoo_group.id,
                })
                odoo_group.unlink()
                task.write({'status': 'completed_ok', 'changes': f'Deleted Odoo group: {com_name}'})
                changes.append(f'Deleted Odoo group: {com_name}')

            # Also delete the Odoo persongroup if different from COM
            self._delete_persongroup_by_name(com_name, school_org, changes)

        # Update org feature flags
        org.update_org_flags()

        return changes

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
    def _resolve_person_target_org(self, person):
        """Determine the target org for a person's PERSON-TREE based on roles.

        Logic:
        1. Find all active PPSBR for this person
        2. For each PPSBR, find the BRSO with has_accounts=True for that role
        3. If PPSBR.is_master=True → that role's org wins
        4. Otherwise → use role with highest priority
        5. Return the target org (from BRSO.id_org)
        """
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)
        brso_type = PropRelationType.search([('name', '=', 'BRSO')], limit=1)
        if not ppsbr_type or not brso_type:
            return None

        # Find all active PPSBR for this person
        ppsbr_rels = PropRelation.search([
            ('proprelation_type_id', '=', ppsbr_type.id),
            ('id_person', '=', person.id),
            ('is_active', '=', True),
            ('id_role', '!=', False),
        ])
        if not ppsbr_rels:
            return None

        best_org = None
        best_priority = -1

        for ppsbr in ppsbr_rels:
            role = ppsbr.id_role
            school_org = ppsbr.id_org_parent

            # Find BRSO with has_accounts=True for this role+school
            brso = PropRelation.search([
                ('proprelation_type_id', '=', brso_type.id),
                ('id_role', '=', role.id),
                ('id_org_parent', '=', school_org.id) if school_org else ('id_org_parent', '!=', False),
                ('has_accounts', '=', True),
                ('is_active', '=', True),
            ], limit=1)
            if not brso:
                continue

            # IsMaster wins immediately
            if ppsbr.is_master:
                return brso.id_org

            # Otherwise track by role priority
            role_priority = role.priority or 0
            if role_priority > best_priority:
                best_priority = role_priority
                best_org = brso.id_org

        return best_org

    @api.model
    def _update_person_tree_position(self, person):
        """Update a person's PERSON-TREE and FQDN fields based on role assignments.

        Determines target org via _resolve_person_target_org, then:
        - Creates/updates PERSON-TREE proprelation
        - Updates person_fqdn_internal/external
        """
        target_org = self._resolve_person_target_org(person)
        if not target_org:
            return

        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        pt_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        if not pt_type:
            return

        # Find existing active PERSON-TREE
        existing_pt = PropRelation.search([
            ('proprelation_type_id', '=', pt_type.id),
            ('id_person', '=', person.id),
            ('is_active', '=', True),
        ], limit=1)

        if existing_pt and existing_pt.id_org.id == target_org.id:
            # Already in correct position
            pass
        elif existing_pt:
            # Move to new org
            existing_pt.write({'id_org': target_org.id})
            _logger.info(f'[TREE] Moved {person.name} to {target_org.name}')
        else:
            # Create new PERSON-TREE
            service = self.env['myschool.manual.task.service']
            service.create_manual_task('PROPRELATION', 'ADD', {
                'type': 'PERSON-TREE',
                'person_id': person.id,
                'org_id': target_org.id,
            })
            _logger.info(f'[TREE] Created PERSON-TREE for {person.name} at {target_org.name}')

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
        """Update PERSON-TREE for all persons affected by a BRSO with has_accounts=True."""
        if not brso_rel.has_accounts:
            return

        person_ids = self._get_brso_member_ids(brso_rel)
        Person = self.env['myschool.person']
        for pid in person_ids:
            person = Person.browse(pid)
            if person.exists():
                self._update_person_tree_position(person)
