"""Audit-log voor drukwerkverwijderingen.

Wordt door de directie gebruikt om te zien wie het meeste aanvragen
ingediend heeft en wie het meeste fouten heeft moeten rechtzetten
(verwijderingen).
"""
from odoo import models, fields


class DrukwerkAuditLog(models.Model):
    _name = 'drukwerk.audit.log'
    _description = 'Drukwerk audit-log'
    _order = 'create_date desc'

    actor_id = fields.Many2one(
        'res.users', string='Gebruiker', ondelete='set null',
        help='Gebruiker die de actie uitvoerde. Wordt null als de '
             'gebruiker later verwijderd wordt; de naam blijft in '
             'actor_name bewaard.',
    )
    actor_name = fields.Char(
        string='Gebruikersnaam', help='Naam op moment van actie (blijft '
        'bewaard ook al wordt gebruiker verwijderd).',
    )
    record_name = fields.Char(
        string='Drukwerk', required=True,
        help='Referentie van het verwijderde drukwerk (DWK-####).',
    )
    record_titel = fields.Char(string='Titel')
    school_company_id = fields.Many2one(
        'res.company', string='School', ondelete='set null',
    )
    action = fields.Selection([
        ('delete', 'Verwijderd'),
    ], string='Actie', required=True, default='delete')
    state_before = fields.Char(
        string='Status voor verwijdering',
        help='In welke fase de aanvraag stond op moment van verwijdering. '
             'Helpt te zien of het om foute concepten dan wel om al-'
             'ingediende aanvragen gaat.',
    )
