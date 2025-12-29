# -*- coding: utf-8 -*-
"""
Object Browser - Hierarchical Tree View
========================================
Backend model that provides tree data as JSON.
The frontend OWL component handles expand/collapse.
"""

from odoo import models, fields, api
import json
import logging

_logger = logging.getLogger(__name__)


class ObjectBrowser(models.TransientModel):
    """
    Object Browser - provides tree data for the OWL component.
    """
    _name = 'myschool.object.browser'
    _description = 'Object Browser'

    name = fields.Char(default='Object Browser')

    @api.model
    def get_tree_data(self, search_text='', show_inactive=False):
        """
        Get tree data as JSON for the OWL component.
        Returns a list of root nodes, each with children.
        """
        result = {
            'organizations': self._get_org_tree(search_text, show_inactive),
            'roles': self._get_role_list(show_inactive),
        }
        return result

    def _get_org_tree(self, search_text='', show_inactive=False):
        """Build organization tree using proprelation."""
        if 'myschool.org' not in self.env:
            return []
        
        Org = self.env['myschool.org']
        
        # Get all orgs
        domain = []
        if not show_inactive:
            domain.append(('is_active', '=', True))
        if search_text:
            domain.append(('name', 'ilike', search_text))
        
        all_orgs = Org.search(domain, order='name')
        
        # Build parent-child map from proprelation
        org_children = {}
        org_parent = {}
        
        if 'myschool.proprelation' in self.env:
            PropRelation = self.env['myschool.proprelation']
            
            # id_org (child) -> id_org_parent (parent)
            relations = PropRelation.search([
                ('id_org', '!=', False),
                ('id_org_parent', '!=', False),
            ])
            
            for rel in relations:
                is_active = rel.is_active if hasattr(rel, 'is_active') else True
                if is_active or show_inactive:
                    child_id = rel.id_org.id
                    parent_id = rel.id_org_parent.id
                    org_parent[child_id] = parent_id
                    if parent_id not in org_children:
                        org_children[parent_id] = []
                    org_children[parent_id].append(child_id)
            
            # Also check id_org_child -> id_org_parent
            relations2 = PropRelation.search([
                ('id_org_child', '!=', False),
                ('id_org_parent', '!=', False),
            ])
            
            for rel in relations2:
                is_active = rel.is_active if hasattr(rel, 'is_active') else True
                if is_active or show_inactive:
                    child_id = rel.id_org_child.id
                    parent_id = rel.id_org_parent.id
                    org_parent[child_id] = parent_id
                    if parent_id not in org_children:
                        org_children[parent_id] = []
                    if child_id not in org_children[parent_id]:
                        org_children[parent_id].append(child_id)
        
        # Find root orgs
        root_orgs = [org for org in all_orgs if org.id not in org_parent]
        
        # Build tree
        org_dict = {org.id: org for org in all_orgs}
        tree = []
        for org in root_orgs:
            tree.append(self._build_org_node(org, org_dict, org_children))
        
        return tree

    def _build_org_node(self, org, org_dict, org_children):
        """Build a single org node with children."""
        child_ids = org_children.get(org.id, [])
        
        # Get person count
        person_count = 0
        persons = []
        if 'myschool.proprelation' in self.env:
            PropRelation = self.env['myschool.proprelation']
            person_rels = PropRelation.search([
                ('id_org', '=', org.id),
                ('id_person', '!=', False),
                ('is_active', '=', True)
            ])
            
            person_dict = {}
            for rel in person_rels:
                pid = rel.id_person.id
                if pid not in person_dict:
                    person = rel.id_person
                    name = person.name or 'Unknown'
                    if hasattr(person, 'first_name') and person.first_name:
                        name = f"{person.first_name} {person.name}"
                    person_dict[pid] = {
                        'id': pid,
                        'name': name,
                        'type': 'person',
                        'model': 'myschool.person',
                        'roles': []
                    }
                if rel.id_role:
                    role = rel.id_role
                    role_name = role.shortname if hasattr(role, 'shortname') and role.shortname else role.name
                    person_dict[pid]['roles'].append(role_name)
            
            persons = list(person_dict.values())
            person_count = len(persons)
        
        node = {
            'id': org.id,
            'name': org.name,
            'type': 'org',
            'model': 'myschool.org',
            'child_count': len(child_ids),
            'person_count': person_count,
            'children': [],
            'persons': persons,
        }
        
        # Add child orgs
        for child_id in child_ids:
            if child_id in org_dict:
                child_org = org_dict[child_id]
                node['children'].append(self._build_org_node(child_org, org_dict, org_children))
        
        return node

    def _get_role_list(self, show_inactive=False):
        """Get flat list of roles."""
        if 'myschool.role' not in self.env:
            return []
        
        Role = self.env['myschool.role']
        domain = []
        if not show_inactive:
            if 'is_active' in Role._fields:
                domain.append(('is_active', '=', True))
        
        roles = Role.search(domain, order='name')
        
        return [{
            'id': role.id,
            'name': role.name,
            'shortname': role.shortname if hasattr(role, 'shortname') else '',
            'type': 'role',
            'model': 'myschool.role',
        } for role in roles]

    @api.model
    def search_persons(self, search_text, limit=50):
        """Search persons by name."""
        if 'myschool.person' not in self.env or not search_text:
            return []
        
        Person = self.env['myschool.person']
        domain = [
            '|',
            ('name', 'ilike', search_text),
            ('first_name', 'ilike', search_text),
        ]
        
        persons = Person.search(domain, limit=limit, order='name')
        
        return [{
            'id': p.id,
            'name': f"{p.first_name} {p.name}" if hasattr(p, 'first_name') and p.first_name else p.name,
            'type': 'person',
            'model': 'myschool.person',
        } for p in persons]
