"""Wachtwoordbeleid — bundel van regels die per persoon-type, rol en
leeftijdsbereik bepalen hoe het wachtwoord wordt gekozen of gegenereerd.

Resolutiestroom (zie ``_resolve_for_person``):
    persoon → school (via parent-chain in PERSON-TREE)
    school → policy → walk rule_ids in sequence-order
    eerste match (op person_type, rol, leeftijd) wint;
    valt niets te matchen → de regel met ``is_default_rule=True`` wint;
    geen default-rule → fall-through naar de eerste systeem-default policy.

Aangenomen modellen (lazy-resolved zodat we niet hard couplen):
    myschool.person          — birth_date, person_type_id
    myschool.proprelation    — id_org / id_person met PERSON-TREE
    myschool.org             — org_type_id (SCHOOL), password_policy_id
"""
from datetime import date
import logging
import secrets
import string

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


# ============================================================================
# Policy
# ============================================================================

class PasswordPolicy(models.Model):
    _name = 'myschool.password.policy'
    _description = 'Wachtwoordbeleid'
    _order = 'is_system_default desc, name'

    name = fields.Char(string='Naam', required=True)
    description = fields.Text(string='Omschrijving')
    is_active = fields.Boolean(string='Actief', default=True)

    is_system_default = fields.Boolean(
        string='Systeemdefault',
        default=False,
        help='Wanneer een school geen eigen beleid heeft, valt het '
             'systeem terug op het beleid met deze vlag. Slechts één '
             'actief beleid mag deze vlag dragen.',
    )

    rule_ids = fields.One2many(
        'myschool.password.policy.rule',
        'policy_id',
        string='Regels',
        copy=True,
    )

    school_ids = fields.One2many(
        'myschool.org',
        'password_policy_id',
        string='Gekoppelde scholen',
        help='Scholen waarvoor dit beleid actief is. Een beleid kan op '
             'meerdere scholen toegepast worden; een school kiest één beleid.',
    )

    rule_count = fields.Integer(compute='_compute_counts', string='# regels')
    school_count = fields.Integer(compute='_compute_counts', string='# scholen')

    @api.depends('rule_ids', 'school_ids')
    def _compute_counts(self):
        for rec in self:
            rec.rule_count = len(rec.rule_ids)
            rec.school_count = len(rec.school_ids)

    @api.constrains('is_system_default', 'is_active')
    def _check_single_default(self):
        for rec in self:
            if rec.is_system_default and rec.is_active:
                duplicates = self.search([
                    ('id', '!=', rec.id),
                    ('is_system_default', '=', True),
                    ('is_active', '=', True),
                ], limit=1)
                if duplicates:
                    raise ValidationError(_(
                        'Er kan maar één actief beleid de '
                        '"Systeemdefault"-vlag dragen. Conflict met: %s'
                    ) % duplicates.name)

    # -- Resolution --------------------------------------------------------

    @api.model
    def _system_default(self):
        """Return the policy flagged as system-default (or empty recordset)."""
        return self.search([
            ('is_active', '=', True),
            ('is_system_default', '=', True),
        ], limit=1)

    @api.model
    def _school_for_person(self, person):
        """Walk parent-org chain via PERSON-TREE → ORG-TREE until we hit
        a SCHOOL-type org. Returns the SCHOOL org recordset (or empty).
        """
        if not person or 'myschool.proprelation' not in self.env:
            return self.env['myschool.org']

        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']

        person_tree_type = PropRelationType.search(
            [('name', '=', 'PERSON-TREE')], limit=1)
        if not person_tree_type:
            return self.env['myschool.org']

        rels = PropRelation.search([
            ('proprelation_type_id', '=', person_tree_type.id),
            ('id_person', '=', person.id),
            ('id_org', '!=', False),
            ('is_active', '=', True),
        ], limit=20)
        if not rels:
            return self.env['myschool.org']

        org_tree_type = PropRelationType.search(
            [('name', '=', 'ORG-TREE')], limit=1)

        # Walk each org upward; first SCHOOL-type ancestor we hit wins.
        seen = set()
        for rel in rels:
            org = rel.id_org
            cur = org
            depth = 0
            while cur and cur.id not in seen and depth < 20:
                seen.add(cur.id)
                if cur.org_type_id and cur.org_type_id.name == 'SCHOOL':
                    return cur
                # Find parent via ORG-TREE
                if not org_tree_type:
                    break
                parent_rel = PropRelation.search([
                    ('proprelation_type_id', '=', org_tree_type.id),
                    ('id_org', '=', cur.id),
                    ('id_org_parent', '!=', False),
                    ('is_active', '=', True),
                ], limit=1) or PropRelation.search([
                    ('proprelation_type_id', '=', org_tree_type.id),
                    ('id_org_child', '=', cur.id),
                    ('id_org_parent', '!=', False),
                    ('is_active', '=', True),
                ], limit=1)
                if not parent_rel:
                    break
                cur = parent_rel.id_org_parent
                depth += 1
        return self.env['myschool.org']

    def _resolve_for_person(self, person):
        """Return the matching ``myschool.password.policy.rule`` for the
        given person, walking this policy's rule_ids. Falls back to
        ``is_default_rule`` if no match. Returns empty if even no
        default exists.
        """
        self.ensure_one()
        person_age = _compute_age(getattr(person, 'birth_date', False))
        person_type_id = (person.person_type_id.id
                          if getattr(person, 'person_type_id', False) else None)
        person_role_ids = _person_role_ids(self.env, person)

        ordered = self.rule_ids.sorted(lambda r: (r.sequence, r.id))
        default_rule = ordered.filtered(lambda r: r.is_default_rule)[:1]
        candidates = ordered - default_rule

        for rule in candidates:
            if rule._matches(person_type_id, person_role_ids, person_age):
                return rule
        return default_rule  # may itself be empty if not configured

    @api.model
    def _resolve_rule_for_person(self, person):
        """Top-level entry point: find school, get school's policy (or
        system default), and resolve the rule. Returns empty recordset
        if no applicable rule was found anywhere.
        """
        school = self._school_for_person(person)
        policy = school.password_policy_id if school else self.env['myschool.password.policy']
        if not policy:
            policy = self._system_default()
        if not policy:
            return self.env['myschool.password.policy.rule']
        return policy._resolve_for_person(person)

    @api.model
    def generate_password_for_person(self, person):
        """Convenience: resolve + generate. Returns a password string,
        or raises UserError when nothing applies.
        """
        rule = self._resolve_rule_for_person(person)
        if not rule:
            raise UserError(_(
                "Geen wachtwoordbeleid van toepassing voor %s. "
                "Stel een systeemdefault-beleid in met een default-rule."
            ) % (person.display_name or person.name or person.id))
        return rule.generate_password()


