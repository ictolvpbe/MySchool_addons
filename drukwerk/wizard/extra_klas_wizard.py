from odoo import models, fields, api
from odoo.exceptions import UserError


class ExtraKlasWizard(models.TransientModel):
    _name = 'drukwerk.extra.klas.wizard'
    _description = 'Extra klas toevoegen aan drukwerk'

    drukwerk_id = fields.Many2one('drukwerk.record', required=True, ondelete='cascade')
    school_id = fields.Many2one('myschool.org', related='drukwerk_id.school_id', readonly=True)
    school_klas_ids = fields.Many2many(
        'myschool.org',
        compute='_compute_school_klas_ids',
        string='Beschikbare klassen',
    )
    klas_ids = fields.Many2many(
        'myschool.org',
        'drukwerk_extra_klas_wiz_rel',
        'wiz_id', 'klas_id',
        string='Klassen toevoegen',
    )

    @api.depends('school_id')
    def _compute_school_klas_ids(self):
        OrgType = self.env['myschool.org.type']
        dept_type = OrgType.search([('name', '=', 'DEPARTMENT')], limit=1)
        PropRel = self.env['myschool.proprelation']
        for wiz in self:
            if not wiz.school_id or not dept_type:
                wiz.school_klas_ids = False
                continue
            lln_rels = PropRel.search([
                ('id_org_parent', '=', wiz.school_id.id),
                ('id_org.org_type_id', '=', dept_type.id),
                ('id_org.name_short', '=', 'lln'),
            ])
            lln_ids = lln_rels.mapped('id_org').ids
            if not lln_ids:
                wiz.school_klas_ids = False
                continue
            klas_rels = PropRel.search([
                ('id_org_parent', 'in', lln_ids),
                ('id_org', '!=', False),
            ])
            wiz.school_klas_ids = klas_rels.mapped('id_org')

    def action_confirm(self):
        self.ensure_one()
        if not self.klas_ids:
            raise UserError("Selecteer minstens één klas.")
        if self.drukwerk_id.state == 'done':
            raise UserError("Klassen kunnen niet meer toegevoegd worden voor een afgeronde aanvraag.")
        self.drukwerk_id.klas_ids = [(4, k.id) for k in self.klas_ids]
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}
