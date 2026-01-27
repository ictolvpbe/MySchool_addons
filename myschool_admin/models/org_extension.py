# -*- coding: utf-8 -*-
"""
Org model extension - adds reverse relation to proprelations and name_tree methods
"""

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class OrgProprelations(models.Model):
    """Extend myschool.org to add proprelation_ids One2many field and name_tree methods."""
    _inherit = 'myschool.org'

    # This is just a reverse link - no database change needed
    # It allows us to show proprelations in the org form
    proprelation_ids = fields.One2many(
        'myschool.proprelation', 
        'id_org', 
        string='Relations'
    )
    
    def _compute_name_tree_from_fqdn(self):
        """
        Compute name_tree from ou_fqdn_internal.
        
        Example: ou=pers,ou=bawa,dc=olvp,dc=int becomes int.olvp.bawa.pers
        """
        self.ensure_one()
        
        if not self.ou_fqdn_internal:
            return None
        
        ou_fqdn = self.ou_fqdn_internal.lower()
        components = ou_fqdn.split(',')
        
        dc_parts = []
        ou_parts = []
        
        for comp in components:
            comp = comp.strip()
            if comp.startswith('dc='):
                dc_parts.append(comp[3:])
            elif comp.startswith('ou='):
                ou_parts.append(comp[3:])
            elif comp.startswith('cn='):
                ou_parts.append(comp[3:])
        
        # Reverse DC parts (domain first), reverse OU parts (root to leaf)
        dc_parts.reverse()
        ou_parts.reverse()
        
        parts = dc_parts + ou_parts
        
        if parts:
            return '.'.join(parts)
        return None
    
    def action_update_name_tree(self):
        """Update name_tree for this organization."""
        self.ensure_one()
        
        name_tree = self._compute_name_tree_from_fqdn()
        if name_tree:
            self.write({'name_tree': name_tree})
            _logger.info(f"Updated name_tree for {self.name_short}: {name_tree}")
        
        return True
    
    def action_update_all_name_trees(self):
        """Update name_tree for ALL organizations in the system."""
        Org = self.env['myschool.org']
        
        # Get all orgs with ou_fqdn_internal
        all_orgs = Org.search([('ou_fqdn_internal', '!=', False)])
        
        updated_count = 0
        for org in all_orgs:
            name_tree = org._compute_name_tree_from_fqdn()
            if name_tree and org.name_tree != name_tree:
                org.write({'name_tree': name_tree})
                updated_count += 1
                _logger.info(f"Updated name_tree for {org.name_short}: {name_tree}")
        
        _logger.info(f"Updated name_tree for {updated_count} organizations")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Name Tree Update Complete',
                'message': f'Updated name_tree for {updated_count} organizations.',
                'type': 'success',
                'sticky': False,
            }
        }
    
    @api.model
    def update_all_name_trees_cron(self):
        """Update all name_trees. Called from server action or cron job."""
        Org = self.env['myschool.org']
        all_orgs = Org.search([('ou_fqdn_internal', '!=', False)])
        
        updated_count = 0
        for org in all_orgs:
            name_tree = org._compute_name_tree_from_fqdn()
            if name_tree and org.name_tree != name_tree:
                org.write({'name_tree': name_tree})
                updated_count += 1
        
        _logger.info(f"Updated name_tree for {updated_count} organizations")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Name Tree Update Complete',
                'message': f'Updated name_tree for {updated_count} organizations.',
                'type': 'success',
                'sticky': False,
            }
        }
