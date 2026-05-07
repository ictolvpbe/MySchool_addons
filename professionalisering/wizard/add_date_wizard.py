from odoo import models, fields, api
from odoo.exceptions import UserError


class AddDateWizard(models.TransientModel):
    _name = 'professionalisering.add.date.wizard'
    _description = 'Datum toevoegen aan professionalisering'

    record_id = fields.Many2one(
        'professionalisering.record', required=True, ondelete='cascade',
    )
    date = fields.Date(
        string='Datum', required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    cost = fields.Float(string='Kost (€)')

    def action_confirm(self):
        self.ensure_one()
        if not self.date:
            raise UserError("Kies een datum.")
        # Geen duplicates per aanvraag.
        existing = self.env['professionalisering.date.line'].search_count([
            ('professionalisering_id', '=', self.record_id.id),
            ('date', '=', self.date),
        ])
        if existing:
            raise UserError(
                f"De datum {self.date.strftime('%d/%m/%Y')} is al toegevoegd "
                f"aan deze aanvraag. Kies een andere datum."
            )
        self.env['professionalisering.date.line'].create({
            'professionalisering_id': self.record_id.id,
            'date': self.date,
            'cost': self.cost,
        })
        # Sluit enkel deze inner-dialog. De parent extra-info dialog blijft open;
        # de One2many (date_line_ids) ziet automatisch de nieuwe regel via Owl's
        # reactive cache zodra de focus terug op de parent ligt.
        return {'type': 'ir.actions.act_window_close'}
