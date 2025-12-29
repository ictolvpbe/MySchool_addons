# -*- coding: utf-8 -*-
"""
Wizards for Object Browser
==========================

Provides wizards for:
- Assigning roles to persons
- Moving objects in hierarchy
- Bulk operations
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class AssignRoleWizard(models.TransientModel):
    """Wizard to assign a role to a person within an organization."""
    _name = 'myschool.assign.role.wizard'
    _description = 'Assign Role to Person'
    
    person_id = fields.Many2one(
        'myschool.person',
        string='Persoon',
        required=True
    )
    
    role_id = fields.Many2one(
        'myschool.role',
        string='Rol',
        required=True,
        domain=[('is_active', '=', True)]
    )
    
    org_id = fields.Many2one(
        'myschool.org',
        string='Organisatie',
        required=True,
        domain=[('is_active', '=', True)]
    )
    
    proprelation_type_id = fields.Many2one(
        'myschool.proprelation.type',
        string='Relatie Type',
        domain=[('is_active', '=', True)]
    )
    
    is_master = fields.Boolean(
        string='Is Master Relatie',
        default=False,
        help='Markeer als primaire relatie'
    )
    
    start_date = fields.Datetime(
        string='Startdatum',
        default=fields.Datetime.now
    )
    
    def action_assign(self):
        """Create the proprelation to assign the role."""
        self.ensure_one()
        
        # Check if relation already exists
        existing = self.env['myschool.proprelation'].search([
            ('id_person', '=', self.person_id.id),
            ('id_role', '=', self.role_id.id),
            ('id_org', '=', self.org_id.id),
            ('is_active', '=', True)
        ], limit=1)
        
        if existing:
            raise UserError(_('Deze persoon heeft deze rol al bij deze organisatie.'))
        
        # Get display name
        person_name = self.person_id.display_name if hasattr(self.person_id, 'display_name') else self.person_id.name
        
        # Create new proprelation
        vals = {
            'name': f"{person_name} - {self.role_id.name} @ {self.org_id.name}",
            'id_person': self.person_id.id,
            'id_role': self.role_id.id,
            'id_org': self.org_id.id,
            'proprelation_type_id': self.proprelation_type_id.id if self.proprelation_type_id else False,
            'is_master': self.is_master,
            'is_active': True,
            'start_date': self.start_date,
        }
        
        relation = self.env['myschool.proprelation'].create(vals)
        _logger.info(f"Created proprelation {relation.id}: {relation.name}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Rol Toegewezen'),
                'message': _('Rol %s is toegewezen aan %s bij %s') % (
                    self.role_id.name, person_name, self.org_id.name
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }


class MoveOrgWizard(models.TransientModel):
    """Wizard to move an organization to a new parent using proprelation."""
    _name = 'myschool.move.org.wizard'
    _description = 'Move Organization'
    
    org_id = fields.Many2one(
        'myschool.org',
        string='Organisatie',
        required=True
    )
    
    current_parent_id = fields.Many2one(
        'myschool.org',
        string='Huidige Parent',
        compute='_compute_current_parent',
        readonly=True
    )
    
    new_parent_id = fields.Many2one(
        'myschool.org',
        string='Nieuwe Parent',
        domain="[('id', '!=', org_id)]",
        help='Laat leeg om naar root niveau te verplaatsen'
    )
    
    @api.depends('org_id')
    def _compute_current_parent(self):
        """Get current parent from proprelation."""
        PropRelation = self.env['myschool.proprelation']
        for wizard in self:
            if wizard.org_id:
                parent_rel = PropRelation.search([
                    ('id_org', '=', wizard.org_id.id),
                    ('id_org_parent', '!=', False),
                    ('is_active', '=', True)
                ], limit=1)
                wizard.current_parent_id = parent_rel.id_org_parent if parent_rel else False
            else:
                wizard.current_parent_id = False
    
    def action_move(self):
        """Execute the move using proprelation."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        
        # Find or create OrgTree relation type
        org_tree_type = PropRelationType.search([
            '|', '|',
            ('name', '=', 'OrgTree'),
            ('name', '=', 'Org Tree'),
            ('name', '=', 'ORG_TREE')
        ], limit=1)
        
        if not org_tree_type:
            org_tree_type = PropRelationType.create({
                'name': 'OrgTree',
                'usage': 'Organization hierarchy',
                'is_active': True
            })
        
        # Find existing parent relation for this org
        existing_rel = PropRelation.search([
            ('id_org', '=', self.org_id.id),
            ('id_org_parent', '!=', False),
            ('is_active', '=', True)
        ], limit=1)
        
        old_parent_name = existing_rel.id_org_parent.name if existing_rel else 'Root'
        
        if self.new_parent_id:
            # Check for circular reference
            current = self.new_parent_id
            checked_ids = set()
            while current:
                if current.id == self.org_id.id:
                    raise ValidationError(_('Kan niet verplaatsen naar een eigen sub-organisatie!'))
                if current.id in checked_ids:
                    break  # Prevent infinite loop
                checked_ids.add(current.id)
                
                # Get parent of current via proprelation
                parent_rel = PropRelation.search([
                    ('id_org', '=', current.id),
                    ('id_org_parent', '!=', False),
                    ('is_active', '=', True)
                ], limit=1)
                current = parent_rel.id_org_parent if parent_rel else None
            
            # Update or create parent relation
            if existing_rel:
                existing_rel.write({
                    'id_org_parent': self.new_parent_id.id,
                    'name': f"{self.org_id.name} -> {self.new_parent_id.name}"
                })
            else:
                PropRelation.create({
                    'name': f"{self.org_id.name} -> {self.new_parent_id.name}",
                    'proprelation_type_id': org_tree_type.id,
                    'id_org': self.org_id.id,
                    'id_org_parent': self.new_parent_id.id,
                    'is_active': True,
                    'is_organisational': True,
                })
            
            new_parent_name = self.new_parent_id.name
        else:
            # Moving to root - deactivate parent relation
            if existing_rel:
                existing_rel.write({'is_active': False})
            new_parent_name = 'Root'
        
        msg = _('Organisatie %s verplaatst van %s naar %s') % (
            self.org_id.name,
            old_parent_name,
            new_parent_name
        )
        
        _logger.info(msg)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Organisatie Verplaatst'),
                'message': msg,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }


