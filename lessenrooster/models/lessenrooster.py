from markupsafe import Markup

from odoo import models, fields, api


class LessenroosterKlasView(models.TransientModel):
    _name = 'lessenrooster.klas.view'
    _description = 'Klasrooster weergave'

    schooljaar = fields.Char(string='Schooljaar', default='2025-2026', required=True)
    view_type = fields.Selection([
        ('klas', 'Klas'),
        ('leerkracht', 'Leerkracht'),
        ('lokaal', 'Lokaal'),
    ], string='Weergave', default='klas', required=True)
    available_klas_ids = fields.Many2many(
        'myschool.org', compute='_compute_available_klas_ids',
    )
    klas_id = fields.Many2one(
        'myschool.org', string='Klas',
        domain="[('id', 'in', available_klas_ids)]",
    )
    available_leerkracht_ids = fields.Many2many(
        'myschool.person', compute='_compute_available_leerkracht_ids',
    )
    leerkracht_id = fields.Many2one(
        'myschool.person', string='Leerkracht',
        domain="[('id', 'in', available_leerkracht_ids)]",
    )
    available_lokaal_ids = fields.Many2many(
        'myschool.org', compute='_compute_available_lokaal_ids',
    )
    lokaal_filter_id = fields.Many2one(
        'myschool.org', string='Lokaal',
        domain="[('id', 'in', available_lokaal_ids)]",
    )
    rooster_html = fields.Html(string='Rooster', compute='_compute_rooster_html', sanitize=False)

    @api.depends('schooljaar')
    def _compute_available_klas_ids(self):
        for rec in self:
            if rec.schooljaar:
                klas_ids = self.env['lessenrooster.line'].search([
                    ('schooljaar', '=', rec.schooljaar),
                ]).mapped('klas_id').ids
                rec.available_klas_ids = [(6, 0, klas_ids)]
            else:
                rec.available_klas_ids = [(5, 0, 0)]

    @api.depends('schooljaar')
    def _compute_available_leerkracht_ids(self):
        for rec in self:
            if rec.schooljaar:
                leerkracht_ids = self.env['lessenrooster.line'].search([
                    ('schooljaar', '=', rec.schooljaar),
                    ('leerkracht_id', '!=', False),
                ]).mapped('leerkracht_id').ids
                rec.available_leerkracht_ids = [(6, 0, leerkracht_ids)]
            else:
                rec.available_leerkracht_ids = [(5, 0, 0)]

    @api.depends('schooljaar')
    def _compute_available_lokaal_ids(self):
        for rec in self:
            if rec.schooljaar:
                lokaal_ids = self.env['lessenrooster.line'].search([
                    ('schooljaar', '=', rec.schooljaar),
                    ('lokaal_id', '!=', False),
                ]).mapped('lokaal_id').ids
                rec.available_lokaal_ids = [(6, 0, lokaal_ids)]
            else:
                rec.available_lokaal_ids = [(5, 0, 0)]

    @api.depends('view_type', 'klas_id', 'leerkracht_id', 'lokaal_filter_id', 'schooljaar')
    def _compute_rooster_html(self):
        dagen = [('1', 'Maandag'), ('2', 'Dinsdag'), ('3', 'Woensdag'), ('4', 'Donderdag'), ('5', 'Vrijdag')]
        for rec in self:
            if not rec.schooljaar:
                rec.rooster_html = ''
                continue

            # Build domain based on view type
            domain = [('schooljaar', '=', rec.schooljaar)]
            if rec.view_type == 'klas' and rec.klas_id:
                domain.append(('klas_id', '=', rec.klas_id.id))
            elif rec.view_type == 'leerkracht' and rec.leerkracht_id:
                domain.append(('leerkracht_id', '=', rec.leerkracht_id.id))
            elif rec.view_type == 'lokaal' and rec.lokaal_filter_id:
                domain.append(('lokaal_id', '=', rec.lokaal_filter_id.id))
            else:
                rec.rooster_html = ''
                continue

            lines = self.env['lessenrooster.line'].search(domain)

            if not lines:
                rec.rooster_html = Markup('<p class="text-muted">Geen rooster gevonden.</p>')
                continue

            max_uur = max(lines.mapped('lesuur')) if lines else 0
            grid = {}
            for line in lines:
                grid.setdefault(line.lesuur, {}).setdefault(line.dag, []).append(line)

            html = '<table class="table table-bordered table-sm text-center" style="table-layout:fixed;">'
            html += '<thead class="table-dark"><tr><th style="width:60px;">Uur</th>'
            for dag_key, dag_label in dagen:
                html += f'<th>{dag_label}</th>'
            html += '</tr></thead><tbody>'

            for uur in range(1, max_uur + 1):
                html += f'<tr><td class="fw-bold table-light">{uur}</td>'
                for dag_key, _ in dagen:
                    cell_lines = grid.get(uur, {}).get(dag_key, [])
                    if cell_lines:
                        cell_parts = []
                        for cl in cell_lines:
                            vak = f'<strong>{cl.vak}</strong>'
                            if rec.view_type == 'klas':
                                detail = cl.leerkracht_afkorting or ''
                                extra = cl.lokaal_name or ''
                            elif rec.view_type == 'leerkracht':
                                detail = cl.klas_name or ''
                                extra = cl.lokaal_name or ''
                            else:  # lokaal
                                detail = cl.klas_name or ''
                                extra = cl.leerkracht_afkorting or ''
                            cell_parts.append(
                                f'{vak}<br/><small>{detail}</small>'
                                + (f'<br/><small class="text-muted">{extra}</small>' if extra else '')
                            )
                        html += f'<td>{"<hr style=\"margin:2px 0;\"/>".join(cell_parts)}</td>'
                    else:
                        html += '<td class="table-light"></td>'
                html += '</tr>'

            html += '</tbody></table>'
            rec.rooster_html = Markup(html)


