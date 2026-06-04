# -*- coding: utf-8 -*-
"""
Settings Item — catalogus / definitie

Vervangt het oude `myschool.config.item` model (verwijderd in fase 5).
Belangrijkste eigenschappen:
- Slechts één definitie per key (uniek).
- Geen waarde-velden op de definitie zelf — die staan op
  `myschool.settings.value`.
- `scope_kind` bepaalt waar overrides zijn toegestaan (global / org /
  person / both = global+org).

Lookup-API: zie `get()` onderaan deze module. Walk-volgorde volgt
ORG-TREE upward met `inherit_to_children`-gating.

Note: `migrate_from_legacy` blijft als no-op wanneer de oude modellen
weg zijn, voor het geval een productie-DB nog ongemigreerde tabellen
heeft uit een tussenrelease.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

VALUE_TYPES = [
    ('string', 'Tekst'),
    ('integer', 'Geheel getal'),
    ('boolean', 'Ja / Nee'),
]

SCOPE_KINDS = [
    ('global', 'Alleen globaal'),
    ('org', 'Alleen per organisatie'),
    ('person', 'Alleen per persoon'),
    ('both', 'Globaal + per organisatie'),
]

# Veilige bovengrens voor ORG-TREE walks. Onze hiërarchie is in de
# praktijk hooguit 4-5 lagen diep; 20 is meer dan ruim genoeg en
# voorkomt dat een corrupte cyclus deze code laat hangen.
_MAX_ORG_DEPTH = 20


class SettingsItem(models.Model):
    _name = 'myschool.settings.item'
    _description = 'MySchool Settings Item (catalogus-definitie)'
    _order = 'category, key'
    _rec_name = 'label'

    key = fields.Char(
        string='Sleutel', required=True, index=True,
        help='Machine-naam waarmee deze SI in code wordt opgezocht '
             '(bv. CurrentSchoolYear, OuForGroups). Uniek.')
    label = fields.Char(
        string='Label', required=True, translate=True,
        help='Mens-leesbare naam voor in de UI.')
    description = fields.Text(string='Beschrijving', translate=True)
    category = fields.Selection(
        [('integrations', 'Integraties'),
         ('lifecycle', 'Lifecycle'),
         ('ad_ou', 'AD / OU'),
         ('general', 'Algemeen')],
        string='Categorie', default='general', required=True, index=True)

    value_type = fields.Selection(
        VALUE_TYPES, string='Waarde-type',
        required=True, default='string')
    scope_kind = fields.Selection(
        SCOPE_KINDS, string='Scope',
        required=True, default='global', index=True,
        help="'Alleen globaal' = één waarde voor heel MySchool. "
             "'Alleen per organisatie' = waarde per org (en sub-orgs "
             "kunnen overerven). 'Both' = beide; per-org override op "
             "een globale fallback. 'Alleen per persoon' = eigen voor "
             "individuele personen.")

    default_string = fields.Char(string='Default (tekst)')
    default_integer = fields.Integer(string='Default (getal)')
    default_boolean = fields.Boolean(string='Default (boolean)')

    is_encrypted = fields.Boolean(
        string='Encrypted',
        help='Wachtwoorden / secrets. UI verbergt de waarde achter dots; '
             'export-routines slaan deze SI over.')
    is_active = fields.Boolean(string='Actief', default=True, index=True)

    value_ids = fields.One2many(
        comodel_name='myschool.settings.value',
        inverse_name='settings_item_id',
        string='Waarden')

    _key_unique = models.Constraint(
        'UNIQUE(key)',
        'Een Settings Item met deze sleutel bestaat al.',
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _default_value(self):
        """Geef de default-waarde uit de catalogus volgens value_type."""
        self.ensure_one()
        if self.value_type == 'string':
            return self.default_string or None
        if self.value_type == 'integer':
            return self.default_integer
        if self.value_type == 'boolean':
            return self.default_boolean
        return None

    def _extract_value(self, value_record):
        """Haal de typed waarde uit een settings.value-record volgens
        value_type van deze SI-definitie."""
        self.ensure_one()
        if self.value_type == 'string':
            return value_record.string_value or None
        if self.value_type == 'integer':
            return value_record.integer_value
        if self.value_type == 'boolean':
            return value_record.boolean_value
        return None

    @api.model
    def _walk_org_ancestors(self, org):
        """Yield org zelf, dan iedere ORG-TREE-voorouder, in volgorde
        van dichtstbij naar verst weg. Stopt op cyclus of na
        ``_MAX_ORG_DEPTH`` stappen — onze hiërarchie is in de praktijk
        veel ondieper.
        """
        if not org:
            return
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        org_tree = PropRelationType.search(
            [('name', '=', 'ORG-TREE')], limit=1)
        yield org
        if not org_tree:
            return
        current = org
        seen = {org.id}
        for _ in range(_MAX_ORG_DEPTH):
            rel = PropRelation.search([
                ('proprelation_type_id', '=', org_tree.id),
                ('id_org', '=', current.id),
                ('id_org_parent', '!=', False),
                ('is_active', '=', True),
            ], limit=1)
            if not rel or not rel.id_org_parent:
                return
            parent = rel.id_org_parent
            if parent.id in seen:
                return
            seen.add(parent.id)
            yield parent
            current = parent

    # ------------------------------------------------------------------
    # Lookup-API (vervangt ConfigItem.get_ci_value_by_org_and_name)
    # ------------------------------------------------------------------

    @api.model
    def get(self, key, org=None, person=None, default=None):
        """Resolve een SI-waarde met inheritance-fallback.

        Volgorde van fallback (eerste hit wint):
          1. ``person``-waarde (geen inheritance — alleen direct).
          2. ``org``-waarde: walk ORG-TREE upward. Eigen org wint
             altijd; voorouder enkel als die waarde
             ``inherit_to_children=True`` heeft.
          3. globale waarde (``org_id=False, person_id=False``).
          4. ``default_*`` uit de catalogus-definitie.
          5. de ``default`` parameter.

        :param key:    SI-sleutel (Char, bv. 'CurrentSchoolYear').
        :param org:    optioneel ``myschool.org``-record (of False).
        :param person: optioneel ``myschool.person``-record (of False).
        :param default: terugval als geen enkele bron iets oplevert.
        """
        item = self.search(
            [('key', '=', key), ('is_active', '=', True)], limit=1)
        if not item:
            _logger.debug(
                "Settings Item '%s' niet gevonden in catalogus.", key)
            return default

        Value = self.env['myschool.settings.value']

        # 1. Person-scoped — direct, geen inheritance.
        if person:
            v = Value.search([
                ('settings_item_id', '=', item.id),
                ('person_id', '=', person.id),
                ('is_active', '=', True),
            ], limit=1)
            if v:
                return item._extract_value(v)

        # 2. Org-scoped met ORG-TREE walk.
        if org:
            is_self = True
            for ancestor in item._walk_org_ancestors(org):
                v = Value.search([
                    ('settings_item_id', '=', item.id),
                    ('org_id', '=', ancestor.id),
                    ('person_id', '=', False),
                    ('is_active', '=', True),
                ], limit=1)
                if v and (is_self or v.inherit_to_children):
                    return item._extract_value(v)
                is_self = False

        # 3. Globale waarde (org_id en person_id beide leeg).
        v = Value.search([
            ('settings_item_id', '=', item.id),
            ('org_id', '=', False),
            ('person_id', '=', False),
            ('is_active', '=', True),
        ], limit=1)
        if v:
            return item._extract_value(v)

        # 4 + 5. Catalogus-default → expliciete default.
        catalog_default = item._default_value()
        if catalog_default is not None:
            # Booleans returnen we altijd; integers ook (0 is geldig).
            return catalog_default
        return default

    @api.model
    def set(self, key, value, org=None, person=None,
            inherit_to_children=True):
        """Schrijf een SI-waarde weg op het juiste scope-niveau.

        - Zonder ``org`` en ``person``: globale waarde.
        - Met ``org``: per-org waarde, met ``inherit_to_children``
          bepaalt of sub-orgs deze ook gebruiken (default True —
          opt-out per waarde, conform de afspraak).
        - Met ``person``: per-person waarde (geen inheritance).

        Maakt een nieuw ``myschool.settings.value`` aan of overschrijft
        een bestaand record op exact dit (key, scope)-niveau.
        """
        item = self.search([('key', '=', key)], limit=1)
        if not item:
            raise ValidationError(
                _("Settings Item '%s' bestaat niet in de catalogus.")
                % key)

        Value = self.env['myschool.settings.value']
        domain = [
            ('settings_item_id', '=', item.id),
            ('org_id', '=', org.id if org else False),
            ('person_id', '=', person.id if person else False),
        ]
        existing = Value.search(domain, limit=1)

        vals = {
            'settings_item_id': item.id,
            'org_id': org.id if org else False,
            'person_id': person.id if person else False,
            'is_active': True,
        }
        if org:
            vals['inherit_to_children'] = inherit_to_children

        if item.value_type == 'string':
            vals['string_value'] = value or False
        elif item.value_type == 'integer':
            vals['integer_value'] = int(value) if value is not None else 0
        elif item.value_type == 'boolean':
            vals['boolean_value'] = bool(value)

        if existing:
            existing.write(vals)
            return existing
        return Value.create(vals)

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Migratie van legacy myschool.config.item / myschool.ci.relation
    # ------------------------------------------------------------------
    # CurrentSchoolYear staat in legacy data per-org (vooral olvp), maar
    # we hebben de nieuwe SI-definitie als ``global`` geseed. Alle
    # legacy per-org waarden van deze key worden tijdens migratie
    # samengevoegd tot één globale waarde (de olvp-waarde wint, of
    # anders de eerst-gevonden actieve waarde).
    _LEGACY_FORCE_GLOBAL = {'CurrentSchoolYear'}
    _LEGACY_FORCE_GLOBAL_PREFER_ORG = 'olvp'

    @api.model
    def migrate_from_legacy(self):
        """Eenmalige (idempotente) migratie van legacy ``config_item`` +
        ``ci_relation`` naar de nieuwe SI-modellen.

        Veilig om meermaals te draaien: alle writes zoeken eerst een
        bestaand record op exact dezelfde (key, scope) en updaten dat
        in plaats van een duplicaat te maken.

        Returns: dict met telling per stap (handig voor de UI-melding).
        """
        ConfigItem = self.env.get('myschool.config.item')
        CiRelation = self.env.get('myschool.ci.relation')
        Value = self.env['myschool.settings.value']

        stats = {
            'items_created': 0, 'items_existing': 0,
            'values_created': 0, 'values_updated': 0,
            'values_skipped': 0, 'globals_created': 0,
            'errors': [],
        }
        if ConfigItem is None or CiRelation is None:
            stats['errors'].append(
                'Legacy modellen (myschool.config.item / .ci.relation) '
                'bestaan niet — niets te migreren.')
            return stats

        # ---------- Stap 1: SI-definities aanmaken voor elke key ----------
        legacy_names = sorted({
            n for n in ConfigItem.search([]).mapped('name') if n})
        for name in legacy_names:
            si = self.search([('key', '=', name)], limit=1)
            if si:
                stats['items_existing'] += 1
                continue

            # Determine value_type op basis van eerste niet-leeg sample
            sample = ConfigItem.search([('name', '=', name)], limit=1)
            if sample.string_value:
                vtype = 'string'
            elif sample.integer_value:
                vtype = 'integer'
            else:
                vtype = 'boolean'

            # Determine scope_kind op basis van legacy relations
            has_org = CiRelation.search_count([
                ('id_ci.name', '=', name),
                ('id_org', '!=', False),
            ])
            scope = 'org' if has_org else 'global'
            if name in self._LEGACY_FORCE_GLOBAL:
                scope = 'global'

            self.create({
                'key': name,
                'label': name,
                'description': sample.description or '',
                'value_type': vtype,
                'scope_kind': scope,
                'is_encrypted': sample.is_encrypted,
                'is_active': True,
            })
            stats['items_created'] += 1

        # ---------- Stap 2: per-org waarden uit ci.relation ----------
        relations = CiRelation.search([
            ('isactive', '=', True),
            ('id_org', '!=', False),
            ('id_ci', '!=', False),
        ])
        for rel in relations:
            key = rel.id_ci.name
            if not key:
                stats['values_skipped'] += 1
                continue
            si = self.search([('key', '=', key)], limit=1)
            if not si:
                stats['values_skipped'] += 1
                continue

            # SI's die in de catalogus als ``global`` staan, krijgen
            # geen per-org waarden — die worden in stap 3 als één
            # globale waarde samengevat.
            if si.scope_kind == 'global':
                stats['values_skipped'] += 1
                continue

            vals = {
                'settings_item_id': si.id,
                'org_id': rel.id_org.id,
                'is_active': True,
                'inherit_to_children': True,
            }
            if si.value_type == 'string':
                vals['string_value'] = rel.id_ci.string_value or False
            elif si.value_type == 'integer':
                vals['integer_value'] = rel.id_ci.integer_value or 0
            elif si.value_type == 'boolean':
                vals['boolean_value'] = bool(rel.id_ci.boolean_value)

            existing = Value.search([
                ('settings_item_id', '=', si.id),
                ('org_id', '=', rel.id_org.id),
                ('person_id', '=', False),
            ], limit=1)
            try:
                if existing:
                    existing.write(vals)
                    stats['values_updated'] += 1
                else:
                    Value.create(vals)
                    stats['values_created'] += 1
            except Exception as exc:
                stats['errors'].append(
                    f"{key}@{rel.id_org.name_short}: {exc}")
                stats['values_skipped'] += 1

        # ---------- Stap 3: forced-global keys (bv. CurrentSchoolYear) ----------
        # Voor elke key in _LEGACY_FORCE_GLOBAL: kies de waarde uit de
        # voorkeurs-org (olvp) of de eerst-gevonden actieve, en zet die
        # weg als globale settings.value (org_id=False).
        for key in self._LEGACY_FORCE_GLOBAL:
            si = self.search([('key', '=', key)], limit=1)
            if not si:
                continue
            # Pak eerst de voorkeurs-org
            preferred = CiRelation.search([
                ('id_ci.name', '=', key),
                ('id_org.name_short', '=', self._LEGACY_FORCE_GLOBAL_PREFER_ORG),
                ('isactive', '=', True),
            ], limit=1)
            chosen = preferred or CiRelation.search([
                ('id_ci.name', '=', key),
                ('isactive', '=', True),
            ], limit=1)
            if not chosen or not chosen.id_ci:
                continue

            vals = {
                'settings_item_id': si.id,
                'org_id': False,
                'person_id': False,
                'is_active': True,
            }
            if si.value_type == 'string':
                vals['string_value'] = chosen.id_ci.string_value or False
            elif si.value_type == 'integer':
                vals['integer_value'] = chosen.id_ci.integer_value or 0
            elif si.value_type == 'boolean':
                vals['boolean_value'] = bool(chosen.id_ci.boolean_value)

            existing = Value.search([
                ('settings_item_id', '=', si.id),
                ('org_id', '=', False),
                ('person_id', '=', False),
            ], limit=1)
            try:
                if existing:
                    existing.write(vals)
                else:
                    Value.create(vals)
                    stats['globals_created'] += 1
            except Exception as exc:
                stats['errors'].append(f"{key} (global): {exc}")

        _logger.info("SI-migratie afgerond: %s", stats)
        return stats

    def action_migrate_from_legacy(self):
        """UI-knop wrapper rond migrate_from_legacy(). Toont een
        notification met de telling."""
        stats = self.migrate_from_legacy()
        msg = (
            f"SI-definities: {stats['items_created']} aangemaakt, "
            f"{stats['items_existing']} bestonden al. "
            f"Waarden: {stats['values_created']} aangemaakt, "
            f"{stats['values_updated']} bijgewerkt, "
            f"{stats['globals_created']} globaal toegevoegd, "
            f"{stats['values_skipped']} overgeslagen.")
        if stats['errors']:
            msg += f"\nFouten: {len(stats['errors'])} (zie log)."
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Settings Items — migratie afgerond',
                'message': msg,
                'type': 'success' if not stats['errors'] else 'warning',
                'sticky': bool(stats['errors']),
            },
        }

    @api.constrains('scope_kind', 'value_ids')
    def _check_scope_consistency(self):
        """Zorg dat bestaande waarden niet conflicteren met het
        scope_kind van de definitie (bv. een 'global'-only SI met een
        per-org waarde)."""
        for item in self:
            for v in item.value_ids:
                if item.scope_kind == 'global' and (v.org_id or v.person_id):
                    raise ValidationError(_(
                        "SI '%(key)s' is 'Alleen globaal' maar heeft "
                        "een org/person-waarde."
                    ) % {'key': item.key})
                if item.scope_kind == 'org' and v.person_id:
                    raise ValidationError(_(
                        "SI '%(key)s' is 'Alleen per organisatie' maar "
                        "heeft een per-person waarde."
                    ) % {'key': item.key})
                if item.scope_kind == 'person' and v.org_id:
                    raise ValidationError(_(
                        "SI '%(key)s' is 'Alleen per persoon' maar "
                        "heeft een per-org waarde."
                    ) % {'key': item.key})
