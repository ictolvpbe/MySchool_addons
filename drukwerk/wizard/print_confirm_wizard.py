from odoo import models, fields


class DrukwerkPrintConfirmWizard(models.TransientModel):
    _name = 'drukwerk.print.confirm.wizard'
    _description = 'Drukwerk: Bevestig afdruk'

    record_id = fields.Many2one(
        'drukwerk.record', string='Aanvraag', required=True, ondelete='cascade',
    )
    titel = fields.Char(related='record_id.titel', readonly=True)

    def action_open_pdf(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/drukwerk/print/{self.record_id.id}',
            'target': 'new',
        }

    def action_confirm_printed(self):
        self.ensure_one()
        self.record_id.action_mark_printed()
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}