class LessenroosterLine(models.Model):
    _name = 'lessenrooster.line'
    _description = 'Lessenrooster lijn'
    _order = 'dag, lesuur, klas_id'

    schooljaar = fields.Char(string='Schooljaar', required=True, index=True)
    school_id = fields.Many2one(
        'myschool.org', string='School', index=True,
    )
    school_company_id = fields.Many2one(
        'res.company', string='Bedrijf (school)',
        compute='_compute_school_company_id', store=True,
    )
    external_id = fields.Integer(string='Extern ID')
    klas_id = fields.Many2one(
        'myschool.org', string='Klas', required=True, index=True,
    )
    klas_name = fields.Char(string='Klas naam', related='klas_id.name_short', store=True)
    leerkracht_id = fields.Many2one(
        'myschool.person', string='Leerkracht', index=True,
    )
    leerkracht_afkorting = fields.Char(
        string='Afkorting', related='leerkracht_id.abbreviation', store=True,
    )
    vak = fields.Char(string='Vak', required=True, index=True)
    lokaal_id = fields.Many2one(
        'myschool.org', string='Lokaal', index=True,
    )
    lokaal_name = fields.Char(string='Lokaal naam', related='lokaal_id.name_short', store=True)
    dag = fields.Selection([
        ('1', 'Maandag'),
        ('2', 'Dinsdag'),
        ('3', 'Woensdag'),
        ('4', 'Donderdag'),
        ('5', 'Vrijdag'),
    ], string='Dag', required=True)
    lesuur = fields.Integer(string='Lesuur', required=True)

    @api.depends('school_id')
    def _compute_school_company_id(self):
        companies = self.env['res.company'].sudo().search([('school_id', '!=', False)])
        school_to_company = {c.school_id.id: c.id for c in companies}
        for record in self:
            record.school_company_id = school_to_company.get(record.school_id.id, False)

    @api.depends('klas_id', 'leerkracht_id', 'vak', 'dag', 'lesuur', 'lokaal_id')
    def _compute_display_name(self):
        dag_labels = dict(self._fields['dag'].selection)
        for rec in self:
            parts = [
                rec.klas_id.name_short or '',
                rec.leerkracht_id.abbreviation or '',
                rec.vak or '',
                dag_labels.get(rec.dag, ''),
                f'uur {rec.lesuur}' if rec.lesuur else '',
            ]
            rec.display_name = ' - '.join(p for p in parts if p)
