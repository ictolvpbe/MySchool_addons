# -*- coding: utf-8 -*-
"""
RoleType Model and Service for Odoo 19
======================================

RoleType defines categories of roles such as:
- BACKEND: Backend system roles
- SAP: SAP system roles
- UI: User interface roles

Converted from Java:
- RoleType.java (Entity)
- RoleTypeDao.java (Repository)
- RoleTypeService.java (Interface)
- RoleTypeServiceImpl.java (Implementation)

@author: Converted to Odoo 19
@version: 0.1
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from typing import Optional, List
import logging

_logger = logging.getLogger(__name__)


class RoleType(models.Model):
    """
    Role Type model.
    
    Categorizes roles into types such as BACKEND, SAP, UI, etc.
    
    Equivalent to Java: RoleType.java + RoleTypeServiceImpl.java
    """
    _name = 'myschool.role.type'
    _description = 'MySchool Role Type'
    _rec_name = 'name'
    _order = 'name'

    # =========================================================================
    # Fields (from RoleType.java)
    # =========================================================================

    name = fields.Char(
        string='Name',
        required=True,
        index=True,
        help="Name of the role type (e.g., BACKEND, SAP, UI)"
    )

    shortname = fields.Char(
        string='Short Name',
        size=50,
        index=True,
        help="Short abbreviation for the role type"
    )

    is_active = fields.Boolean(
        string='Active',
        default=True,
        index=True,
        help="Whether this role type is currently active"
    )

    description = fields.Text(
        string='Description',
        help="Description of this role type"
    )

    # Inverse relation to roles
    role_ids = fields.One2many(
        comodel_name='myschool.role',
        inverse_name='role_type_id',
        string='Roles',
        help="Roles of this type"
    )

    role_count = fields.Integer(
        string='Role Count',
        compute='_compute_role_count',
        store=True
    )

    # =========================================================================
    # Computed Fields
    # =========================================================================

    @api.depends('role_ids')
    def _compute_role_count(self):
        """Compute the number of roles of this type."""
        for record in self:
            record.role_count = len(record.role_ids)

    # =========================================================================
    # Constraints
    # =========================================================================

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Role type name must be unique!'),
        ('shortname_unique', 'UNIQUE(shortname)', 'Role type short name must be unique!'),
    ]

    # =========================================================================
    # Service Methods (from RoleTypeServiceImpl.java)
    # =========================================================================

    @api.model
    def find_by_id(self, role_type_id: int) -> Optional['RoleType']:
        """
        Find a RoleType by ID.
        
        Equivalent to Java: RoleTypeDao.findRoleTypeById()
        
        @param role_type_id: ID of the role type
        @return: RoleType record or None
        """
        record = self.browse(role_type_id)
        return record if record.exists() else None

    @api.model
    def find_by_name(self, name: str) -> Optional['RoleType']:
        """
        Find a RoleType by name.
        
        Equivalent to Java: RoleTypeServiceImpl.findByName() / findRoleTypeByName()
        
        @param name: Name of the role type
        @return: RoleType record or None
        """
        return self.search([('name', '=', name)], limit=1) or None

    @api.model
    def find_role_type_by_name(self, name: str) -> Optional['RoleType']:
        """
        Find a RoleType by name (alias for find_by_name).
        
        Equivalent to Java: RoleTypeDao.findRoleTypeByName()
        
        @param name: Name of the role type
        @return: RoleType record or None
        """
        return self.find_by_name(name)

    @api.model
    def find_role_types_by_name(self, name: str) -> 'RoleType':
        """
        Find all RoleTypes matching a name (may return multiple).
        
        Equivalent to Java: RoleTypeDao.findRoleTypesByName()
        
        @param name: Name to search for
        @return: Recordset of matching RoleTypes
        """
        return self.search([('name', '=', name)])

    @api.model
    def find_all(self) -> 'RoleType':
        """
        Find all RoleTypes.
        
        Equivalent to Java: RoleTypeServiceImpl.findAll()
        
        @return: Recordset of all RoleTypes
        """
        return self.search([])

    @api.model
    def find_all_active(self) -> 'RoleType':
        """
        Find all active RoleTypes.
        
        @return: Recordset of active RoleTypes
        """
        return self.search([('is_active', '=', True)])

    def delete(self) -> bool:
        """
        Delete this RoleType.
        
        Equivalent to Java: RoleTypeServiceImpl.delete()
        
        @return: True if deleted
        """
        self.ensure_one()
        if self.role_ids:
            raise UserError(_("Cannot delete role type '%s' because it has associated roles.") % self.name)
        self.unlink()
        return True

    @api.model
    def register_or_update_role_type(self, vals: dict) -> 'RoleType':
        """
        Register a new RoleType or update an existing one.
        
        @param vals: Dictionary with role type values
        @return: Created or updated RoleType
        """
        name = vals.get('name')
        if not name:
            raise ValidationError(_("RoleType name is required"))
        
        existing = self.search([('name', '=', name)], limit=1)
        
        if existing:
            existing.write(vals)
            return existing
        else:
            return self.create(vals)

    @api.model
    def create_role_type(self, name: str, shortname: str = None) -> Optional['RoleType']:
        """
        Create a new RoleType.
        
        @param name: Name of the role type
        @param shortname: Short name (optional)
        @return: Created RoleType or None on error
        """
        try:
            return self.create({
                'name': name,
                'shortname': shortname or name[:50],
                'is_active': True,
            })
        except Exception as e:
            _logger.error(f"Error creating RoleType: {e}")
            return None

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def activate(self):
        """Activate this role type."""
        self.write({'is_active': True})

    def deactivate(self):
        """Deactivate this role type."""
        self.write({'is_active': False})

    def name_get(self):
        """Custom name display including active status."""
        result = []
        for record in self:
            name = record.name
            if record.shortname:
                name = f"{record.name} ({record.shortname})"
            if not record.is_active:
                name = f"{name} [Inactive]"
            result.append((record.id, name))
        return result