class MovePersonWizard(models.TransientModel):
    """Wizard to move a person to a different organization."""
    _name = 'myschool.move.person.wizard'
    _description = 'Move Person to Organization'
    
    person_id = fields.Many2one(
        'myschool.person',
        string='Persoon',
        required=True
    )
    
    current_org_id = fields.Many2one(
        'myschool.org',
        string='Huidige Organisatie'
    )
    
    new_org_id = fields.Many2one(
        'myschool.org',
        string='Nieuwe Organisatie',
        required=True,
        domain=[('is_active', '=', True)]
    )
    
    role_id = fields.Many2one(
        'myschool.role',
        string='Rol',
        help='Optioneel: Selecteer welke rol te verplaatsen. Laat leeg om alle rollen te verplaatsen.'
    )
    
    keep_old_relations = fields.Boolean(
        string='Oude relaties behouden',
        default=False,
        help='Als aangevinkt, worden oude relaties niet gedeactiveerd'
    )
    
    def action_move(self):
        """Execute the move - update proprelations."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        
        # Find existing relations
        domain = [
            ('id_person', '=', self.person_id.id),
            ('is_active', '=', True)
        ]
        
        if self.current_org_id:
            domain.append(('id_org', '=', self.current_org_id.id))
        
        if self.role_id:
            domain.append(('id_role', '=', self.role_id.id))
        
        relations = PropRelation.search(domain)
        
        if not relations:
            raise UserError(_('Geen actieve relaties gevonden om te verplaatsen.'))
        
        person_name = self.person_id.display_name if hasattr(self.person_id, 'display_name') else self.person_id.name
        
        moved_count = 0
        for rel in relations:
            role_name = rel.id_role.name if rel.id_role else 'N/A'
            new_name = f"{person_name} - {role_name} @ {self.new_org_id.name}"
            
            if self.keep_old_relations:
                # Create new relation, keep old one
                rel.copy({
                    'id_org': self.new_org_id.id,
                    'name': new_name,
                })
            else:
                # Update existing relation
                rel.write({
                    'id_org': self.new_org_id.id,
                    'name': new_name,
                })
            moved_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Persoon Verplaatst'),
                'message': _('%d relatie(s) verplaatst naar %s') % (moved_count, self.new_org_id.name),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }


class RemoveRoleWizard(models.TransientModel):
    """Wizard to remove a role from a person."""
    _name = 'myschool.remove.role.wizard'
    _description = 'Remove Role from Person'
    
    proprelation_id = fields.Many2one(
        'myschool.proprelation',
        string='Relatie',
        required=True
    )
    
    person_id = fields.Many2one(
        'myschool.person',
        string='Persoon',
        related='proprelation_id.id_person',
        readonly=True
    )
    
    role_id = fields.Many2one(
        'myschool.role',
        string='Rol',
        related='proprelation_id.id_role',
        readonly=True
    )
    
    org_id = fields.Many2one(
        'myschool.org',
        string='Organisatie',
        related='proprelation_id.id_org',
        readonly=True
    )
    
    delete_permanently = fields.Boolean(
        string='Permanent verwijderen',
        default=False,
        help='Als aangevinkt, wordt de relatie definitief verwijderd. Anders wordt deze gedeactiveerd.'
    )
    
    def action_remove(self):
        """Remove or deactivate the relation."""
        self.ensure_one()
        
        if self.delete_permanently:
            self.proprelation_id.unlink()
            msg = _('Relatie definitief verwijderd')
        else:
            self.proprelation_id.write({'is_active': False})
            msg = _('Relatie gedeactiveerd')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Rol Verwijderd'),
                'message': msg,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }


class AddChildOrgWizard(models.TransientModel):
    """Wizard to add a child organization using proprelation."""
    _name = 'myschool.add.child.org.wizard'
    _description = 'Add Child Organization'
    
    parent_org_id = fields.Many2one(
        'myschool.org',
        string='Parent Organisatie',
        required=True
    )
    
    child_org_id = fields.Many2one(
        'myschool.org',
        string='Sub Organisatie',
        required=True,
        domain="[('id', '!=', parent_org_id), ('is_active', '=', True)]",
        help='Selecteer een bestaande organisatie om als sub-organisatie toe te voegen'
    )
    
    def action_add(self):
        """Create the proprelation to link child to parent org."""
        self.ensure_one()
        
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        
        # Check if relation already exists
        existing = PropRelation.search([
            ('id_org', '=', self.child_org_id.id),
            ('id_org_parent', '=', self.parent_org_id.id),
            ('is_active', '=', True)
        ], limit=1)
        
        if existing:
            raise UserError(_('Deze organisatie is al een sub-organisatie van de geselecteerde parent.'))
        
        # Check if child already has a different parent
        existing_parent = PropRelation.search([
            ('id_org', '=', self.child_org_id.id),
            ('id_org_parent', '!=', False),
            ('is_active', '=', True)
        ], limit=1)
        
        if existing_parent:
            raise UserError(_('Deze organisatie heeft al een parent (%s). Gebruik "Verplaatsen" om de parent te wijzigen.') % existing_parent.id_org_parent.name)
        
        # Check for circular reference
        current = self.parent_org_id
        checked_ids = set()
        while current:
            if current.id == self.child_org_id.id:
                raise ValidationError(_('Circulaire referentie: de parent is een sub-organisatie van de geselecteerde organisatie!'))
            if current.id in checked_ids:
                break
            checked_ids.add(current.id)
            
            parent_rel = PropRelation.search([
                ('id_org', '=', current.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True)
            ], limit=1)
            current = parent_rel.id_org_parent if parent_rel else None
        
        # Find or create OrgTree relation type
        org_tree_type = PropRelationType.search([
            '|', '|',
            ('name', '=', 'OrgTree'),
            ('name', '=', 'Org Tree'),
            ('name', '=', 'ORG_TREE')
        ], limit=1)
        
        if not org_tree_type:
            org_tree_type = PropRelationType.create({
                'name': 'OrgTree',
                'usage': 'Organization hierarchy',
                'is_active': True
            })
        
        # Create proprelation
        PropRelation.create({
            'name': f"{self.child_org_id.name} -> {self.parent_org_id.name}",
            'proprelation_type_id': org_tree_type.id,
            'id_org': self.child_org_id.id,
            'id_org_parent': self.parent_org_id.id,
            'is_active': True,
            'is_organisational': True,
        })
        
        _logger.info(f"Added {self.child_org_id.name} as child of {self.parent_org_id.name}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sub Organisatie Toegevoegd'),
                'message': _('%s is nu een sub-organisatie van %s') % (self.child_org_id.name, self.parent_org_id.name),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
