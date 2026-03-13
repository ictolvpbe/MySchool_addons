from odoo import models, fields, tools


class KostenPerMedewerker(models.Model):
    _name = 'kosten.per.medewerker'
    _description = 'Kosten per medewerker'
    _auto = False
    _order = 'totale_kost desc'

    employee_id = fields.Many2one('hr.employee', string='Medewerker', readonly=True)
    school_id = fields.Many2one('myschool.org', string='School', readonly=True)
    aantal_activiteiten = fields.Integer(string='Activiteiten', readonly=True)
    aantal_prof = fields.Integer(string='Professionaliseringen', readonly=True)
    aantal_totaal = fields.Integer(string='Totaal', readonly=True)
    kost_activiteiten = fields.Float(string='Kost activiteiten', readonly=True)
    kost_prof = fields.Float(string='Kost professionalisering', readonly=True)
    totale_kost = fields.Float(string='Totale kost', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    emp_id AS employee_id,
                    school_id,
                    SUM(act_count) AS aantal_activiteiten,
                    SUM(prof_count) AS aantal_prof,
                    SUM(act_count + prof_count) AS aantal_totaal,
                    SUM(act_kost) AS kost_activiteiten,
                    SUM(prof_kost) AS kost_prof,
                    SUM(act_kost + prof_kost) AS totale_kost
                FROM (
                    -- Activiteiten: kost per leerkracht (gedeeld door aantal leerkrachten)
                    SELECT
                        p.odoo_employee_id AS emp_id,
                        a.school_id AS school_id,
                        1 AS act_count,
                        0 AS prof_count,
                        CASE
                            WHEN (SELECT COUNT(*) FROM activiteiten_record_leerkracht_rel r2
                                  WHERE r2.record_id = a.id) > 0
                            THEN COALESCE(a.totale_kost, 0) /
                                 (SELECT COUNT(*) FROM activiteiten_record_leerkracht_rel r2
                                  WHERE r2.record_id = a.id)
                            ELSE COALESCE(a.totale_kost, 0)
                        END AS act_kost,
                        0 AS prof_kost
                    FROM activiteiten_record a
                    JOIN activiteiten_record_leerkracht_rel rel ON rel.record_id = a.id
                    JOIN myschool_person p ON p.id = rel.person_id
                    WHERE a.state IN ('approved', 's_code', 'vervanging', 'done')
                      AND p.odoo_employee_id IS NOT NULL

                    UNION ALL

                    -- Professionalisering: eigenaar
                    SELECT
                        pr.employee_id AS emp_id,
                        pr.school_id AS school_id,
                        0 AS act_count,
                        1 AS prof_count,
                        0 AS act_kost,
                        CASE
                            WHEN (1 + (SELECT COUNT(*) FROM professionalisering_invite inv
                                       WHERE inv.professionalisering_id = pr.id
                                         AND inv.state = 'accepted')) > 0
                            THEN (COALESCE(pr.s_code_price, 0) +
                                  COALESCE((SELECT SUM(kl.bedrag)
                                            FROM professionalisering_kosten_line kl
                                            WHERE kl.professionalisering_id = pr.id), 0))
                                 / (1 + (SELECT COUNT(*) FROM professionalisering_invite inv
                                         WHERE inv.professionalisering_id = pr.id
                                           AND inv.state = 'accepted'))
                            ELSE 0
                        END AS prof_kost
                    FROM professionalisering_record pr
                    WHERE pr.state IN ('bevestiging', 'done')

                    UNION ALL

                    -- Professionalisering: geaccepteerde uitnodigingen
                    SELECT
                        inv.employee_id AS emp_id,
                        pr.school_id AS school_id,
                        0 AS act_count,
                        1 AS prof_count,
                        0 AS act_kost,
                        CASE
                            WHEN (1 + (SELECT COUNT(*) FROM professionalisering_invite inv2
                                       WHERE inv2.professionalisering_id = pr.id
                                         AND inv2.state = 'accepted')) > 0
                            THEN (COALESCE(pr.s_code_price, 0) +
                                  COALESCE((SELECT SUM(kl.bedrag)
                                            FROM professionalisering_kosten_line kl
                                            WHERE kl.professionalisering_id = pr.id), 0))
                                 / (1 + (SELECT COUNT(*) FROM professionalisering_invite inv2
                                         WHERE inv2.professionalisering_id = pr.id
                                           AND inv2.state = 'accepted'))
                            ELSE 0
                        END AS prof_kost
                    FROM professionalisering_record pr
                    JOIN professionalisering_invite inv ON inv.professionalisering_id = pr.id
                    WHERE pr.state IN ('bevestiging', 'done')
                      AND inv.state = 'accepted'
                ) sub
                GROUP BY emp_id, school_id
            )
        """ % self._table)


class KostenDetail(models.Model):
    _name = 'kosten.detail'
    _description = 'Kosten detail per activiteit/professionalisering'
    _auto = False
    _order = 'datum desc'

    employee_id = fields.Many2one('hr.employee', string='Medewerker', readonly=True)
    bron = fields.Selection([
        ('activiteit', 'Activiteit'),
        ('professionalisering', 'Professionalisering'),
    ], string='Type', readonly=True)
    titel = fields.Char(string='Titel', readonly=True)
    school_id = fields.Many2one('myschool.org', string='School', readonly=True)
    datum = fields.Date(string='Datum', readonly=True)
    totale_kost = fields.Float(string='Totale kost', readonly=True)
    eigen_kost = fields.Float(string='Eigen aandeel', readonly=True)
    aantal_deelnemers = fields.Integer(string='Deelnemers', readonly=True)
    state = fields.Char(string='Status', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                -- Activiteiten per leerkracht
                SELECT
                    row_number() OVER () AS id,
                    p.odoo_employee_id AS employee_id,
                    'activiteit' AS bron,
                    a.titel AS titel,
                    a.school_id AS school_id,
                    a.datetime::date AS datum,
                    COALESCE(a.totale_kost, 0) AS totale_kost,
                    CASE
                        WHEN (SELECT COUNT(*) FROM activiteiten_record_leerkracht_rel r2
                              WHERE r2.record_id = a.id) > 0
                        THEN COALESCE(a.totale_kost, 0) /
                             (SELECT COUNT(*) FROM activiteiten_record_leerkracht_rel r2
                              WHERE r2.record_id = a.id)
                        ELSE COALESCE(a.totale_kost, 0)
                    END AS eigen_kost,
                    (SELECT COUNT(*) FROM activiteiten_record_leerkracht_rel r2
                     WHERE r2.record_id = a.id) AS aantal_deelnemers,
                    a.state AS state
                FROM activiteiten_record a
                JOIN activiteiten_record_leerkracht_rel rel ON rel.record_id = a.id
                JOIN myschool_person p ON p.id = rel.person_id
                WHERE a.state IN ('approved', 's_code', 'vervanging', 'done')
                  AND p.odoo_employee_id IS NOT NULL

                UNION ALL

                -- Professionalisering: eigenaar
                SELECT
                    2000000 + row_number() OVER () AS id,
                    pr.employee_id AS employee_id,
                    'professionalisering' AS bron,
                    pr.titel AS titel,
                    pr.school_id AS school_id,
                    pr.start_date AS datum,
                    (COALESCE(pr.s_code_price, 0) +
                     COALESCE((SELECT SUM(kl.bedrag)
                               FROM professionalisering_kosten_line kl
                               WHERE kl.professionalisering_id = pr.id), 0)) AS totale_kost,
                    CASE
                        WHEN (1 + (SELECT COUNT(*) FROM professionalisering_invite inv
                                   WHERE inv.professionalisering_id = pr.id
                                     AND inv.state = 'accepted')) > 0
                        THEN (COALESCE(pr.s_code_price, 0) +
                              COALESCE((SELECT SUM(kl.bedrag)
                                        FROM professionalisering_kosten_line kl
                                        WHERE kl.professionalisering_id = pr.id), 0))
                             / (1 + (SELECT COUNT(*) FROM professionalisering_invite inv
                                     WHERE inv.professionalisering_id = pr.id
                                       AND inv.state = 'accepted'))
                        ELSE 0
                    END AS eigen_kost,
                    (1 + (SELECT COUNT(*) FROM professionalisering_invite inv
                          WHERE inv.professionalisering_id = pr.id
                            AND inv.state = 'accepted')) AS aantal_deelnemers,
                    pr.state AS state
                FROM professionalisering_record pr
                WHERE pr.state IN ('bevestiging', 'done')

                UNION ALL

                -- Professionalisering: geaccepteerde uitnodigingen
                SELECT
                    3000000 + row_number() OVER () AS id,
                    inv.employee_id AS employee_id,
                    'professionalisering' AS bron,
                    pr.titel AS titel,
                    pr.school_id AS school_id,
                    pr.start_date AS datum,
                    (COALESCE(pr.s_code_price, 0) +
                     COALESCE((SELECT SUM(kl.bedrag)
                               FROM professionalisering_kosten_line kl
                               WHERE kl.professionalisering_id = pr.id), 0)) AS totale_kost,
                    CASE
                        WHEN (1 + (SELECT COUNT(*) FROM professionalisering_invite inv2
                                   WHERE inv2.professionalisering_id = pr.id
                                     AND inv2.state = 'accepted')) > 0
                        THEN (COALESCE(pr.s_code_price, 0) +
                              COALESCE((SELECT SUM(kl.bedrag)
                                        FROM professionalisering_kosten_line kl
                                        WHERE kl.professionalisering_id = pr.id), 0))
                             / (1 + (SELECT COUNT(*) FROM professionalisering_invite inv2
                                     WHERE inv2.professionalisering_id = pr.id
                                       AND inv2.state = 'accepted'))
                        ELSE 0
                    END AS eigen_kost,
                    (1 + (SELECT COUNT(*) FROM professionalisering_invite inv2
                          WHERE inv2.professionalisering_id = pr.id
                            AND inv2.state = 'accepted')) AS aantal_deelnemers,
                    pr.state AS state
                FROM professionalisering_record pr
                JOIN professionalisering_invite inv ON inv.professionalisering_id = pr.id
                WHERE pr.state IN ('bevestiging', 'done')
                  AND inv.state = 'accepted'
            )
        """ % self._table)
