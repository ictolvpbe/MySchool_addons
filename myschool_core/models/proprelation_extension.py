# -*- coding: utf-8 -*-
"""
Proprelation model extension - adds method to update all proprelation names
"""

from odoo import models, fields, api
from .wizards import build_proprelation_name
import logging

_logger = logging.getLogger(__name__)


class ProprelationExtension(models.Model):
    """Extend myschool.proprelation to add name update methods."""
    _inherit = 'myschool.proprelation'
    
    def _compute_standardized_name(self):
        """
        Compute the standardized name for this proprelation based on its type and related records.
        
        Returns:
            String with standardized name or None if cannot be computed
        """
        self.ensure_one()
        
        # Get proprelation type name
        type_name = None
        if self.proprelation_type_id and self.proprelation_type_id.name:
            type_name = self.proprelation_type_id.name
        
        if not type_name:
            return None
        
        # Build kwargs for build_proprelation_name
        kwargs = {}
        
        # Add org fields
        if self.id_org:
            kwargs['id_org'] = self.id_org
        if self.id_org_parent:
            kwargs['id_org_parent'] = self.id_org_parent
        if self.id_org_child:
            kwargs['id_org_child'] = self.id_org_child
        
        # Add role fields
        if self.id_role:
            kwargs['id_role'] = self.id_role
        if self.id_role_parent:
            kwargs['id_role_parent'] = self.id_role_parent
        if self.id_role_child:
            kwargs['id_role_child'] = self.id_role_child
        
        # Add person fields
        if self.id_person:
            kwargs['id_person'] = self.id_person
        if self.id_person_parent:
            kwargs['id_person_parent'] = self.id_person_parent
        if self.id_person_child:
            kwargs['id_person_child'] = self.id_person_child
        
        # Add period fields
        if self.id_period:
            kwargs['id_period'] = self.id_period
        if self.id_period_parent:
            kwargs['id_period_parent'] = self.id_period_parent
        if self.id_period_child:
            kwargs['id_period_child'] = self.id_period_child
        
        # Only build name if we have at least one related record
        if kwargs:
            return build_proprelation_name(type_name, **kwargs)
        
        return None
    
    def action_update_name(self):
        """Update the name of this proprelation to the standardized format."""
        self.ensure_one()
        
        new_name = self._compute_standardized_name()
        if new_name and self.name != new_name:
            self.write({'name': new_name})
            _logger.info(f"Updated proprelation name: {new_name}")
        
        return True
    
    @api.model
    def update_all_proprelation_names(self):
        """Update names for ALL proprelations in the system."""
        PropRelation = self.env['myschool.proprelation']
        
        # Get all proprelations with a type
        all_rels = PropRelation.search([('proprelation_type_id', '!=', False)])
        
        updated_count = 0
        skipped_count = 0
        
        for rel in all_rels:
            try:
                new_name = rel._compute_standardized_name()
                if new_name and rel.name != new_name:
                    rel.write({'name': new_name})
                    updated_count += 1
                    _logger.debug(f"Updated proprelation {rel.id}: {new_name}")
                else:
                    skipped_count += 1
            except Exception as e:
                _logger.warning(f"Error updating proprelation {rel.id}: {e}")
                skipped_count += 1
        
        _logger.info(f"Updated {updated_count} proprelation names, skipped {skipped_count}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Proprelation Names Update Complete',
                'message': f'Updated {updated_count} proprelation names ({skipped_count} unchanged/skipped).',
                'type': 'success',
                'sticky': False,
            }
        }
