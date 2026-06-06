from odoo import models, fields, api


class MyschoolDataDomain(models.Model):
    """Catalogus van data-domeinen voor de data-locatie/privacy-matrix
    (SRVMGR-4).

    Een data-domein is een categorie data die per server lokaal kan staan of
    via API bij een andere server opgehaald wordt — bv. PII, bedrijven,
    org-structuur. De ``is_pii``-vlag sluit aan op de PII-classificatie uit de
    toekomst-architectuur.
    """

    _name = 'myschool.data.domain'
    _description = 'Data Domain'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        string='Code', required=True,
        help='Technische sleutel (uniek) voor automatisering.')
    is_pii = fields.Boolean(
        string='Contains PII', tracking=True,
        help='Bevat persoonsgegevens — relevant voor de privacy-afweging '
             'lokaal vs. ophalen via API.')
    description = fields.Text()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint('UNIQUE(code)', 'Data domain code must be unique.')

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for domain in self:
            domain.display_name = (
                f'{domain.name} [{domain.code}]' if domain.code else domain.name)
