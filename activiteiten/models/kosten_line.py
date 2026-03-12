from odoo import models, fields
from odoo.exceptions import UserError


class ActiviteitenKostenLine(models.Model):
    _name = 'activiteiten.kosten.line'
    _description = 'Activiteiten Kostenlijn'

    activiteit_id = fields.Many2one(
        'activiteiten.record', string='Activiteit',
        required=True, ondelete='cascade',
    )
    omschrijving = fields.Char(string='Omschrijving', required=True)
    bedrag = fields.Monetary(
        string='Bedrag',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='activiteit_id.currency_id',
    )
    is_auto = fields.Boolean(string='Automatisch', default=False)

    def unlink(self):
        if self.filtered('is_auto'):
            raise UserError("Automatische kostenlijnen (bv. Verzekering) kunnen niet verwijderd worden.")
        return super().unlink()
