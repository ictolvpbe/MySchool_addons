# -*- coding: utf-8 -*-
"""
Role Model and Service for Odoo 19
==================================

Role defines the various roles that persons can have in the system,
such as EMPLOYEE, STUDENT, GUARDIAN, TEACHER, etc.

Includes Odoo Group integration for automatic security group assignment.

Converted from Java:
- Role.java (Entity)
- RoleDao.java (Repository)
- RoleService.java (Interface)
- RoleServiceImpl.java (Implementation)

@author: Converted to Odoo 19
@version: 0.2
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from typing import Optional, List, Dict, Any
import logging

_logger = logging.getLogger(__name__)


class Role(models.Model):
    """
    Role model.
    
    Defines roles that can be assigned to persons, such as:
    - EMPLOYEE
    - STUDENT
    - GUARDIAN
    - TEACHER
    - EMPLOYEE_PARTNER
    - EMPLOYEE_CHILD
    
    Includes Odoo Group integration: when has_odoo_group is True and
    odoo_group_id is set, users with this role will automatically be
    added to the specified Odoo security group.
    
    Equivalent to Java: Role.java + RoleServiceImpl.java
    """
    _name = 'myschool.role'
    _description = 'MySchool Role'
    _rec_name = 'name'
    _order = 'priority desc, name'

    # =========================================================================
    # Fields (from Role.java)
    # =========================================================================

    name = fields.Char(
        string='Name',
        required=True,
        index=True,
        help='System name of the role (e.g. EMPLOYEE, STUDENT)'
    )

    label = fields.Char(
        string='Label',
        help='UI-friendly display name for the role (e.g. Medewerker, Leerling)'
    )

    shortname = fields.Char(
        string='Short Name',
        index=True,
        help='Short code for the role (used in SAP systems)'
    )

    # Role Type relation
    role_type_id = fields.Many2one(
        comodel_name='myschool.role.type',
        string='Role Type',
        ondelete='restrict',
        index=True,
        help='Type/category of this role (BACKEND, SAP, UI)'
    )

    role_type_name = fields.Char(
        related='role_type_id.name',
        string='Role Type Name',
        store=True,
        readonly=True
    )

    # Access and permission flags
    has_ui_access = fields.Boolean(
        string='Has UI Access',
        default=True,
        help='Whether this role grants access to the user interface'
    )

    has_group = fields.Boolean(
        string='Has Group',
        default=False,
        help='Whether this role requires Org creation per School'
    )

    has_accounts = fields.Boolean(
        string='Has Accounts',
        default=False,
        help='Whether this role requires account creation'
    )

    # Priority for account creation (highest priority role determines the account)
    priority = fields.Integer(
        string='Priority',
        default=0,
        help='Priority determines which role is used for account creation in AD. '
             'Highest priority wins. Also used for PERSON-TREE placement (lowest = highest priority).'
    )

    is_active = fields.Boolean(
        string='Active',
        default=True,
        index=True,
        help='Whether this role is currently active'
    )

    automatic_sync = fields.Boolean(
        string='Automatic Sync',
        default=True,
        help='Whether this role should be automatically synchronized'
    )

    # Legacy field for migration
    old_id = fields.Char(
        string='Old ID',
        help='ID from legacy system for migration purposes'
    )

    description = fields.Text(
        string='Description',
        help='Description of this role and its permissions'
    )

    # =========================================================================
    # ODOO GROUP INTEGRATION FIELDS
    # =========================================================================
    
    has_odoo_group = fields.Boolean(
        string='Has Odoo Groups',
        default=False,
        help='If enabled, employees with this role will be added to the linked Odoo security groups'
    )

    odoo_group_ids = fields.Many2many(
        'res.groups',
        'myschool_role_odoo_groups_rel',
        'role_id', 'group_id',
        string='Odoo Groups',
        domain="[('privilege_id', '!=', False)]",
        help='Odoo security groups linked to this role. '
             'Employees with this role will be added to all these groups.'
    )
    odoo_group_display = fields.Char(
        string='Toegewezen groepen',
        compute='_compute_odoo_group_display',
    )

    @api.depends('odoo_group_ids')
    def _compute_odoo_group_display(self):
        for record in self:
            if not record.odoo_group_ids:
                record.odoo_group_display = ''
                continue
            parts = []
            for group in record.odoo_group_ids:
                category = group.privilege_id.category_id.name if group.privilege_id and group.privilege_id.category_id else ''
                parts.append(f"{category} → {group.name}" if category else group.name)
            record.odoo_group_display = ', '.join(parts)

    # =========================================================================
    # Constraints
    # =========================================================================

    _shortname_unique = models.Constraint('UNIQUE(shortname)', 'Role short name must be unique!')

    @api.constrains('has_odoo_group', 'odoo_group_ids')
    def _check_odoo_group_consistency(self):
        """Warn if has_odoo_group is True but no groups are set."""
        for record in self:
            if record.has_odoo_group and not record.odoo_group_ids:
                _logger.warning(
                    f'Role {record.name} has has_odoo_group=True but no odoo_group_ids set'
                )

    # =========================================================================
    # Onchange Methods
    # =========================================================================
    
    @api.onchange('has_odoo_group')
    def _onchange_has_odoo_group(self):
        """Clear odoo_group_ids when has_odoo_group is disabled."""
        if not self.has_odoo_group:
            self.odoo_group_ids = [(5, 0, 0)]

    @api.onchange('odoo_group_ids')
    def _onchange_odoo_group_ids(self):
        """Set has_odoo_group when groups are selected."""
        if self.odoo_group_ids:
            self.has_odoo_group = True

    # =========================================================================
    # CRUD Overrides
    # =========================================================================

    def write(self, vals):
        result = super().write(vals)
        if vals.get('has_group'):
            processor = self.env['myschool.betask.processor']
            for role in self:
                try:
                    processor._sync_role_persongroups(role)
                except Exception as e:
                    _logger.warning(f'[PG-SYNC] Failed to sync persongroups for role {role.name}: {e}')
        return result

    # =========================================================================
    # Service Methods (from RoleServiceImpl.java)
    # =========================================================================

    @api.model
    def find_by_id(self, role_id: int) -> Optional['Role']:
        """
        Find a Role by ID.
        
        Equivalent to Java: RoleDao.findRoleById()
        
        @param role_id: ID of the role
        @return: Role record or None
        """
        record = self.browse(role_id)
        return record if record.exists() else None

    @api.model
    def find_by_name(self, name: str) -> Optional['Role']:
        """
        Find a Role by name.
        
        Equivalent to Java: RoleDao.findRoleByName()
        
        @param name: Name of the role
        @return: Role record or None
        """
        return self.search([('name', '=', name)], limit=1) or None

    @api.model
    def find_roles_by_name(self, name: str) -> 'Role':
        """
        Find all Roles matching a name.
        
        Equivalent to Java: RoleDao.findRolesByName()
        
        @param name: Name to search for
        @return: Recordset of matching Roles
        """
        return self.search([('name', '=', name)])

    @api.model
    def find_by_shortname(self, shortname: str) -> Optional['Role']:
        """
        Find a Role by short name.
        
        Equivalent to Java: RoleDao.findRoleByShortname()
        
        @param shortname: Short name of the role
        @return: Role record or None
        """
        return self.search([('shortname', '=', shortname)], limit=1) or None

    @api.model
    def find_roles_by_shortname(self, shortname: str) -> 'Role':
        """
        Find all Roles matching a short name.
        
        Equivalent to Java: RoleDao.findRolesByShortname()
        
        @param shortname: Short name to search for
        @return: Recordset of matching Roles
        """
        return self.search([('shortname', '=', shortname)])

    @api.model
    def find_all(self) -> 'Role':
        """
        Find all Roles.
        
        Equivalent to Java: RoleServiceImpl.findAll()
        
        @return: Recordset of all Roles
        """
        return self.search([])

    @api.model
    def find_all_active(self) -> 'Role':
        """
        Find all active Roles.
        
        @return: Recordset of active Roles
        """
        return self.search([('is_active', '=', True)])

    @api.model
    def find_all_by_role_type_and_active(self, role_type_name: str, is_active: bool = True) -> 'Role':
        """
        Find all Roles by role type name and active status.
        
        Equivalent to Java: RoleDao.findAllByRoletype_NameAndIsactive()
        
        @param role_type_name: Name of the role type
        @param is_active: Active status filter
        @return: Recordset of matching Roles
        """
        return self.search([
            ('role_type_id.name', '=', role_type_name),
            ('is_active', '=', is_active)
        ])

    @api.model
    def find_all_with_odoo_group(self) -> 'Role':
        """
        Find all Roles that have Odoo groups configured.

        @return: Recordset of Roles with Odoo groups
        """
        return self.search([
            ('has_odoo_group', '=', True),
            ('odoo_group_ids', '!=', False),
            ('is_active', '=', True)
        ])

    def delete(self) -> bool:
        """
        Delete this Role.
        
        Equivalent to Java: RoleServiceImpl.delete()
        
        @return: True if deleted
        """
        self.ensure_one()
        # Check if role is used in any relations
        PropRelation = self.env.get('myschool.proprelation')
        if PropRelation:
            relations = PropRelation.search([('id_role', '=', self.id)], limit=1)
            if relations:
                raise UserError(_("Cannot delete role '%s' because it is used in relations.") % self.name)
        
        self.unlink()
        return True

    @api.model
    def register_or_update_role(self, vals: dict) -> 'Role':
        """
        Register a new Role or update an existing one.
        
        @param vals: Dictionary with role values
        @return: Created or updated Role
        """
        shortname = vals.get('shortname') or vals.get('sapRoleShortName')
        if not shortname:
            raise ValidationError(_("Role shortname is required"))

        existing = self.search([('shortname', '=', shortname)], limit=1)
        
        if existing:
            existing.write(vals)
            return existing
        else:
            return self.create(vals)

    # =========================================================================
    # Odoo Group Integration Actions
    # =========================================================================

    def action_sync_group_members(self):
        """
        Manual action to sync all employees with this role to the Odoo groups.
        Can be called from a button in the form view.
        """
        self.ensure_one()

        if not self.has_odoo_group or not self.odoo_group_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'Deze rol heeft geen Odoo groepen geconfigureerd.',
                    'type': 'info',
                }
            }

        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        ppsbr_type = PropRelationType.search([('name', '=', 'PPSBR')], limit=1)

        if not ppsbr_type:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Fout',
                    'message': 'PPSBR PropRelationType niet gevonden.',
                    'type': 'danger',
                }
            }

        ppsbr_records = PropRelation.search([
            ('id_role', '=', self.id),
            ('proprelation_type_id', '=', ppsbr_type.id),
            ('is_active', '=', True),
            ('id_person', '!=', False)
        ])

        added_count = 0
        for ppsbr in ppsbr_records:
            person = ppsbr.id_person
            if person and person.odoo_user_id:
                user = person.odoo_user_id
                for group in self.odoo_group_ids:
                    if group not in user.group_ids:
                        user.write({'group_ids': [(4, group.id)]})
                        added_count += 1

        group_names = ', '.join(self.odoo_group_ids.mapped('full_name'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Succes',
                'message': f'{added_count} groepstoewijzingen toegevoegd ({group_names}).',
                'type': 'success',
            }
        }
    
    def action_view_group_members(self):
        """Action to view all users in the linked Odoo groups."""
        self.ensure_one()

        if not self.odoo_group_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'Geen Odoo groepen gekoppeld aan deze rol.',
                    'type': 'info',
                }
            }

        return {
            'type': 'ir.actions.act_window',
            'name': f'Gebruikers met rol {self.name}',
            'res_model': 'res.users',
            'view_mode': 'tree,form',
            'domain': [('group_ids', 'in', self.odoo_group_ids.ids)],
            'target': 'current',
        }

    def action_remove_all_group_members(self):
        """
        Remove all users from this role's Odoo groups.
        Use with caution!
        """
        self.ensure_one()

        if not self.has_odoo_group or not self.odoo_group_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'Deze rol heeft geen Odoo groepen geconfigureerd.',
                    'type': 'info',
                }
            }

        removed_count = 0
        for group in self.odoo_group_ids:
            users_in_group = self.env['res.users'].search([
                ('group_ids', 'in', [group.id])
            ])
            for user in users_in_group:
                user.write({'group_ids': [(3, group.id)]})
                removed_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Succes',
                'message': f'{removed_count} groepstoewijzingen verwijderd.',
                'type': 'success',
            }
        }

    # =========================================================================
    # Persongroup Integration Actions
    # =========================================================================

    def action_sync_persongroup_members(self):
        """Manual action to sync persongroups for this role.

        Creates persongroups (via MANUAL/ORG/ADD betask) for each school
        where this role has a BRSO, and syncs PG-P memberships.
        """
        self.ensure_one()

        if not self.has_group:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Info',
                    'message': 'Has Group is not enabled for this role.',
                    'type': 'info',
                },
            }

        processor = self.env['myschool.betask.processor']
        try:
            processor._sync_role_persongroups(self)
        except Exception as e:
            _logger.warning(f'[PG-SYNC] Failed to sync persongroups for role {self.name}: {e}')
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Failed to sync persongroups: {e}',
                    'type': 'danger',
                },
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Persongroups synced for role {self.name}.',
                'type': 'success',
            },
        }

    # =========================================================================
    # Person Role Methods (from RoleServiceImpl.java)
    # =========================================================================

    @api.model
    def find_roles_by_person(self, person_id: int, exclude_roles: List[str] = None) -> 'Role':
        """
        Find all Roles assigned to a Person.
        
        Equivalent to Java: RoleServiceImpl.findRolesByIdPerson()
        
        @param person_id: ID of the person
        @param exclude_roles: List of role names to exclude (e.g., ['EMPLOYEE_CHILD'])
        @return: Recordset of Roles
        """
        PropRelation = self.env.get('myschool.proprelation')
        if not PropRelation:
            _logger.warning("PropRelation model not found")
            return self.browse()
        
        # Default exclusions from Java code
        if exclude_roles is None:
            exclude_roles = ['EMPLOYEE_CHILD']
        
        # Find prop relations for this person
        domain = [('id_person', '=', person_id)]
        if exclude_roles:
            excluded_role_ids = self.search([('name', 'in', exclude_roles)]).ids
            if excluded_role_ids:
                domain.append(('id_role', 'not in', excluded_role_ids))
        
        prop_relations = PropRelation.search(domain)
        
        # Extract unique roles
        role_ids = list(set(prop_relations.mapped('id_role').ids))
        return self.browse(role_ids)

    @api.model
    def find_employee_roles_by_person(self, person_id: int) -> Dict[int, int]:
        """
        Find employee Roles and their associated Orgs for a Person.
        
        Equivalent to Java: RoleServiceImpl.findEmployeeRolesByIdPerson()
        
        Excludes: GUARDIAN, EMPLOYEE_PARTNER, EMPLOYEE_CHILD, STUDENT
        
        @param person_id: ID of the person
        @return: Dictionary mapping role_id -> org_id
        """
        PropRelation = self.env.get('myschool.proprelation')
        if not PropRelation:
            _logger.warning("PropRelation model not found")
            return {}
        
        # Roles to exclude (from Java code)
        exclude_role_names = ['GUARDIAN', 'EMPLOYEE_PARTNER', 'EMPLOYEE_CHILD', 'STUDENT']
        excluded_roles = self.search([('name', 'in', exclude_role_names)])
        excluded_role_ids = excluded_roles.ids
        
        # Find prop relations for this person, excluding certain roles
        domain = [('id_person', '=', person_id)]
        if excluded_role_ids:
            domain.append(('id_role', 'not in', excluded_role_ids))
        
        prop_relations = PropRelation.search(domain)
        
        # Build role -> org mapping
        result = {}
        for pr in prop_relations:
            if pr.id_role and pr.id_org:
                result[pr.id_role.id] = pr.id_org.id
        
        return result

    @api.model
    def find_employee_backend_roles_by_person(self, person_id: int) -> Dict[int, int]:
        """
        Find backend Roles for an employee Person.
        
        Equivalent to Java: RoleServiceImpl.findEmployeeBackEndRolesByIdPerson()
        
        For SAP roles, finds the related BACKEND role type parent.
        
        @param person_id: ID of the person
        @return: Dictionary mapping role_id -> org_id for BACKEND roles
        """
        PropRelation = self.env.get('myschool.proprelation')
        RoleType = self.env.get('myschool.role.type')
        
        if not PropRelation or not RoleType:
            _logger.warning("PropRelation or RoleType model not found")
            return {}
        
        # Get role types
        backend_role_type = RoleType.search([('name', '=', 'BACKEND')], limit=1)
        sap_role_type = RoleType.search([('name', '=', 'SAP')], limit=1)
        
        if not backend_role_type or not sap_role_type:
            _logger.warning("BACKEND or SAP role type not found")
            return {}
        
        # Get employee roles
        employee_roles = self.find_employee_roles_by_person(person_id)
        
        result = {}
        for role_id, org_id in employee_roles.items():
            role = self.browse(role_id)
            
            # If this is a SAP role, find the related BACKEND parent role
            if role.role_type_id.id == sap_role_type.id:
                # Find parent role relation
                parent_relations = PropRelation.search([
                    ('id_role', '=', role_id),
                    ('id_role_parent', '!=', False),
                    ('id_role_parent.role_type_id', '=', backend_role_type.id),
                    ('is_active', '=', True)
                ], limit=1)
                
                if parent_relations:
                    parent_role = parent_relations.id_role_parent
                    parent_org = parent_relations.id_org
                    if parent_role and parent_org:
                        result[parent_role.id] = parent_org.id
        
        return result

    @api.model
    def get_roles_with_orgs_for_person(self, person_id: int) -> List[Dict[str, Any]]:
        """
        Get detailed role and org information for a person.
        
        @param person_id: ID of the person
        @return: List of dicts with role and org details
        """
        role_org_map = self.find_employee_roles_by_person(person_id)
        
        result = []
        Org = self.env.get('myschool.org')
        
        for role_id, org_id in role_org_map.items():
            role = self.browse(role_id)
            org = Org.browse(org_id) if Org else None
            
            result.append({
                'role_id': role_id,
                'role_name': role.name,
                'role_shortname': role.shortname,
                'role_type': role.role_type_id.name if role.role_type_id else None,
                'has_odoo_group': role.has_odoo_group,
                'odoo_group_names': role.odoo_group_ids.mapped('full_name') if role.odoo_group_ids else [],
                'org_id': org_id,
                'org_name': org.name if org else None,
                'org_short_name': org.name_short if org and hasattr(org, 'name_short') else None,
            })
        
        return result

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def activate(self):
        """Activate this role."""
        self.write({'is_active': True})

    def deactivate(self):
        """Deactivate this role."""
        self.write({'is_active': False})

    @api.depends('name', 'label', 'shortname', 'role_type_id', 'has_odoo_group', 'is_active')
    def _compute_display_name(self):
        """Custom display name: prefer label over system name."""
        for record in self:
            display = record.label or record.name
            if record.label:
                display = f"{record.label} ({record.name})"
            elif record.shortname and record.shortname != record.name:
                display = f"{record.name} ({record.shortname})"
            if record.has_odoo_group:
                display = f"{display} 🔐"
            if not record.is_active:
                display = f"{display} [Inactive]"
            record.display_name = display

    @api.model
    def _name_search(self, name='', domain=None, operator='ilike', limit=100, order=None):
        """Allow searching by label in Many2one dropdowns."""
        domain = domain or []
        if name:
            domain = ['|', '|',
                       ('name', operator, name),
                       ('label', operator, name),
                       ('shortname', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)

    @api.model
    def get_exclude_roles_for_employee(self) -> 'Role':
        """
        Get roles that should be excluded when finding employee roles.
        
        @return: Recordset of roles to exclude
        """
        exclude_names = ['GUARDIAN', 'EMPLOYEE_PARTNER', 'EMPLOYEE_CHILD', 'STUDENT']
        return self.search([('name', 'in', exclude_names)])
