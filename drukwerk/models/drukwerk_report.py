from odoo import models, fields, tools


class DrukwerkClassReport(models.Model):
    _name = 'drukwerk.class.report'
    _description = 'Drukwerk: Overzicht per klas'
    _auto = False
    _order = 'klas_id'

    klas_id = fields.Many2one('myschool.org', string='Klas', readonly=True)
    school_id = fields.Many2one('myschool.org', string='School', readonly=True)
    drukwerk_type = fields.Selection([
        ('gewoon', 'Gewoon drukwerk'),
        ('examen', 'Examen drukwerk'),
    ], string='Type', readonly=True)
    aantal_leerlingen = fields.Integer(string='Aantal lln', readonly=True)
    aantal_prints = fields.Integer(string='Aantal prints', readonly=True)
    aantal_aanvragen = fields.Integer(string='Aantal aanvragen', readonly=True)
    totale_kostprijs = fields.Monetary(
        string='Totale kost', currency_field='currency_id', readonly=True,
    )
    currency_id = fields.Many2one('res.currency', readonly=True)

    def action_view_students(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Leerlingen — {self.klas_id.display_name}',
            'res_model': 'drukwerk.student.report',
            'view_mode': 'list',
            'domain': [
                ('klas_id', '=', self.klas_id.id),
                ('drukwerk_type', '=', self.drukwerk_type),
            ],
            'context': {'search_default_klas_id': self.klas_id.id},
        }

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE VIEW {self._table} AS (
                SELECT
                    ROW_NUMBER() OVER () AS id,
                    p.tree_org_id AS klas_id,
                    d.school_id,
                    d.drukwerk_type,
                    d.currency_id,
                    COUNT(DISTINCT p.id) AS aantal_leerlingen,
                    COALESCE(SUM(d.aantal_paginas), 0) AS aantal_prints,
                    COUNT(DISTINCT d.id) AS aantal_aanvragen,
                    COALESCE(SUM(d.cost_per_student), 0) AS totale_kostprijs
                FROM drukwerk_record d
                JOIN drukwerk_record_student_rel rel
                    ON rel.record_id = d.id
                JOIN myschool_person p
                    ON p.id = rel.person_id
                WHERE d.state = 'done'
                  AND p.tree_org_id IS NOT NULL
                GROUP BY p.tree_org_id, d.school_id, d.drukwerk_type, d.currency_id
            )
        """)


class DrukwerkStudentReport(models.Model):
    _name = 'drukwerk.student.report'
    _description = 'Drukwerk: Overzicht per leerling'
    _auto = False
    _order = 'klas_id, person_id'

    person_id = fields.Many2one('myschool.person', string='Leerling', readonly=True)
    klas_id = fields.Many2one('myschool.org', string='Klas', readonly=True)
    school_id = fields.Many2one('myschool.org', string='School', readonly=True)
    drukwerk_type = fields.Selection([
        ('gewoon', 'Gewoon drukwerk'),
        ('examen', 'Examen drukwerk'),
    ], string='Type', readonly=True)
    aantal_prints = fields.Integer(string='Aantal prints', readonly=True)
    aantal_aanvragen = fields.Integer(string='Aantal aanvragen', readonly=True)
    totale_kostprijs = fields.Monetary(
        string='Kost', currency_field='currency_id', readonly=True,
    )
    currency_id = fields.Many2one('res.currency', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE VIEW {self._table} AS (
                SELECT
                    ROW_NUMBER() OVER () AS id,
                    p.id AS person_id,
                    p.tree_org_id AS klas_id,
                    d.school_id,
                    d.drukwerk_type,
                    d.currency_id,
                    COALESCE(SUM(d.aantal_paginas), 0) AS aantal_prints,
                    COUNT(DISTINCT d.id) AS aantal_aanvragen,
                    COALESCE(SUM(d.cost_per_student), 0) AS totale_kostprijs
                FROM drukwerk_record d
                JOIN drukwerk_record_student_rel rel
                    ON rel.record_id = d.id
                JOIN myschool_person p
                    ON p.id = rel.person_id
                WHERE d.state = 'done'
                  AND p.tree_org_id IS NOT NULL
                GROUP BY p.id, p.tree_org_id, d.school_id, d.drukwerk_type, d.currency_id
            )
        """)
