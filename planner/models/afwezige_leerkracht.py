from odoo import models, fields, tools


class AfwezigeLeerkracht(models.Model):
    _name = 'planner.afwezige.leerkracht'
    _description = 'Afwezigen (vanuit activiteiten)'
    _auto = False
    _order = 'datum asc'

    leerkracht_id = fields.Many2one('myschool.person', string='Leerkracht', readonly=True)
    activiteit_id = fields.Many2one('activiteiten.record', string='Activiteit', readonly=True)
    titel = fields.Char(string='Activiteit titel', readonly=True)
    school_id = fields.Many2one('myschool.org', string='School', readonly=True)
    datum = fields.Datetime(string='Datum', readonly=True)
    datum_end = fields.Datetime(string='Einde', readonly=True)
    state = fields.Selection([
        ('approved', 'Goedgekeurd'),
        ('s_code', 'S-Code'),
        ('vervanging', 'Vervanging'),
        ('done', 'Afgerond'),
    ], string='Status', readonly=True)
    klas_id = fields.Many2one('myschool.org', string='Klas', readonly=True)
    record_type = fields.Selection([
        ('leerkracht', 'Leerkracht'),
        ('klas', 'Klas'),
    ], string='Type', readonly=True)

    def action_plan_vervanging(self):
        self.ensure_one()
        ctx = {
            'default_titel': f'Vervanging {self.leerkracht_id.display_name or self.klas_id.display_name} - {self.titel}',
            'default_inhaal_date': self.datum and self.datum.strftime('%Y-%m-%d'),
        }
        if self.leerkracht_id:
            ctx['default_leerkracht_id'] = self.leerkracht_id.id
        return {
            'type': 'ir.actions.act_window',
            'name': 'Inhaalmoment plannen',
            'res_model': 'planner.record',
            'view_mode': 'form',
            'target': 'current',
            'context': ctx,
        }

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    rel.person_id AS leerkracht_id,
                    NULL::integer AS klas_id,
                    a.id AS activiteit_id,
                    a.titel AS titel,
                    a.school_id AS school_id,
                    a.datetime AS datum,
                    a.datetime_end AS datum_end,
                    a.state AS state,
                    'leerkracht' AS record_type
                FROM activiteiten_record a
                JOIN activiteiten_record_leerkracht_rel rel
                    ON rel.record_id = a.id
                WHERE a.state IN ('approved', 's_code', 'vervanging', 'done')
                UNION ALL
                SELECT
                    (SELECT COUNT(*) FROM activiteiten_record_leerkracht_rel) + row_number() OVER () AS id,
                    NULL::integer AS leerkracht_id,
                    krel.org_id AS klas_id,
                    a.id AS activiteit_id,
                    a.titel AS titel,
                    a.school_id AS school_id,
                    a.datetime AS datum,
                    a.datetime_end AS datum_end,
                    a.state AS state,
                    'klas' AS record_type
                FROM activiteiten_record a
                JOIN activiteiten_record_klas_rel krel
                    ON krel.record_id = a.id
                WHERE a.state IN ('approved', 's_code', 'vervanging', 'done')
            )
        """ % self._table)
