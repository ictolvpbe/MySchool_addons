from odoo import models, fields, api
from odoo.exceptions import UserError


class DrukwerkRecord(models.Model):
    _name = 'drukwerk.record'
    _description = 'Drukwerk Aanvraag'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Referentie',
        required=True,
        copy=False,
        readonly=True,
        default='New',
    )
    drukwerk_type = fields.Selection([
        ('gewoon', 'Gewoon drukwerk'),
        ('examen', 'Examen drukwerk'),
    ], string='Type drukwerk', tracking=True)
    titel = fields.Char(string='Omschrijving')
    description = fields.Text(string='Toelichting')
    school_id = fields.Many2one(
        'myschool.org',
        string='School',
        default=lambda self: self.env.company.school_id or self.env.user.school_ids[:1],
        domain="[('id', 'in', allowed_school_json)]",
    )
    allowed_school_json = fields.Json(
        compute='_compute_allowed_school_json',
    )
    available_klas_ids = fields.Many2many(
        'myschool.org',
        compute='_compute_available_klas_ids',
        store=False,
    )
    klas_ids = fields.Many2many(
        'myschool.org',
        'drukwerk_record_klas_rel',
        'record_id', 'org_id',
        string='Klassen',
        domain="[('id', 'in', available_klas_ids)]",
    )
    student_ids = fields.Many2many(
        'myschool.person',
        'drukwerk_record_student_rel',
        'record_id', 'person_id',
        string='Leerlingen',
    )
    line_ids = fields.One2many(
        'drukwerk.line', 'drukwerk_id',
        string='Drukwerk items',
    )
    student_count = fields.Integer(
        string='Aantal leerlingen',
        compute='_compute_student_count',
    )
    total_pages = fields.Integer(
        string='Totaal pagina\'s',
        compute='_compute_totals',
        store=True,
    )
    total_cost = fields.Monetary(
        string='Totale kost',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Valuta',
        default=lambda self: self.env.company.currency_id,
    )
    state = fields.Selection([
        ('draft', 'Concept'),
        ('form_invullen', 'Formulier invullen'),
        ('afdrukken', 'Afdrukken'),
        ('doorrekenen', 'Doorrekenen'),
        ('done', 'Afgerond'),
    ], string='Status', default='draft', required=True, tracking=True)
    is_owner = fields.Boolean(compute='_compute_is_owner')

    @api.depends_context('uid')
    def _compute_is_owner(self):
        for record in self:
            record.is_owner = not record.create_uid or record.create_uid.id == self.env.uid

    @api.depends_context('uid', 'company')
    def _compute_allowed_school_json(self):
        schools = self.env.company.school_id or self.env.user.school_ids
        ids = schools.ids or self.env['myschool.org'].sudo().search([('org_type_id.name', '=', 'SCHOOL'), ('is_active', '=', True)]).ids
        for record in self:
            record.allowed_school_json = ids

    @api.depends('school_id')
    def _compute_available_klas_ids(self):
        OrgType = self.env['myschool.org.type']
        dept_type = OrgType.search([('name', '=', 'DEPARTMENT')], limit=1)
        PropRel = self.env['myschool.proprelation']
        for record in self:
            if not record.school_id or not dept_type:
                record.available_klas_ids = False
                continue
            lln_rels = PropRel.search([
                ('id_org_parent', '=', record.school_id.id),
                ('id_org.org_type_id', '=', dept_type.id),
                ('id_org.name_short', '=', 'lln'),
            ])
            lln_ids = lln_rels.mapped('id_org').ids
            if not lln_ids:
                record.available_klas_ids = False
                continue
            klas_rels = PropRel.search([
                ('id_org_parent', 'in', lln_ids),
                ('id_org', '!=', False),
            ])
            record.available_klas_ids = klas_rels.mapped('id_org')

    @api.depends('student_ids')
    def _compute_student_count(self):
        for record in self:
            record.student_count = len(record.student_ids)

    def _get_students_from_classes(self):
        """Get all active students from the selected classes."""
        self.ensure_one()
        PropRelation = self.env['myschool.proprelation']
        PropRelationType = self.env['myschool.proprelation.type']
        person_tree_type = PropRelationType.search([('name', '=', 'PERSON-TREE')], limit=1)
        if not person_tree_type or not self.klas_ids:
            return self.env['myschool.person']
        rels = PropRelation.search([
            ('proprelation_type_id', '=', person_tree_type.id),
            ('id_org', 'in', self.klas_ids.ids),
            ('id_person', '!=', False),
            ('is_active', '=', True),
        ])
        return rels.mapped('id_person')

    @api.onchange('klas_ids')
    def _onchange_klas_ids_select_students(self):
        """Auto-select all students when classes change."""
        students = self._get_students_from_classes()
        self.student_ids = [(6, 0, students.ids)]

    def action_select_all_students(self):
        """Select all students from the chosen classes."""
        for record in self:
            students = record._get_students_from_classes()
            record.student_ids = [(6, 0, students.ids)]

    def action_deselect_all_students(self):
        """Deselect all students."""
        for record in self:
            record.student_ids = [(5, 0, 0)]

    @api.depends('line_ids.aantal_paginas', 'line_ids.aantal_kopies', 'line_ids.prijs_per_pagina')
    def _compute_totals(self):
        for record in self:
            total_pages = 0
            total_cost = 0.0
            for line in record.line_ids:
                pages = (line.aantal_paginas or 0) * (line.aantal_kopies or 0)
                total_pages += pages
                total_cost += pages * (line.prijs_per_pagina or 0)
            record.total_pages = total_pages
            record.total_cost = total_cost

    @api.depends('name', 'titel')
    def _compute_display_name(self):
        for record in self:
            if record.titel:
                record.display_name = f'{record.name} - {record.titel}'
            else:
                record.display_name = record.name or ''

    _rec_names_search = ['name', 'titel']

    @api.onchange('drukwerk_type')
    def _onchange_drukwerk_type(self):
        if self.drukwerk_type and self.state == 'draft':
            self.state = 'form_invullen'

    @api.onchange('school_id')
    def _onchange_school_id(self):
        self.klas_ids = [(5, 0, 0)]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('drukwerk.record') or 'New'
            if vals.get('drukwerk_type') and (not vals.get('state') or vals.get('state') == 'draft'):
                vals['state'] = 'form_invullen'
        return super().create(vals_list)

    # --- Personeelslid actions ---

    def action_submit(self):
        for record in self:
            if record.state != 'form_invullen':
                raise UserError("Kan alleen vanuit de invulfase ingediend worden.")
            if not record.titel:
                raise UserError("Vul een omschrijving in.")
            if not record.klas_ids:
                raise UserError("Selecteer minstens één klas.")
            if not record.line_ids:
                raise UserError("Voeg minstens één drukwerk item toe.")
            record.state = 'afdrukken'
        self._notify_drukwerk_team()

    # --- Drukwerk actions ---

    def action_mark_printed(self):
        for record in self:
            if record.state != 'afdrukken':
                raise UserError("Kan alleen in de afdrukkenfase afgedrukt worden.")
            if record.drukwerk_type == 'examen':
                record.state = 'done'
            else:
                record.state = 'doorrekenen'
        gewoon_records = self.filtered(lambda r: r.drukwerk_type != 'examen')
        if gewoon_records:
            gewoon_records._notify_boekhouding()

    # --- Boekhouding actions ---

    def action_mark_invoiced(self):
        for record in self:
            if record.state != 'doorrekenen':
                raise UserError("Kan alleen in de doorrekeningsfase afgerond worden.")
            record.state = 'done'

    # --- Shared actions ---

    def action_reset_to_form(self):
        for record in self:
            if record.state not in ('afdrukken',):
                raise UserError("Kan alleen vanuit de afdrukkenfase teruggezet worden.")
            record.state = 'form_invullen'

    def action_view_students(self):
        """Open wizard to select/deselect students."""
        self.ensure_one()
        all_students = self._get_students_from_classes()
        selected_ids = set(self.student_ids.ids)
        wiz = self.env['drukwerk.student.select.wizard'].create({
            'drukwerk_id': self.id,
        })
        lines = []
        for student in all_students:
            lines.append({
                'wizard_id': wiz.id,
                'person_id': student.id,
                'selected': student.id in selected_ids,
            })
        if lines:
            self.env['drukwerk.student.select.line'].create(lines)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Leerlingen selecteren',
            'res_model': 'drukwerk.student.select.wizard',
            'res_id': wiz.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def unlink(self):
        if not self.env.user.has_group('drukwerk.group_drukwerk_admin'):
            for record in self:
                if record.state not in ('draft', 'form_invullen'):
                    raise UserError("U kunt alleen aanvragen verwijderen die nog niet ingediend zijn.")
        return super().unlink()

    def _notify_drukwerk_team(self):
        drukwerk_group = self.env.ref(
            'drukwerk.group_drukwerk_drukwerk', raise_if_not_found=False)
        if not drukwerk_group:
            return
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            for user in drukwerk_group.user_ids:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Drukwerk afdrukken',
                    note=f'Drukwerk aanvraag "{record.titel}" is klaar om af te drukken.',
                    user_id=user.id,
                )

    def _notify_boekhouding(self):
        boekhouding_group = self.env.ref(
            'drukwerk.group_drukwerk_boekhouding', raise_if_not_found=False)
        if not boekhouding_group:
            return
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for record in self:
            for user in boekhouding_group.user_ids:
                record.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Drukwerk doorrekenen',
                    note=f'Drukwerk "{record.titel}" is afgedrukt en kan doorgerekend worden.',
                    user_id=user.id,
                )
