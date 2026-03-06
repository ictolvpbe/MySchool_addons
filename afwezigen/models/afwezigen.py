from datetime import datetime, time
from odoo import models, fields, api


class AfwezigenDashboard(models.Model):
    _name = 'myschool.afwezigen'
    _description = 'Afwezigen Dashboard'

    name = fields.Char(default='Afwezigen')

    @api.model
    def action_open_dashboard(self):
        today_start = datetime.combine(fields.Date.context_today(self), time.min)
        view_id = self.env.ref('afwezigen.view_afwezigen_list').id
        return {
            'type': 'ir.actions.act_window',
            'name': 'Afwezigen',
            'res_model': 'activiteiten.record',
            'view_mode': 'list,form',
            'views': [(view_id, 'list'), (False, 'form')],
            'domain': [
                ('state', 'in', ('approved', 's_code', 'vervanging', 'done')),
                '|',
                ('datetime', '=', False),
                ('datetime', '>=', str(today_start)),
            ],
            'context': {'create': False},
        }
