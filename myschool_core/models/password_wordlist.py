"""Wachtwoord-woordenlijst — een herbruikbare set van eenvoudige
wachtwoorden waaruit een rule kan kiezen voor jongere leerlingen.

Wachtwoorden worden bewust opnieuw gebruikt (zoals afgesproken: leerlingen
passen typisch een cijfer aan). Geen unique constraint, geen used-tracking.
"""
from odoo import api, fields, models


class PasswordWordlist(models.Model):
    _name = 'myschool.password.wordlist'
    _description = 'Wachtwoord-woordenlijst'
    _order = 'list_type, difficulty, name'

    name = fields.Char(string='Naam', required=True)
    description = fields.Text(string='Omschrijving')
    is_active = fields.Boolean(string='Actief', default=True)

    list_type = fields.Selection(
        selection=[
            ('passwords', 'Volledige wachtwoorden'),
            ('words',     'Woorden (voor wachtzinnen)'),
        ],
        string='Type',
        required=True,
        default='passwords',
        help='"Volledige wachtwoorden": elke regel = één bruikbaar wachtwoord '
             '(jongere leerlingen). "Woorden": vocabulaire dat door templates '
             'in passphrase-mode gecombineerd wordt tot een wachtzin.',
    )

    difficulty = fields.Selection(
        selection=[
            ('very_easy', 'Heel makkelijk'),
            ('easy', 'Makkelijk'),
            ('normal', 'Normaal'),
        ],
        string='Moeilijkheidsgraad',
        default='easy',
        help='Indicatief label voor de complexiteit. Vooral relevant voor '
             '"Volledige wachtwoorden"-lijsten.',
    )

    content = fields.Text(
        string='Wachtwoorden',
        help='Eén wachtwoord per regel. Lege regels en regels die met # '
             'beginnen worden genegeerd.',
    )

    line_count = fields.Integer(
        string='Aantal wachtwoorden',
        compute='_compute_line_count',
        store=True,
    )

    @api.depends('content')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec._password_lines())

    def _password_lines(self):
        """Return the parsed list of wachtwoorden (skipping blanks/comments)."""
        self.ensure_one()
        if not self.content:
            return []
        out = []
        for raw in self.content.splitlines():
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            out.append(line)
        return out

    def pick_random(self):
        """Return one wachtwoord at random from the list (may be reused
        across calls — dat is by design)."""
        import secrets
        self.ensure_one()
        lines = self._password_lines()
        if not lines:
            return ''
        return secrets.choice(lines)

    def pick_words(self, count):
        """Pick ``count`` random woorden uit de lijst voor passphrase-
        compositie. Woorden mogen herhaald worden als de lijst kleiner
        is dan ``count`` (with-replacement). Returns lijst van strings.
        """
        import secrets
        self.ensure_one()
        lines = self._password_lines()
        if not lines or count <= 0:
            return []
        return [secrets.choice(lines) for _ in range(count)]
