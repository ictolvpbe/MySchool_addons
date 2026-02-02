# -*- coding: utf-8 -*-
"""
CiRelation Model and Service for Odoo 19
========================================

CiRelation links ConfigItems to other entities (Org, Person, Role, Period).
This allows configuration items to have different values per organization,
person, role, or period.

Converted from Java:
- CiRelation.java (Entity)
- CiRelationDao.java (Repository)
- CiRelationService.java (Interface)
- CiRelationServiceImpl.java (Implementation)

@author: Converted to Odoo 19
@version: 0.1
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from typing import Optional, List
import logging

_logger = logging.getLogger(__name__)


class CiRelation(models.Model):
    """
    Configuration Item Relation model.
    
    Links ConfigItems to organizations, persons, roles, and periods.
    This enables context-specific configuration values.
    
    Equivalent to Java: CiRelation.java + CiRelationServiceImpl.java
    """
    _name = 'myschool.ci.relation'
    _description = 'MySchool Configuration Item Relation'
    _rec_name = 'name'
    _order = 'name'

    # =========================================================================
    # Fields (from CiRelation.java)
    # =========================================================================

    name = fields.Char(
        string="Name",
        compute='_compute_name',
        store=True,
        readonly=False,
        help="Auto-generated name based on linked entities"
    )

    isactive = fields.Boolean(
        string="Is Active",
        default=True,
        index=True,
        help="Whether this relation is currently active"
    )

    automatic_sync = fields.Boolean(
        string="Automatic Sync",
        default=False,
        help="Whether this relation should be automatically synchronized"
    )

    # Many2one relations to other entities
    id_ci = fields.Many2one(
        comodel_name='myschool.config.item',
        string="Config Item",
        ondelete='cascade',
        index=True,
        help="The configuration item this relation links to"
    )

    id_role = fields.Many2one(
        comodel_name='myschool.role',
        string="Role",
        ondelete='set null',
        index=True,
        help="Role this config item applies to"
    )

    id_org = fields.Many2one(
        comodel_name='myschool.org',
        string="Organization",
        ondelete='set null',
        index=True,
        help="Organization this config item applies to"
    )

    id_person = fields.Many2one(
        comodel_name='myschool.person',
        string="Person",
        ondelete='set null',
        index=True,
        help="Person this config item applies to"
    )

    id_period = fields.Many2one(
        comodel_name='myschool.period',
        string="Period",
        ondelete='set null',
        index=True,
        help="Period this config item applies to"
    )

    # id_sysmodule = fields.Many2one(
    #     comodel_name='myschool.sys.module',
    #     string="System Module",
    #     ondelete='set null',
    #     index=True,
    #     help="System module this config item applies to"
    # )

    # =========================================================================
    # Related fields for easy access
    # =========================================================================

    ci_name = fields.Char(
        related='id_ci.name',
        string="Config Item Name",
        store=True,
        readonly=True
    )

    ci_string_value = fields.Char(
        related='id_ci.string_value',
        string="String Value",
        readonly=True
    )

    ci_integer_value = fields.Integer(
        related='id_ci.integer_value',
        string="Integer Value",
        readonly=True
    )

    ci_boolean_value = fields.Boolean(
        related='id_ci.boolean_value',
        string="Boolean Value",
        readonly=True
    )

    org_name = fields.Char(
        related='id_org.name_short',
        string="Org Short Name",
        store=True,
        readonly=True
    )

    # =========================================================================
    # Computed Fields
    # =========================================================================

    @api.depends('id_ci', 'id_person', 'id_role', 'id_org', 'id_period')
    def _compute_name(self):
        """
        Compute the name based on linked entities.

        Equivalent to Java: CiRelationServiceImpl.registerOrUpdateCiRelation()
        Format: CI=name.Pn=name-firstname.Ro=name.Or=name_tree.Pd=name
        """
        for record in self:
            name_parts = []

            if record.id_ci:
                name_parts.append(f"CI={record.id_ci.name}")

            if record.id_person:
                person_name = f"{record.id_person.name or ''}"
                if hasattr(record.id_person, 'first_name') and record.id_person.first_name:
                    person_name += f"-{record.id_person.first_name}"
                elif hasattr(record.id_person, 'firstname') and record.id_person.firstname:
                    person_name += f"-{record.id_person.firstname}"
                name_parts.append(f"Pn={person_name}")

            if record.id_role:
                name_parts.append(f"Ro={record.id_role.name or ''}")

            if record.id_org:
                # Use name_tree for org identification (e.g., "int.olvp.bawa")
                org_name = record.id_org.name_tree if hasattr(record.id_org, 'name_tree') and record.id_org.name_tree else record.id_org.name
                name_parts.append(f"Or={org_name or ''}")

            if record.id_period:
                name_parts.append(f"Pd={record.id_period.name or ''}")

            # if record.id_sysmodule:
            #     name_parts.append(f"Sm={record.id_sysmodule.name or ''}")

            record.name = '.'.join(name_parts) if name_parts else 'New Relation'

    # =========================================================================
    # Constraints
    # =========================================================================

    @api.constrains('id_ci')
    def _check_config_item(self):
        """Ensure a config item is always linked."""
        for record in self:
            if not record.id_ci:
                raise ValidationError(_("A Configuration Item must be specified."))

    # =========================================================================
    # Service Methods (from CiRelationServiceImpl.java)
    # =========================================================================

    @api.model
    def find_by_id(self, relation_id: int) -> Optional['CiRelation']:
        """
        Find a CiRelation by ID.
        
        Equivalent to Java: CiRelationServiceImpl.findById()
        
        @param relation_id: ID of the relation
        @return: CiRelation record or None
        """
        record = self.browse(relation_id)
        return record if record.exists() else None

    @api.model
    def find_by_name(self, name: str) -> Optional['CiRelation']:
        """
        Find a CiRelation by name.
        
        Equivalent to Java: CiRelationServiceImpl.findByName()
        
        @param name: Name of the relation
        @return: CiRelation record or None
        """
        return self.search([('name', '=', name)], limit=1) or None

    @api.model
    def find_all(self) -> 'CiRelation':
        """
        Find all CiRelations.
        
        Equivalent to Java: CiRelationServiceImpl.findAll()
        
        @return: Recordset of all CiRelations
        """
        return self.search([])

    @api.model
    def register_or_update_ci_relation(self, vals: dict) -> 'CiRelation':
        """
        Register a new CiRelation or update an existing one.
        The name is automatically computed.
        
        Equivalent to Java: CiRelationServiceImpl.registerOrUpdateCiRelation()
        
        @param vals: Dictionary with relation values
        @return: Created or updated CiRelation
        """
        # If ID provided, update existing
        if vals.get('id'):
            existing = self.browse(vals['id'])
            if existing.exists():
                existing.write(vals)
                return existing
        
        # Create new
        return self.create(vals)

    @api.model
    def create_ci_relation(self) -> 'CiRelation':
        """
        Create an empty CiRelation (for later configuration).
        
        Equivalent to Java: CiRelationServiceImpl.createCiRelation()
        
        @return: Created CiRelation
        """
        return self.create({
            'isactive': True,
            'automatic_sync': False,
        })

    @api.model
    def create_ci_relation_org_config_item(self, org_id: int, config_item_id: int) -> Optional['CiRelation']:
        """
        Create a CiRelation linking an Organization to a ConfigItem.
        
        Equivalent to Java: CiRelationServiceImpl.createCiRelationOrgConfigItem()
        
        @param org_id: ID of the Organization
        @param config_item_id: ID of the ConfigItem
        @return: Created CiRelation or None on error
        """
        try:
            return self.create({
                'id_org': org_id,
                'id_ci': config_item_id,
                'isactive': True,
                'automatic_sync': False,
            })
        except Exception as e:
            _logger.error(f"Error creating CiRelation: {e}")
            return None

    @api.model
    def create_ci_relation_person_config_item(self, person_id: int, config_item_id: int) -> Optional['CiRelation']:
        """
        Create a CiRelation linking a Person to a ConfigItem.
        
        @param person_id: ID of the Person
        @param config_item_id: ID of the ConfigItem
        @return: Created CiRelation or None on error
        """
        try:
            return self.create({
                'id_person': person_id,
                'id_ci': config_item_id,
                'isactive': True,
                'automatic_sync': False,
            })
        except Exception as e:
            _logger.error(f"Error creating CiRelation: {e}")
            return None

    @api.model
    def create_ci_relation_role_config_item(self, role_id: int, config_item_id: int) -> Optional['CiRelation']:
        """
        Create a CiRelation linking a Role to a ConfigItem.
        
        @param role_id: ID of the Role
        @param config_item_id: ID of the ConfigItem
        @return: Created CiRelation or None on error
        """
        try:
            return self.create({
                'id_role': role_id,
                'id_ci': config_item_id,
                'isactive': True,
                'automatic_sync': False,
            })
        except Exception as e:
            _logger.error(f"Error creating CiRelation: {e}")
            return None

    @api.model
    def create_ci_relation_period_config_item(self, period_id: int, config_item_id: int) -> Optional['CiRelation']:
        """
        Create a CiRelation linking a Period to a ConfigItem.
        
        @param period_id: ID of the Period
        @param config_item_id: ID of the ConfigItem
        @return: Created CiRelation or None on error
        """
        try:
            return self.create({
                'id_period': period_id,
                'id_ci': config_item_id,
                'isactive': True,
                'automatic_sync': False,
            })
        except Exception as e:
            _logger.error(f"Error creating CiRelation: {e}")
            return None

    # =========================================================================
    # DAO-style Query Methods (from CiRelationDao.java)
    # =========================================================================

    @api.model
    def find_ci_relation_by_org(self, org_id: int) -> Optional['CiRelation']:
        """
        Find CiRelation by Organization.
        
        Equivalent to Java: CiRelationDao.findCiRelationByIdOrg()
        
        @param org_id: ID of the Organization
        @return: CiRelation or None
        """
        return self.search([('id_org', '=', org_id), ('isactive', '=', True)], limit=1) or None

    @api.model
    def find_ci_relations_by_org(self, org_id: int) -> 'CiRelation':
        """
        Find all CiRelations for an Organization.
        
        @param org_id: ID of the Organization
        @return: Recordset of CiRelations
        """
        return self.search([('id_org', '=', org_id), ('isactive', '=', True)])

    @api.model
    def find_ci_relation_by_period(self, period_id: int) -> Optional['CiRelation']:
        """
        Find CiRelation by Period.
        
        Equivalent to Java: CiRelationDao.findCiRelationByIdPeriod()
        
        @param period_id: ID of the Period
        @return: CiRelation or None
        """
        return self.search([('id_period', '=', period_id), ('isactive', '=', True)], limit=1) or None

    @api.model
    def find_ci_relations_by_period(self, period_id: int) -> 'CiRelation':
        """
        Find all CiRelations for a Period.
        
        @param period_id: ID of the Period
        @return: Recordset of CiRelations
        """
        return self.search([('id_period', '=', period_id), ('isactive', '=', True)])

    @api.model
    def find_ci_relation_by_person(self, person_id: int) -> Optional['CiRelation']:
        """
        Find CiRelation by Person.
        
        Equivalent to Java: CiRelationDao.findCiRelationByIdPerson()
        
        @param person_id: ID of the Person
        @return: CiRelation or None
        """
        return self.search([('id_person', '=', person_id), ('isactive', '=', True)], limit=1) or None

    @api.model
    def find_ci_relations_by_person(self, person_id: int) -> 'CiRelation':
        """
        Find all CiRelations for a Person.
        
        @param person_id: ID of the Person
        @return: Recordset of CiRelations
        """
        return self.search([('id_person', '=', person_id), ('isactive', '=', True)])

    @api.model
    def find_ci_relation_by_role(self, role_id: int) -> Optional['CiRelation']:
        """
        Find CiRelation by Role.
        
        Equivalent to Java: CiRelationDao.findCiRelationByIdRole()
        
        @param role_id: ID of the Role
        @return: CiRelation or None
        """
        return self.search([('id_role', '=', role_id), ('isactive', '=', True)], limit=1) or None

    @api.model
    def find_ci_relations_by_role(self, role_id: int) -> 'CiRelation':
        """
        Find all CiRelations for a Role.
        
        @param role_id: ID of the Role
        @return: Recordset of CiRelations
        """
        return self.search([('id_role', '=', role_id), ('isactive', '=', True)])

    @api.model
    def find_ci_relation_by_config_item(self, config_item_id: int) -> 'CiRelation':
        """
        Find all CiRelations for a ConfigItem.
        
        @param config_item_id: ID of the ConfigItem
        @return: Recordset of CiRelations
        """
        return self.search([('id_ci', '=', config_item_id), ('isactive', '=', True)])

    @api.model
    def find_ci_relation_by_org_and_config_item_name(self, org_id: int, ci_name: str) -> Optional['CiRelation']:
        """
        Find CiRelation by Organization and ConfigItem name.
        
        @param org_id: ID of the Organization
        @param ci_name: Name of the ConfigItem
        @return: CiRelation or None
        """
        return self.search([
            ('id_org', '=', org_id),
            ('id_ci.name', '=', ci_name),
            ('isactive', '=', True)
        ], limit=1) or None

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def get_config_value(self):
        """
        Get the value from the linked ConfigItem.
        
        @return: The value (string, integer, or boolean)
        """
        self.ensure_one()
        if self.id_ci:
            return self.id_ci.get_value()
        return None

    def deactivate(self):
        """Deactivate this relation."""
        self.write({'isactive': False})

    def activate(self):
        """Activate this relation."""
        self.write({'isactive': True})

    # =========================================================================
    # Maintenance Actions
    # =========================================================================

    @api.model
    def action_update_all_ci_relation_names(self):
        """
        Update names for ALL CI relations in the system.
        This recalculates the computed name field for all records.

        @return: Notification action with update count
        """
        CiRelation = self.env['myschool.ci.relation']

        # Get all CI relations
        all_relations = CiRelation.search([])

        updated_count = 0
        skipped_count = 0

        for rel in all_relations:
            try:
                old_name = rel.name
                # Trigger recomputation of the name field
                rel._compute_name()
                if rel.name != old_name:
                    updated_count += 1
                    _logger.debug(f"Updated CI relation {rel.id}: {old_name} -> {rel.name}")
                else:
                    skipped_count += 1
            except Exception as e:
                _logger.warning(f"Error updating CI relation {rel.id}: {e}")
                skipped_count += 1

        _logger.info(f"Updated {updated_count} CI relation names, skipped {skipped_count}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'CI Relation Names Update Complete',
                'message': f'Updated {updated_count} CI relation names ({skipped_count} unchanged/skipped).',
                'type': 'success',
                'sticky': False,
            }
        }