# ============================================================================
# Rule
# ============================================================================

class PasswordPolicyRule(models.Model):
    _name = 'myschool.password.policy.rule'
    _description = 'Wachtwoordbeleid-regel'
    _order = 'policy_id, sequence, id'

    policy_id = fields.Many2one(
        'myschool.password.policy',
        string='Beleid',
        required=True,
        ondelete='cascade',
    )

    name = fields.Char(string='Naam', required=True)
    sequence = fields.Integer(string='Volgorde', default=10)

    # -- Match criteria (allemaal optioneel; leeg = match-alles) ------------

    person_type_ids = fields.Many2many(
        'myschool.person.type',
        string='Persoon-types',
        help='Indien gevuld: alleen personen met één van deze types matchen.',
    )

    role_ids = fields.Many2many(
        'myschool.role',
        string='Rollen',
        help='Indien gevuld: alleen personen met (minstens) één van deze '
             'rollen matchen (via actieve PERSON-TREE proprelations).',
    )

    min_age = fields.Integer(
        string='Min. leeftijd',
        default=0,
        help='0 = geen ondergrens. Leeftijd wordt berekend op '
             'basis van person.birth_date.',
    )

    max_age = fields.Integer(
        string='Max. leeftijd',
        default=0,
        help='0 = geen bovengrens.',
    )

    is_default_rule = fields.Boolean(
        string='Default-regel (vangregel)',
        default=False,
        help='Deze regel wordt gebruikt als geen enkele andere regel '
             'binnen het beleid matcht. Slechts één vangregel per beleid.',
    )

    # -- Generatie-mode ---------------------------------------------------

    mode = fields.Selection(
        selection=[
            ('generated', 'Gegenereerd via template'),
            ('wordlist', 'Uit woordenlijst'),
        ],
        string='Modus',
        required=True,
        default='generated',
    )

    # Voor 'generated': verwijst naar een herbruikbaar template dat de
    # volledige complexiteits-configuratie bundelt. Meerdere regels en
    # meerdere policies kunnen hetzelfde template hergebruiken.
    template_id = fields.Many2one(
        'myschool.password.template',
        string='Wachtwoord-template',
        ondelete='restrict',
        help='Kies een template met de gewenste complexiteit. Beheer '
             'templates in Instellingen → Wachtwoordbeleid → Templates.',
    )

    # Inline-velden (legacy / fallback). Worden gebruikt wanneer mode is
    # 'generated' maar geen template_id is gekozen. Templates zijn de
    # aanbevolen route.
    gen_length = fields.Integer(string='Lengte (inline)', default=12)
    gen_lowercase = fields.Integer(string='Min. kleine letters (inline)', default=2)
    gen_uppercase = fields.Integer(string='Min. hoofdletters (inline)', default=2)
    gen_digits = fields.Integer(string='Min. cijfers (inline)', default=2)
    gen_specials = fields.Integer(string='Min. speciale tekens (inline)', default=1)
    gen_specials_chars = fields.Char(
        string='Speciale-teken-set (inline)',
        default='!@#$%&*?',
    )

    # Voor 'wordlist'
    wordlist_id = fields.Many2one(
        'myschool.password.wordlist',
        string='Woordenlijst',
        ondelete='restrict',
    )

    # -- Constraints -----------------------------------------------------

    @api.constrains('policy_id', 'is_default_rule')
    def _check_single_default_rule(self):
        for rec in self:
            if rec.is_default_rule:
                others = self.search([
                    ('id', '!=', rec.id),
                    ('policy_id', '=', rec.policy_id.id),
                    ('is_default_rule', '=', True),
                ], limit=1)
                if others:
                    raise ValidationError(_(
                        'Per beleid kan slechts één default-regel bestaan. '
                        'Conflict met regel: %s'
                    ) % others.name)

    @api.constrains('mode', 'wordlist_id', 'template_id',
                    'gen_length', 'gen_lowercase', 'gen_uppercase',
                    'gen_digits', 'gen_specials')
    def _check_mode_consistency(self):
        for rec in self:
            if rec.mode == 'wordlist' and not rec.wordlist_id:
                raise ValidationError(_(
                    'Regel "%s": selecteer een woordenlijst voor modus '
                    '"Uit woordenlijst".') % rec.name)
            if rec.mode == 'generated' and not rec.template_id:
                # Inline-validatie alleen als er geen template gekozen is —
                # bij template-modus valideert het template zelf.
                if rec.gen_length < 4:
                    raise ValidationError(_(
                        'Regel "%s": lengte moet minstens 4 zijn (of kies een template).'
                    ) % rec.name)
                total_min = (rec.gen_lowercase + rec.gen_uppercase
                             + rec.gen_digits + rec.gen_specials)
                if total_min > rec.gen_length:
                    raise ValidationError(_(
                        'Regel "%s": som van minimum-aantallen (%d) '
                        'overschrijdt de totale lengte (%d).'
                    ) % (rec.name, total_min, rec.gen_length))

    @api.constrains('min_age', 'max_age')
    def _check_age_range(self):
        for rec in self:
            if rec.min_age < 0 or rec.max_age < 0:
                raise ValidationError(_('Leeftijden mogen niet negatief zijn.'))
            if rec.max_age and rec.min_age and rec.max_age < rec.min_age:
                raise ValidationError(_(
                    'Max. leeftijd (%d) is kleiner dan min. leeftijd (%d).'
                ) % (rec.max_age, rec.min_age))

    # -- Matching ---------------------------------------------------------

    def _matches(self, person_type_id, person_role_ids, person_age):
        """Return True if this rule matches the given person attributes."""
        self.ensure_one()
        # person_type filter
        if self.person_type_ids:
            if not person_type_id or person_type_id not in self.person_type_ids.ids:
                return False
        # role filter
        if self.role_ids:
            if not person_role_ids or not (set(person_role_ids) & set(self.role_ids.ids)):
                return False
        # age filter
        if self.min_age or self.max_age:
            if person_age is None:
                # No birth_date — can't evaluate. Conservatieve keuze:
                # rules met age-filter slaan we over → fall-through naar default.
                return False
            if self.min_age and person_age < self.min_age:
                return False
            if self.max_age and person_age > self.max_age:
                return False
        return True

    # -- Generation -------------------------------------------------------

    def generate_password(self):
        """Generate / pick a wachtwoord according to this rule.

        - mode='wordlist'  → pick random uit wordlist_id
        - mode='generated' → prefer template_id; valt terug op de
                             inline gen_* velden wanneer geen template gekozen is.
        """
        self.ensure_one()
        if self.mode == 'wordlist':
            if not self.wordlist_id:
                raise UserError(_('Regel "%s" heeft geen woordenlijst.') % self.name)
            pwd = self.wordlist_id.pick_random()
            if not pwd:
                raise UserError(_(
                    'Woordenlijst "%s" is leeg.') % self.wordlist_id.name)
            return pwd
        # mode == 'generated'
        if self.template_id:
            return self.template_id.generate()
        return self._generate_complex()

    def _generate_complex(self):
        """Generate a random password that satisfies the minimum counts
        per character class. Uses ``secrets`` for cryptographic randomness.
        """
        self.ensure_one()
        lower = string.ascii_lowercase
        upper = string.ascii_uppercase
        digits = string.digits
        specials = self.gen_specials_chars or '!@#$%&*?'

        chars = []
        chars.extend(secrets.choice(lower) for _ in range(self.gen_lowercase))
        chars.extend(secrets.choice(upper) for _ in range(self.gen_uppercase))
        chars.extend(secrets.choice(digits) for _ in range(self.gen_digits))
        chars.extend(secrets.choice(specials) for _ in range(self.gen_specials))

        # Determine the pool for the remaining slots: union of classes
        # whose minimum > 0 (admins-defined). If alle minima 0, accept all.
        pool = ''
        if self.gen_lowercase > 0: pool += lower
        if self.gen_uppercase > 0: pool += upper
        if self.gen_digits > 0:    pool += digits
        if self.gen_specials > 0:  pool += specials
        if not pool:
            pool = lower + upper + digits + specials

        remaining = self.gen_length - len(chars)
        chars.extend(secrets.choice(pool) for _ in range(remaining))

        # Shuffle deterministically-random; ``secrets`` lacks shuffle,
        # so we do a Fisher-Yates pass using token_bytes for indices.
        for i in range(len(chars) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            chars[i], chars[j] = chars[j], chars[i]
        return ''.join(chars)


# ============================================================================
# Helpers
# ============================================================================

def _compute_age(birth_date):
    """Return age in years, or None when birth_date is empty/invalid."""
    if not birth_date:
        return None
    if isinstance(birth_date, str):
        try:
            birth_date = fields.Date.from_string(birth_date)
        except Exception:
            return None
    today = date.today()
    years = today.year - birth_date.year
    # If we haven't reached the birthday this year, subtract 1.
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return max(years, 0)


def _person_role_ids(env, person):
    """Return list of role ids actively linked to the person via
    PERSON-TREE proprelations. Empty list when not resolvable."""
    if 'myschool.proprelation' not in env or 'myschool.proprelation.type' not in env:
        return []
    person_tree_type = env['myschool.proprelation.type'].search(
        [('name', '=', 'PERSON-TREE')], limit=1)
    if not person_tree_type:
        return []
    rels = env['myschool.proprelation'].search([
        ('proprelation_type_id', '=', person_tree_type.id),
        ('id_person', '=', person.id),
        ('id_role', '!=', False),
        ('is_active', '=', True),
    ])
    return list({r.id_role.id for r in rels})
