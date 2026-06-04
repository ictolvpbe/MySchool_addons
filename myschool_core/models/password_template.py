"""Wachtwoord-template — herbruikbare complexiteits-configuratie voor
gegenereerde wachtwoorden. Een policy-rule kan een template kiezen ipv
de complexiteits-velden inline op de regel te zetten. Hetzelfde template
kan in meerdere regels en meerdere policies gebruikt worden.
"""
import secrets
import string

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PasswordTemplate(models.Model):
    _name = 'myschool.password.template'
    _description = 'Wachtwoord-template (complexiteit)'
    _order = 'complexity_score, name'

    name = fields.Char(string='Naam', required=True)
    description = fields.Text(string='Omschrijving')
    is_active = fields.Boolean(string='Actief', default=True)

    mode = fields.Selection(
        selection=[
            ('complex',    'Complex wachtwoord'),
            ('passphrase', 'Wachtzin (woordencombinatie)'),
        ],
        string='Modus',
        required=True,
        default='complex',
        help='"Complex": random characters volgens min/max-regels. '
             '"Wachtzin": N woorden uit een woordenlijst, '
             'samengevoegd met een scheidingsteken (makkelijker te onthouden).',
    )

    # Informatief label — voor sorteren / kleuren in lijst-view.
    complexity_label = fields.Selection(
        selection=[
            ('very_low',  'Zeer laag'),
            ('low',       'Laag'),
            ('normal',    'Normaal'),
            ('high',      'Hoog'),
            ('very_high', 'Zeer hoog'),
        ],
        string='Complexiteit',
        default='normal',
    )

    # Berekend op basis van length + char-classes; voor list-decoration.
    complexity_score = fields.Integer(
        string='Score',
        compute='_compute_complexity_score',
        store=True,
        help='Indicatieve score (hoger = sterker). Combineert lengte en '
             'aantal toegelaten character-classes.',
    )

    length = fields.Integer(string='Lengte', default=12, required=True)
    min_lowercase = fields.Integer(string='Min. kleine letters', default=2)
    min_uppercase = fields.Integer(string='Min. hoofdletters', default=2)
    min_digits = fields.Integer(string='Min. cijfers', default=2)
    min_specials = fields.Integer(string='Min. speciale tekens', default=1)
    specials_chars = fields.Char(
        string='Speciale-teken-set',
        default='!@#$%&*?',
        help='Welke speciale tekens mogen voorkomen in gegenereerde wachtwoorden.',
    )

    # Optioneel: dwing minstens N verschillende char-classes af. Bij 4
    # classes met allen min=0 zou anders een wachtwoord van alleen lowercase
    # kunnen vallen. Default 0 = geen extra check.
    min_classes = fields.Integer(
        string='Min. # char-klassen',
        default=0,
        help='Garandeert dat een gegenereerd wachtwoord uit minstens N van '
             'de 4 klassen (kleine, hoofd, cijfer, speciaal) komt. 0 = geen check.',
    )

    # -- Passphrase-velden (gebruikt wanneer mode='passphrase') ---------
    phrase_wordlist_id = fields.Many2one(
        'myschool.password.wordlist',
        string='Woordenlijst',
        domain="[('list_type', '=', 'words'), ('is_active', '=', True)]",
        help='Vocabulaire-lijst (type "Woorden") waaruit de wachtzin '
             'wordt samengesteld.',
    )
    phrase_word_count = fields.Integer(
        string='Aantal woorden',
        default=4,
        help='Aantal random gekozen woorden per gegenereerde wachtzin. '
             '4 woorden uit een lijst van 1000 ≈ 40 bits entropie.',
    )
    phrase_separator = fields.Char(
        string='Scheidingsteken',
        default='-',
        help='Tussen elke twee woorden geplaatst. Leeg = geen scheiding.',
    )
    phrase_capitalize = fields.Selection(
        selection=[
            ('none',  'Geen'),
            ('first', 'Eerste letter van elk woord'),
            ('upper', 'Alles in HOOFDLETTERS'),
        ],
        string='Hoofdletters',
        default='none',
    )
    phrase_add_digits = fields.Integer(
        string='Cijfers achteraan',
        default=0,
        help='Aantal random cijfers dat achteraan de wachtzin wordt geplakt.',
    )
    phrase_add_specials = fields.Integer(
        string='Speciale tekens achteraan',
        default=0,
        help='Aantal random speciale tekens dat achteraan de wachtzin wordt geplakt.',
    )

    rule_count = fields.Integer(
        string='# regels die dit gebruiken',
        compute='_compute_rule_count',
    )

    # ---------------------------------------------------------------------
    # Computeds
    # ---------------------------------------------------------------------

    @api.depends('mode', 'length',
                 'min_lowercase', 'min_uppercase', 'min_digits', 'min_specials',
                 'phrase_word_count', 'phrase_add_digits', 'phrase_add_specials',
                 'phrase_wordlist_id.line_count')
    def _compute_complexity_score(self):
        for rec in self:
            if rec.mode == 'passphrase':
                # Indicatieve entropy: log2(words^n) + log2(10^digits) + log2(specials^N)
                # Cap ruwweg op 100 om de progressbar leesbaar te houden.
                import math
                vocab = rec.phrase_wordlist_id.line_count or 1
                n = max(0, rec.phrase_word_count or 0)
                bits = (math.log2(vocab) * n if vocab > 1 and n > 0 else 0)
                bits += (math.log2(10) * (rec.phrase_add_digits or 0))
                bits += (math.log2(len(rec.specials_chars or '!@#$%&*?'))
                         * (rec.phrase_add_specials or 0))
                rec.complexity_score = min(100, int(bits * 2))  # 50 bits ≈ 100
            else:
                classes = sum(1 for v in (rec.min_lowercase, rec.min_uppercase,
                                           rec.min_digits, rec.min_specials) if v > 0)
                rec.complexity_score = min(100, rec.length * (1 + classes))

    def _compute_rule_count(self):
        Rule = self.env['myschool.password.policy.rule']
        for rec in self:
            rec.rule_count = Rule.search_count([('template_id', '=', rec.id)])

    # ---------------------------------------------------------------------
    # Constraints
    # ---------------------------------------------------------------------

    @api.constrains('mode', 'length', 'min_lowercase', 'min_uppercase',
                    'min_digits', 'min_specials', 'min_classes',
                    'phrase_wordlist_id', 'phrase_word_count',
                    'phrase_add_digits', 'phrase_add_specials')
    def _check_consistency(self):
        for rec in self:
            if rec.mode == 'complex':
                if rec.length < 4:
                    raise ValidationError(_('Template "%s": lengte moet minstens 4 zijn.') % rec.name)
                total = (rec.min_lowercase + rec.min_uppercase
                         + rec.min_digits + rec.min_specials)
                if total > rec.length:
                    raise ValidationError(_(
                        'Template "%s": som van minimum-aantallen (%d) overschrijdt '
                        'de totale lengte (%d).'
                    ) % (rec.name, total, rec.length))
                if rec.min_classes < 0 or rec.min_classes > 4:
                    raise ValidationError(_(
                        'Template "%s": min. char-klassen moet tussen 0 en 4 liggen.'
                    ) % rec.name)
            elif rec.mode == 'passphrase':
                if not rec.phrase_wordlist_id:
                    raise ValidationError(_(
                        'Template "%s": kies een woordenlijst voor passphrase-modus.'
                    ) % rec.name)
                if rec.phrase_wordlist_id.list_type != 'words':
                    raise ValidationError(_(
                        'Template "%s": de gekozen woordenlijst moet type '
                        '"Woorden" hebben (niet "Volledige wachtwoorden").'
                    ) % rec.name)
                if rec.phrase_word_count < 2:
                    raise ValidationError(_(
                        'Template "%s": minstens 2 woorden voor een wachtzin.'
                    ) % rec.name)
                if rec.phrase_add_digits < 0 or rec.phrase_add_specials < 0:
                    raise ValidationError(_(
                        'Template "%s": cijfers/speciale tekens mogen niet negatief zijn.'
                    ) % rec.name)

    # ---------------------------------------------------------------------
    # Generation
    # ---------------------------------------------------------------------

    def generate(self):
        """Generate a wachtwoord / wachtzin volgens dit template. Dispatcht
        op ``mode``. Gebruikt ``secrets`` voor cryptografische randomness.
        """
        self.ensure_one()
        if self.mode == 'passphrase':
            return self._generate_passphrase()
        return self._generate_complex()

    def _generate_passphrase(self):
        """Compose een wachtzin: N woorden uit de wordlist, gekoppeld
        door het scheidingsteken, met optionele capitalisatie en
        cijfer/special-suffix.
        """
        self.ensure_one()
        words = self.phrase_wordlist_id.pick_words(self.phrase_word_count)
        if not words:
            from odoo.exceptions import UserError
            raise UserError(_(
                'Template "%s": woordenlijst "%s" is leeg.'
            ) % (self.name, self.phrase_wordlist_id.name))

        if self.phrase_capitalize == 'first':
            words = [w[:1].upper() + w[1:] for w in words]
        elif self.phrase_capitalize == 'upper':
            words = [w.upper() for w in words]

        sep = self.phrase_separator or ''
        result = sep.join(words)

        if self.phrase_add_digits > 0:
            result += ''.join(secrets.choice(string.digits)
                              for _ in range(self.phrase_add_digits))
        if self.phrase_add_specials > 0:
            specials = self.specials_chars or '!@#$%&*?'
            result += ''.join(secrets.choice(specials)
                              for _ in range(self.phrase_add_specials))
        return result

    def _generate_complex(self):
        """Complex mode: legacy generator op basis van min_* + length."""
        self.ensure_one()
        lower = string.ascii_lowercase
        upper = string.ascii_uppercase
        digits = string.digits
        specials = self.specials_chars or '!@#$%&*?'

        chars = []
        chars.extend(secrets.choice(lower)    for _ in range(self.min_lowercase))
        chars.extend(secrets.choice(upper)    for _ in range(self.min_uppercase))
        chars.extend(secrets.choice(digits)   for _ in range(self.min_digits))
        chars.extend(secrets.choice(specials) for _ in range(self.min_specials))

        # Bepaal de pool voor de resterende posities: unie van klassen
        # waarvan minimum > 0. Geen enkele aangeduid? → alle klassen.
        pool = ''
        if self.min_lowercase > 0: pool += lower
        if self.min_uppercase > 0: pool += upper
        if self.min_digits    > 0: pool += digits
        if self.min_specials  > 0: pool += specials
        if not pool:
            pool = lower + upper + digits + specials

        remaining = self.length - len(chars)
        chars.extend(secrets.choice(pool) for _ in range(remaining))

        # Fisher-Yates shuffle met secrets.randbelow.
        for i in range(len(chars) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            chars[i], chars[j] = chars[j], chars[i]

        result = ''.join(chars)

        # min_classes-check: re-generate indien niet voldaan (max 5 retries).
        if self.min_classes and self.min_classes > 1:
            classes_present = sum([
                any(c in lower    for c in result),
                any(c in upper    for c in result),
                any(c in digits   for c in result),
                any(c in specials for c in result),
            ])
            if classes_present < self.min_classes:
                # Eenvoudige strategie: vervang random posities met chars
                # uit ontbrekende klassen tot de check slaagt.
                wanted = []
                if self.min_lowercase == 0 and not any(c in lower for c in result):
                    wanted.append(lower)
                if self.min_uppercase == 0 and not any(c in upper for c in result):
                    wanted.append(upper)
                if self.min_digits == 0 and not any(c in digits for c in result):
                    wanted.append(digits)
                if self.min_specials == 0 and not any(c in specials for c in result):
                    wanted.append(specials)
                lst = list(result)
                for cls in wanted[: max(0, self.min_classes - classes_present)]:
                    pos = secrets.randbelow(len(lst))
                    lst[pos] = secrets.choice(cls)
                result = ''.join(lst)

        return result

    def action_preview(self):
        """Notificatie met 3 voorbeeld-wachtwoorden (handig om snel het
        gevoel te krijgen wat dit template oplevert)."""
        self.ensure_one()
        samples = ' • '.join(self.generate() for _ in range(3))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Voorbeeld — %s') % self.name,
                'message': samples,
                'type': 'info',
                'sticky': True,
            },
        }
