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

    @api.model
    def recalculate_all_org_trees(self):
        """
        Recalculate all ORG-TREE proprelations from ou_fqdn_internal.

        1. Remove (deactivate) all existing ORG-TREE relations
        2. For each org with ou_fqdn_internal, derive its parent FQDN
        3. Find the parent org and create a new ORG-TREE relation
        """
        from .wizards import build_proprelation_name

        Org = self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        # Get or create ORG-TREE type
        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)
        if not org_tree_type:
            org_tree_type = PropRelationType.create({
                'name': 'ORG-TREE',
                'usage': 'Organization hierarchy relationship',
                'is_active': True,
            })

        # Step 1: Remove all existing ORG-TREE relations
        existing_org_trees = PropRelation.search([
            ('proprelation_type_id', '=', org_tree_type.id),
        ])
        removed_count = len(existing_org_trees)
        if existing_org_trees:
            existing_org_trees.unlink()
            _logger.info(f"Removed {removed_count} existing ORG-TREE relations")

        # Step 2: Build FQDN-to-org index for fast parent lookup
        all_orgs = Org.search([('ou_fqdn_internal', '!=', False)])
        fqdn_to_org = {}
        for org in all_orgs:
            fqdn = org.ou_fqdn_internal.strip().lower()
            fqdn_to_org[fqdn] = org

        # Step 3: For each org, derive parent FQDN and create ORG-TREE relation
        created_count = 0
        skipped_count = 0

        for org in all_orgs:
            fqdn = org.ou_fqdn_internal.strip().lower()
            components = [c.strip() for c in fqdn.split(',') if c.strip()]

            if len(components) <= 1:
                # Root org (only dc= parts or single component) - no parent
                skipped_count += 1
                continue

            # Parent FQDN = remove the first component (ou=xxx or cn=xxx)
            # Only strip if the first component is an ou= or cn= (not dc=)
            first = components[0]
            if first.startswith('ou=') or first.startswith('cn='):
                parent_fqdn = ','.join(components[1:])
            else:
                # First component is dc= - this is a root, no parent
                skipped_count += 1
                continue

            parent_org = fqdn_to_org.get(parent_fqdn)
            if not parent_org:
                _logger.debug(
                    f"No parent org found for {org.name_short} "
                    f"(parent FQDN: {parent_fqdn})"
                )
                skipped_count += 1
                continue

            # Don't create self-referencing relations
            if parent_org.id == org.id:
                skipped_count += 1
                continue

            relation_name = build_proprelation_name(
                'ORG-TREE', id_org=org, id_org_parent=parent_org
            )

            PropRelation.create({
                'name': relation_name,
                'proprelation_type_id': org_tree_type.id,
                'id_org': org.id,
                'id_org_parent': parent_org.id,
                'is_active': True,
            })
            created_count += 1

        _logger.info(
            f"ORG-TREE recalculation complete: "
            f"removed {removed_count}, created {created_count}, skipped {skipped_count}"
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'ORG-TREE Recalculation Complete',
                'message': (
                    f'Removed {removed_count} old relations. '
                    f'Created {created_count} new relations '
                    f'({skipped_count} root orgs skipped).'
                ),
                'type': 'success',
                'sticky': True,
            }
        }
