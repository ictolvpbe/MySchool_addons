from odoo import models, fields, api
from odoo.exceptions import UserError


class StudentSelectLine(models.TransientModel):
    _name = 'drukwerk.student.select.line'
    _description = 'Student selectie lijn'

    wizard_id = fields.Many2one('drukwerk.student.select.wizard', required=True, ondelete='cascade')
    person_id = fields.Many2one('myschool.person', string='Leerling', required=True)
    person_name = fields.Char(related='person_id.name', string='Naam', store=True)
    klas_id = fields.Many2one('myschool.org', string='Klas')
    selected = fields.Boolean(string='Geselecteerd', default=True)


class StudentSelectWizard(models.TransientModel):
    _name = 'drukwerk.student.select.wizard'
    _description = 'Leerlingen selecteren'

    drukwerk_id = fields.Many2one('drukwerk.record', required=True)
    line_ids = fields.One2many('drukwerk.student.select.line', 'wizard_id', string='Leerlingen')
    display_line_ids = fields.Many2many(
        'drukwerk.student.select.line',
        compute='_compute_display_line_ids',
        string='Getoonde leerlingen',
    )
    selected_count = fields.Integer(compute='_compute_selected_count', string='Geselecteerd')
    total_count = fields.Integer(compute='_compute_selected_count', string='Totaal')
    readonly_mode = fields.Boolean(default=False)
    search_name = fields.Char(string='Zoek leerling')

    @api.depends('line_ids.selected')
    def _compute_selected_count(self):
        for wiz in self:
            wiz.total_count = len(wiz.line_ids)
            wiz.selected_count = len(wiz.line_ids.filtered('selected'))

    @api.depends('line_ids', 'line_ids.person_name', 'search_name')
    def _compute_display_line_ids(self):
        for wiz in self:
            search = (wiz.search_name or '').strip().lower()
            if not search:
                wiz.display_line_ids = wiz.line_ids
            else:
                wiz.display_line_ids = wiz.line_ids.filtered(
                    lambda l: search in (l.person_name or '').lower()
                )

    def action_select_all(self):
        if self.readonly_mode:
            raise UserError("De leerlingenselectie kan niet meer gewijzigd worden voor een afgeronde aanvraag.")
        self.line_ids.write({'selected': True})
        return self._reopen()

    def action_deselect_all(self):
        if self.readonly_mode:
            raise UserError("De leerlingenselectie kan niet meer gewijzigd worden voor een afgeronde aanvraag.")
        self.line_ids.write({'selected': False})
        return self._reopen()

    def action_confirm(self):
        """Apply selection back to the drukwerk record."""
        if self.readonly_mode or self.drukwerk_id.state == 'done':
            raise UserError("De leerlingenselectie kan niet meer gewijzigd worden voor een afgeronde aanvraag.")
        selected_persons = self.line_ids.filtered('selected').mapped('person_id')
        self.drukwerk_id.student_ids = [(6, 0, selected_persons.ids)]
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
