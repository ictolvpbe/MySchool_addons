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

    # ``has_group`` / ``has_accounts`` removed — these were per-role
    # without school context and duplicated state already carried by
    # the target org's ``has_comgroup`` / ``has_accounts`` flags. The
    # cascade now consults BRSO.id_org's flags as the single source of
    # truth. ``has_odoo_group`` (below) stays — it's about which Odoo
    # res.groups a role grants, a separate concern from group sync.

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

    description = fields.Text(
        string='Description',
        help='Description of this role and its permissions'
    )

    # ``has_odoo_group`` / ``odoo_group_ids`` moved to ``myschool.org``.
    # Reason: every group-related concern (LDAP COM, LDAP SEC, Odoo
    # res.groups, accounts) now lives on the org — single source of
    # truth. Migrate via ``Org._migrate_group_flags_from_legacy`` (auto-
    # run by post_init).

    # =========================================================================
    # Constraints
    # =========================================================================

    _shortname_unique = models.Constraint('UNIQUE(shortname)', 'Role short name must be unique!')

    # =========================================================================
    # CRUD Overrides
    # =========================================================================

    def write(self, vals):
        return super().write(vals)

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
    # Persongroup Integration Actions
    # =========================================================================

    def action_sync_persongroup_members(self):
        """Manual action to sync persongroups for this role.

        Creates persongroups (via MANUAL/ORG/ADD betask) for each school
        where this role has a BRSO whose target org has
        ``has_comgroup=True``, and syncs PG-P memberships. The
        ``_sync_role_persongroups`` helper does the per-school filtering
        — no role-level pre-gate any more.
        """
        self.ensure_one()
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

    @api.depends('name', 'label', 'shortname', 'role_type_id', 'is_active')
    def _compute_display_name(self):
        """Custom display name: prefer label over system name."""
        for record in self:
            display = record.label or record.name
            if record.label:
                display = f"{record.label} ({record.name})"
            elif record.shortname and record.shortname != record.name:
                display = f"{record.name} ({record.shortname})"
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
