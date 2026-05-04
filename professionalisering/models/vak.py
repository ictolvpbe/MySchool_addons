from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProfessionaliseringVak(models.Model):
    """Vakken die geselecteerd kunnen worden bij een professionalisering-aanvraag.
    Beheerbaar via MySchool Admin → Master Data → Vakken."""

    _name = 'professionalisering.vak'
    _description = 'Vak voor professionalisering'
    _order = 'sequence, name'

    name = fields.Char(string='Naam', required=True, translate=True)
    code = fields.Char(
        string='Code',
        required=True,
        copy=False,
        index=True,
        help='Unieke technische identificatie. Niet wijzigen op bestaande '
             'records — bestaande aanvragen verwijzen ernaar.',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    is_other = fields.Boolean(
        string='Is "Andere"',
        help='Bij selecteren van dit vak wordt het vrije tekstveld '
             '"Vermelding vak" verplicht voor de aanvrager.',
    )

    @api.constrains('code')
    def _check_code_unique(self):
        for record in self:
            duplicate = self.search_count([
                ('code', '=', record.code),
                ('id', '!=', record.id),
            ])
            if duplicate:
                raise ValidationError(
                    f"Er bestaat al een vak met code '{record.code}'. "
                    f"De code moet uniek zijn."
                )
