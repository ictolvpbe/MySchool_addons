# -*- coding: utf-8 -*-
"""
ConfigItem Model and Service for Odoo 19
========================================

Converted from Java:
- ConfigItem.java (Entity)
- ConfigItemDao.java (Repository)
- ConfigItemService.java (Interface)
- ConfigItemServiceImpl.java (Implementation)
- ConfigItemRestDto.java (DTO)

@author: Converted to Odoo 19
@version: 0.1
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from typing import List, Optional, Any
import logging

_logger = logging.getLogger(__name__)


class ConfigItem(models.Model):
    """
    Configuration Item model.
    
    Stores configuration parameters that can be associated with
    organizations, roles, persons, or periods via CiRelation.
    
    Equivalent to Java: ConfigItem.java + ConfigItemServiceImpl.java
    """
    _name = 'myschool.config.item'
    _description = 'MySchool Configuration Item'
    _rec_name = 'name'
    _order = 'scope, name'

    # =========================================================================
    # Fields (from ConfigItem.java)
    # =========================================================================

    # Scope: GLOBAL, LOCAL, MODULE, etc.
    scope = fields.Selection([
        ('global', 'Global'),
        ('local', 'Local'),
        ('module', 'Module'),
        ('org', 'Organization'),
        ('user', 'User'),
    ], string="Scope", default='global', index=True,
       help="Defines where this config item is valid: GLOBAL, LOCAL, MODULE, etc.")

    # Type: status, config, setting, parameter, etc.
    type = fields.Selection([
        ('config', 'Configuration'),
        ('status', 'Status'),
        ('setting', 'Setting'),
        ('parameter', 'Parameter'),
        ('credential', 'Credential'),
        ('api', 'API Setting'),
    ], string="Type", default='config', index=True,
       help="Type of configuration item")

    name = fields.Char(
        string="Name", 
        required=True, 
        index=True,
        help="Unique identifier name for this configuration item"
    )

    # Value fields - only one should be used per record
    string_value = fields.Char(
        string="String Value",
        help="String value for this configuration item"
    )
    
    integer_value = fields.Integer(
        string="Integer Value",
        help="Integer value for this configuration item"
    )
    
    boolean_value = fields.Boolean(
        string="Boolean Value",
        help="Boolean value for this configuration item"
    )

    # Additional fields for better management
    description = fields.Text(
        string="Description",
        help="Description of what this configuration item is used for"
    )

    is_active = fields.Boolean(
        string="Active",
        default=True,
        help="Whether this configuration item is currently active"
    )

    is_encrypted = fields.Boolean(
        string="Encrypted",
        default=False,
        help="Whether the string value should be treated as encrypted/sensitive"
    )

    # Inverse relation to CiRelation
    ci_relation_ids = fields.One2many(
        comodel_name='myschool.ci.relation',
        inverse_name='id_ci',
        string="Relations",
        help="Relations linking this config item to orgs, persons, roles, etc."
    )

    # =========================================================================
    # Constraints
    # =========================================================================

    _sql_constraints = [
        ('name_scope_unique', 'UNIQUE(name, scope)', 
         'Configuration item name must be unique within the same scope!'),
    ]

    # =========================================================================
    # CRUD Methods
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to add validation."""
        for vals in vals_list:
            # Ensure at least one value field is set
            if not any([
                vals.get('string_value'),
                vals.get('integer_value'),
                vals.get('boolean_value') is not None
            ]):
                _logger.warning(f"Creating ConfigItem '{vals.get('name')}' without any value set")
        
        return super().create(vals_list)

    # =========================================================================
    # Service Methods (from ConfigItemServiceImpl.java)
    # =========================================================================

    @api.model
    def find_by_id(self, config_id: int) -> Optional['ConfigItem']:
        """
        Find a ConfigItem by ID.
        
        Equivalent to Java: ConfigItemServiceImpl.findById()
        
        @param config_id: ID of the config item
        @return: ConfigItem record or None
        """
        return self.browse(config_id).exists() or None

    @api.model
    def find_by_name(self, name: str) -> 'ConfigItem':
        """
        Find ConfigItems by name.
        
        Equivalent to Java: ConfigItemServiceImpl.findByName()
        
        @param name: Name of the config item
        @return: Recordset of matching ConfigItems
        """
        return self.search([('name', '=', name)])

    @api.model
    def find_all(self) -> 'ConfigItem':
        """
        Find all ConfigItems.
        
        Equivalent to Java: ConfigItemServiceImpl.findAll()
        
        @return: Recordset of all ConfigItems
        """
        return self.search([])

    @api.model
    def register_or_update_config_item(self, vals: dict) -> 'ConfigItem':
        """
        Register a new ConfigItem or update an existing one.
        
        Equivalent to Java: ConfigItemServiceImpl.registerOrUpdateConfigItem()
        
        @param vals: Dictionary with config item values
        @return: Created or updated ConfigItem
        """
        name = vals.get('name')
        if not name:
            raise ValidationError(_("ConfigItem name is required"))
        
        # Check if exists
        existing = self.search([('name', '=', name)], limit=1)
        
        if existing:
            existing.write(vals)
            return existing
        else:
            return self.create(vals)

    @api.model
    def create_config_item_string(self, name: str, value: str) -> Optional['ConfigItem']:
        """
        Create a ConfigItem with a string value.
        
        Equivalent to Java: ConfigItemServiceImpl.createConfigItemString()
        
        @param name: Name of the config item
        @param value: String value
        @return: Created ConfigItem or None on error
        """
        try:
            return self.create({
                'name': name,
                'string_value': value,
                'type': 'config',
                'scope': 'global',
            })
        except Exception as e:
            _logger.error(f"Error creating ConfigItem: {e}")
            return None

    @api.model
    def create_config_item_integer(self, name: str, value: int) -> Optional['ConfigItem']:
        """
        Create a ConfigItem with an integer value.
        
        @param name: Name of the config item
        @param value: Integer value
        @return: Created ConfigItem or None on error
        """
        try:
            return self.create({
                'name': name,
                'integer_value': value,
                'type': 'config',
                'scope': 'global',
            })
        except Exception as e:
            _logger.error(f"Error creating ConfigItem: {e}")
            return None

    @api.model
    def create_config_item_boolean(self, name: str, value: bool) -> Optional['ConfigItem']:
        """
        Create a ConfigItem with a boolean value.
        
        @param name: Name of the config item
        @param value: Boolean value
        @return: Created ConfigItem or None on error
        """
        try:
            return self.create({
                'name': name,
                'boolean_value': value,
                'type': 'config',
                'scope': 'global',
            })
        except Exception as e:
            _logger.error(f"Error creating ConfigItem: {e}")
            return None

    # =========================================================================
    # DAO-style Query Methods (from ConfigItemDao.java)
    # =========================================================================

    @api.model
    def get_ci_value_by_org_and_name(self, org_short_name: str, ci_name: str) -> Optional[str]:
        """
        Get ConfigItem string value by organization short name and CI name.
        
        This method finds the config item linked to a specific organization
        via CiRelation.
        
        Equivalent to Java: ConfigItemDao.getCiValueByOrgShortNameAndCiName()
        
        @param org_short_name: Short name of the organization
        @param ci_name: Name of the config item
        @return: String value or None
        """
        # Find via CiRelation
        CiRelation = self.env.get('myschool.ci.relation')
        ConfigItem = self.env.get('myschool.config.item')
        Org = self.env.get('myschool.org')
        
        # if not CiRelation or not Org:
        #     _logger.warning("CiRelation or Org model not found")
        #     # Fallback: try to find by name only
        #     config_item = self.search([('name', '=', ci_name)], limit=1)
        #     return config_item.string_value if config_item else None
        #
        # config_item = self.search([('name', '=', ci_name)], limit=1)
        # SearchConfigItem = config_item.string_value
        #


        # Find the organization
        org = Org.search([('name_short', '=', org_short_name)], limit=1)
        if not org:
            _logger.warning(f"Organization not found: {org_short_name}")
            return None
        
        # Find the CiRelation linking org and config item
        ci_relation = CiRelation.search([
            ('id_org', '=', org.id),
            ('id_ci.name', '=', ci_name),
            ('isactive', '=', True)
        ], limit=1)
        
        if ci_relation and ci_relation.id_ci:
            return ci_relation.id_ci.string_value
        
        # Fallback: try to find config item by name only  #todo : behouden ??
        config_item = self.search([('name', '=', ci_name)], limit=1)
        return config_item.string_value if config_item else None

    @api.model
    def get_ci_integer_value_by_org_and_name(self, org_short_name: str, ci_name: str) -> Optional[int]:
        """
        Get ConfigItem integer value by organization short name and CI name.
        
        @param org_short_name: Short name of the organization
        @param ci_name: Name of the config item
        @return: Integer value or None
        """
        CiRelation = self.env.get('myschool.ci.relation')
        Org = self.env.get('myschool.org')
        
        if not CiRelation or not Org:
            config_item = self.search([('name', '=', ci_name)], limit=1)
            return config_item.integer_value if config_item else None
        
        org = Org.search([('name_short', '=', org_short_name)], limit=1)
        if not org:
            return None
        
        ci_relation = CiRelation.search([
            ('id_org', '=', org.id),
            ('id_ci.name', '=', ci_name),
            ('isactive', '=', True)
        ], limit=1)
        
        if ci_relation and ci_relation.id_ci:
            return ci_relation.id_ci.integer_value
        
        config_item = self.search([('name', '=', ci_name)], limit=1)
        return config_item.integer_value if config_item else None

    @api.model
    def get_ci_boolean_value_by_org_and_name(self, org_short_name: str, ci_name: str) -> Optional[bool]:
        """
        Get ConfigItem boolean value by organization short name and CI name.
        
        @param org_short_name: Short name of the organization
        @param ci_name: Name of the config item
        @return: Boolean value or None
        """
        CiRelation = self.env.get('myschool.ci.relation')
        Org = self.env.get('myschool.org')
        
        if not CiRelation or not Org:
            config_item = self.search([('name', '=', ci_name)], limit=1)
            return config_item.boolean_value if config_item else None
        
        org = Org.search([('name_short', '=', org_short_name)], limit=1)
        if not org:
            return None
        
        ci_relation = CiRelation.search([
            ('id_org', '=', org.id),
            ('id_ci.name', '=', ci_name),
            ('isactive', '=', True)
        ], limit=1)
        
        if ci_relation and ci_relation.id_ci:
            return ci_relation.id_ci.boolean_value
        
        config_item = self.search([('name', '=', ci_name)], limit=1)
        return config_item.boolean_value if config_item else None

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def get_value(self) -> Any:
        """
        Get the value of this config item (whichever type is set).
        
        @return: The value (string, integer, or boolean)
        """
        self.ensure_one()
        if self.string_value:
            return self.string_value
        elif self.integer_value:
            return self.integer_value
        elif self.boolean_value is not None:
            return self.boolean_value
        return None

    def set_value(self, value: Any) -> None:
        """
        Set the value of this config item based on the type of value provided.
        
        @param value: The value to set
        """
        self.ensure_one()
        if isinstance(value, bool):
            self.write({'boolean_value': value, 'string_value': False, 'integer_value': 0})
        elif isinstance(value, int):
            self.write({'integer_value': value, 'string_value': False, 'boolean_value': False})
        else:
            self.write({'string_value': str(value), 'integer_value': 0, 'boolean_value': False})

    def name_get(self):
        """Custom name display including scope."""
        result = []
        for record in self:
            name = f"[{record.scope or 'global'}] {record.name}"
            result.append((record.id, name))
        return result
