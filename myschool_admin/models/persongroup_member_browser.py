# -*- coding: utf-8 -*-
"""
Persongroup Member Browser
==========================

Backend for the OWL2 client-action that lets an admin add/remove members
of a persongroup from a two-pane view (member list + org-tree picker).

Mutations go through `myschool.manual.task.service` so the betask audit
trail and downstream cascades stay intact.
"""

from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class PersongroupMemberBrowser(models.AbstractModel):
    _name = 'myschool.persongroup.member.browser'
    _description = 'Persongroup Member Browser (client-action backend)'

    # ------------------------------------------------------------------
    # Data retrieval
    # ------------------------------------------------------------------

    @api.model
    def get_data(self, persongroup_id, search_text=''):
        """Return everything the client needs in one call."""
        Org = self.env['myschool.org']
        pg = Org.browse(persongroup_id).exists()
        if not pg:
            return {'error': f'Persongroup {persongroup_id} not found'}

        members = self._get_members(pg)
        member_ids = {m['id'] for m in members}
        tree = self._get_org_tree(search_text=search_text,
                                  exclude_member_ids=member_ids,
                                  exclude_org_id=persongroup_id)

        return {
            'persongroup': {
                'id': pg.id,
                'name': pg.name,
                'name_tree': pg.name_tree or pg.name,
            },
            'members': members,
            'tree': tree,
        }

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    @api.model
    def add_members(self, persongroup_id, person_ids):
        if not person_ids:
            return {'added': 0}
        service = self.env['myschool.manual.task.service']
        for pid in person_ids:
            service.create_manual_task('PROPRELATION', 'ADD', {
                'type': 'PG-P',
                'org_id': persongroup_id,
                'person_id': pid,
            })
        return {'added': len(person_ids)}

    @api.model
    def remove_members(self, persongroup_id, person_ids):
        if not person_ids:
            return {'removed': 0}
        service = self.env['myschool.manual.task.service']
        for pid in person_ids:
            service.create_manual_task('PROPRELATION', 'DEACT', {
                'type': 'PG-P',
                'org_id': persongroup_id,
                'person_id': pid,
            })
        return {'removed': len(person_ids)}

    # ------------------------------------------------------------------
    # Member list (left pane)
    # ------------------------------------------------------------------

    def _get_members(self, pg):
        """Active PG-P members of this persongroup, sorted by full name."""
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        pg_p_type = PropRelationType.search([('name', '=', 'PG-P')], limit=1)
        if not pg_p_type:
            return []
        rels = PropRelation.search([
            ('proprelation_type_id', '=', pg_p_type.id),
            ('id_org', '=', pg.id),
            ('is_active', '=', True),
            ('id_person', '!=', False),
        ])
        out = []
        for rel in rels:
            p = rel.id_person
            if not p:
                continue
            out.append({
                'id': p.id,
                'name': p.name or '',
                'first_name': p.first_name or '',
                'display': self._person_display(p),
                'person_type': p.person_type_id.name if p.person_type_id else '',
                'tree_org': p.tree_org_id.name_tree or p.tree_org_id.name if p.tree_org_id else '',
            })
        out.sort(key=lambda x: (x['name'].lower(), x['first_name'].lower()))
        return out

    @staticmethod
    def _person_display(p):
        if p.first_name and p.name:
            return f'{p.first_name} {p.name}'
        return p.name or p.first_name or f'#{p.id}'

    # ------------------------------------------------------------------
    # Org tree (right pane)
    # ------------------------------------------------------------------

    def _get_org_tree(self, search_text='', exclude_member_ids=None,
                      exclude_org_id=None):
        """Build an ORG-TREE rooted at all top-level orgs, with persons
        attached at their PERSON-TREE leaf. Excludes:
        - the persongroup itself (you can't add it to itself);
        - persons already in `exclude_member_ids` (so the right pane
          only shows candidates).
        """
        Org = self.env['myschool.org']
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        exclude_member_ids = exclude_member_ids or set()

        # Resolve relation types up front.
        org_tree_type = PropRelationType.search([('name', '=', 'ORG-TREE')], limit=1)
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)

        # Collect orgs. Admin-orgs (OU-holders, organisatorische
        # tussenlagen) tonen we niet als knoop in de picker, maar we
        # gebruiken ze WEL om de hiërarchie tussen niet-admin orgs te
        # bepalen — anders zouden classgroups e.d. losraken van hun
        # school. Daarom: laad alles, bouw raw parent-map, collapse
        # admin-knopen door de eerste niet-admin voorouder te vinden.
        active_domain = [('is_active', '=', True)]
        if exclude_org_id:
            active_domain.append(('id', '!=', exclude_org_id))
        all_active = Org.search(active_domain)
        full_dict = {o.id: o for o in all_active}

        org_dict = {oid: o for oid, o in full_dict.items()
                    if not o.is_administrative}
        all_org_ids = set(org_dict)

        # Build raw child→parent map across ALL active orgs.
        raw_parent = {}
        if org_tree_type:
            rels = PropRelation.search([
                ('proprelation_type_id', '=', org_tree_type.id),
                ('is_active', '=', True),
                ('id_org', '!=', False),
                ('id_org_parent', '!=', False),
            ])
            seen_pairs = set()
            for rel in rels:
                child_id = rel.id_org.id
                parent_id = rel.id_org_parent.id
                if child_id == parent_id or (child_id, parent_id) in seen_pairs:
                    continue
                seen_pairs.add((child_id, parent_id))
                if child_id in full_dict and parent_id in full_dict:
                    # Keep the first parent we see — multiple ORG-TREE
                    # rows for the same child are not expected in normal
                    # data; if they happen, deterministic-first wins.
                    raw_parent.setdefault(child_id, parent_id)

        # For each non-admin org, find its first non-admin ancestor by
        # skipping admin parents. Build the visible parent→children map
        # from those collapsed pairs.
        def _first_non_admin_ancestor(oid):
            cur = raw_parent.get(oid)
            seen = set()
            while cur is not None and cur not in seen:
                seen.add(cur)
                if cur in all_org_ids:  # non-admin → use it
                    return cur
                cur = raw_parent.get(cur)
            return None

        org_parent = {}
        org_children = {}
        for oid in all_org_ids:
            anc = _first_non_admin_ancestor(oid)
            if anc is not None:
                org_parent[oid] = anc
                org_children.setdefault(anc, []).append(oid)

        # Persons by org via PERSON-TREE. As with orgs: persons whose
        # PERSON-TREE org is administrative are re-attached to the
        # first non-admin ancestor — otherwise they'd disappear from
        # the picker.
        persons_by_org = {}
        if person_tree_type:
            person_rels = PropRelation.search([
                ('proprelation_type_id', '=', person_tree_type.id),
                ('is_active', '=', True),
                ('id_person', '!=', False),
                ('id_org', '!=', False),
            ])
            for rel in person_rels:
                p = rel.id_person
                if not p or not p.is_active or p.id in exclude_member_ids:
                    continue
                raw_org_id = rel.id_org.id
                if raw_org_id not in full_dict:
                    continue
                if raw_org_id in all_org_ids:
                    org_id = raw_org_id
                else:
                    org_id = _first_non_admin_ancestor(raw_org_id)
                    if org_id is None:
                        continue
                bucket = persons_by_org.setdefault(org_id, {})
                if p.id not in bucket:
                    bucket[p.id] = {
                        'id': p.id,
                        'name': self._person_display(p),
                        'person_type': p.person_type_id.name if p.person_type_id else '',
                    }

        # Optional name filter — case-insensitive substring on org or person.
        needle = (search_text or '').strip().lower()

        def _display_short(org):
            # Prefer name_short for compactness; fall back to name when
            # no short name is set.
            return org.name_short or org.name or ''

        def _build(org_id, visited):
            if org_id in visited:
                return None
            visited = visited | {org_id}
            org = org_dict[org_id]
            children = []
            for cid in sorted(org_children.get(org_id, []),
                              key=lambda i: _display_short(org_dict[i]).lower()):
                node = _build(cid, visited)
                if node:
                    children.append(node)
            persons = sorted(
                persons_by_org.get(org_id, {}).values(),
                key=lambda p: p['name'].lower(),
            )
            if needle:
                # Drop persons that don't match.
                persons = [p for p in persons if needle in p['name'].lower()]
            display = _display_short(org)
            org_match = (
                not needle
                or needle in display.lower()
                or needle in (org.name or '').lower()
            )
            # Keep org if it matches OR if any descendant survived.
            if not org_match and not children and not persons:
                return None
            return {
                'id': org.id,
                'name': display,
                'name_full': org.name or '',
                'org_type': org.org_type_id.name if org.org_type_id else '',
                'children': children,
                'persons': persons,
            }

        roots = [oid for oid in all_org_ids
                 if oid not in org_parent or org_parent[oid] not in all_org_ids]
        roots.sort(key=lambda i: _display_short(org_dict[i]).lower())
        tree = []
        for rid in roots:
            node = _build(rid, set())
            if node:
                tree.append(node)
        return tree
