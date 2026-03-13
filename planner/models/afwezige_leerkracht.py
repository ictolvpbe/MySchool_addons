from odoo import models, fields, tools


class AfwezigeLeerkracht(models.Model):
    _name = 'planner.afwezige.leerkracht'
    _description = 'Afwezigen (vanuit activiteiten en professionalisering)'
    _auto = False
    _order = 'datum asc'
    _rec_name = 'display_label'

    display_label = fields.Char(string='Afwezige', compute='_compute_display_label')
    employee_id = fields.Many2one('hr.employee', string='Afwezige', readonly=True)
    employee_name = fields.Char(string='Naam', readonly=True)
    activiteit_id = fields.Many2one('activiteiten.record', string='Activiteit', readonly=True)
    professionalisering_id = fields.Many2one('professionalisering.record', string='Professionalisering', readonly=True)
    titel = fields.Char(string='Titel', readonly=True)
    school_id = fields.Many2one('myschool.org', string='School', readonly=True)
    datum = fields.Datetime(string='Datum', readonly=True)
    datum_end = fields.Datetime(string='Einde', readonly=True)
    state = fields.Selection([
        ('approved', 'Goedgekeurd'),
        ('s_code', 'S-Code'),
        ('vervanging', 'Vervanging'),
        ('done', 'Afgerond'),
        ('bevestiging', 'Bevestigd'),
    ], string='Status', readonly=True)
    klas_id = fields.Many2one('myschool.org', string='Klas', readonly=True)
    record_type = fields.Selection([
        ('leerkracht', 'Leerkracht'),
        ('klas', 'Klas'),
        ('professionalisering', 'Professionalisering'),
    ], string='Type', readonly=True)

    def _compute_display_label(self):
        for rec in self:
            name = rec.employee_name or ''
            date = rec.datum.strftime('%d/%m/%Y') if rec.datum else ''
            titel = rec.titel or ''
            rec.display_label = f'{name} - {titel} ({date})' if name else f'{titel} ({date})'

    def action_plan_vervanging(self):
        self.ensure_one()
        name = self.employee_name or ''
        ctx = {
            'default_afwezige_id': self.id,
            'default_titel': f'Vervanging {name} - {self.titel}',
            'default_inhaal_date': self.datum and self.datum.strftime('%Y-%m-%d'),
        }
        if self.employee_id:
            ctx['default_leerkracht_id'] = self.employee_id.id
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
                -- Activiteiten: leerkrachten
                SELECT
                    row_number() OVER () AS id,
                    p.odoo_employee_id AS employee_id,
                    p.name AS employee_name,
                    NULL::integer AS klas_id,
                    a.id AS activiteit_id,
                    NULL::integer AS professionalisering_id,
                    a.titel AS titel,
                    a.school_id AS school_id,
                    a.datetime AS datum,
                    a.datetime_end AS datum_end,
                    a.state AS state,
                    'leerkracht' AS record_type
                FROM activiteiten_record a
                JOIN activiteiten_record_leerkracht_rel rel
                    ON rel.record_id = a.id
                JOIN myschool_person p ON p.id = rel.person_id
                WHERE a.state IN ('approved', 's_code', 'vervanging', 'done')
                UNION ALL
                -- Activiteiten: klassen
                SELECT
                    (SELECT COUNT(*) FROM activiteiten_record_leerkracht_rel) + row_number() OVER () AS id,
                    NULL::integer AS employee_id,
                    org.name AS employee_name,
                    krel.org_id AS klas_id,
                    a.id AS activiteit_id,
                    NULL::integer AS professionalisering_id,
                    a.titel AS titel,
                    a.school_id AS school_id,
                    a.datetime AS datum,
                    a.datetime_end AS datum_end,
                    a.state AS state,
                    'klas' AS record_type
                FROM activiteiten_record a
                JOIN activiteiten_record_klas_rel krel
                    ON krel.record_id = a.id
                LEFT JOIN myschool_org org ON org.id = krel.org_id
                WHERE a.state IN ('approved', 's_code', 'vervanging', 'done')
                UNION ALL
                -- Professionalisering: eigenaar
                SELECT
                    2000000 + row_number() OVER () AS id,
                    pr.employee_id AS employee_id,
                    emp.name AS employee_name,
                    NULL::integer AS klas_id,
                    NULL::integer AS activiteit_id,
                    pr.id AS professionalisering_id,
                    pr.titel AS titel,
                    pr.school_id AS school_id,
                    pr.start_date::timestamp AS datum,
                    COALESCE(pr.end_date, pr.start_date)::timestamp AS datum_end,
                    pr.state AS state,
                    'professionalisering' AS record_type
                FROM professionalisering_record pr
                JOIN hr_employee emp ON emp.id = pr.employee_id
                WHERE pr.state IN ('bevestiging', 'done')
                UNION ALL
                -- Professionalisering: geaccepteerde uitnodigingen
                SELECT
                    3000000 + row_number() OVER () AS id,
                    inv.employee_id AS employee_id,
                    emp.name AS employee_name,
                    NULL::integer AS klas_id,
                    NULL::integer AS activiteit_id,
                    pr.id AS professionalisering_id,
                    pr.titel AS titel,
                    pr.school_id AS school_id,
                    pr.start_date::timestamp AS datum,
                    COALESCE(pr.end_date, pr.start_date)::timestamp AS datum_end,
                    pr.state AS state,
                    'professionalisering' AS record_type
                FROM professionalisering_record pr
                JOIN professionalisering_invite inv ON inv.professionalisering_id = pr.id
                JOIN hr_employee emp ON emp.id = inv.employee_id
                WHERE pr.state IN ('bevestiging', 'done')
                  AND inv.state = 'accepted'
            )
        """ % self._table)
