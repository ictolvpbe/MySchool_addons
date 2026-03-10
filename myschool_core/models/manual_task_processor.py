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

        person.write({'is_active': False})
        changes.append(f"Deactivated person: {person_name}")

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

        person.unlink()
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

        # Build name
        proprel_vals['name'] = _build_proprelation_name(rel_type_name, **name_kwargs)

        PropRelation.create(proprel_vals)
        return {'success': True, 'changes': f"Created {rel_type_name} relation: {proprel_vals['name']}"}

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

        # Mode 1: explicit IDs
        proprelation_ids = data.get('proprelation_ids')
        if proprelation_ids:
            rels = PropRelation.browse(proprelation_ids).exists()
            if rels:
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
                changes.append(f"Deactivated {len(rels)} {rel_type_name} relation(s) for person {person_id} in org {org_id}")

        if not changes:
            return {'success': False, 'error': 'No proprelations found to deactivate'}

        return {'success': True, 'changes': '\n'.join(changes)}
