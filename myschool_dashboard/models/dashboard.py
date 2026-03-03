from odoo import models, fields, api


class MySchoolDashboard(models.Model):
    _name = 'myschool.dashboard'
    _description = 'Mijn Dashboard'

    module_filter = fields.Selection([
        ('all', 'Alle Aanvragen'),
        ('nascholingsaanvraag', 'Nascholingsaanvragen'),
        ('buitenschoolse_activiteit', 'Buitenschoolse Activiteiten'),
        ('professionalisering', 'Professionalisering'),
    ], string="Module", default='all')

    state_filter = fields.Selection([
        ('all', 'Alle'),
        ('draft', 'Concept'),
        ('submitted', 'Ingediend'),
        ('approved', 'Goedgekeurd'),
        ('done', 'Afgerond'),
    ], string="Status", default='all')

    # Access booleans
    has_nascholing_access = fields.Boolean(
        compute='_compute_access_rights')
    has_activiteit_access = fields.Boolean(
        compute='_compute_access_rights')
    has_professionalisering_access = fields.Boolean(
        compute='_compute_access_rights')
    # Counts nascholingsaanvraag
    nascholing_total = fields.Integer(
        string="Nascholing Totaal", compute='_compute_nascholing_counts')
    nascholing_draft = fields.Integer(
        string="Nascholing Concept", compute='_compute_nascholing_counts')
    nascholing_submitted = fields.Integer(
        string="Nascholing Ingediend", compute='_compute_nascholing_counts')
    nascholing_approved = fields.Integer(
        string="Nascholing Goedgekeurd", compute='_compute_nascholing_counts')
    nascholing_done = fields.Integer(
        string="Nascholing Afgerond", compute='_compute_nascholing_counts')

    # Counts buitenschoolse activiteit
    activiteit_total = fields.Integer(
        string="Activiteit Totaal", compute='_compute_activiteit_counts')
    activiteit_draft = fields.Integer(
        string="Activiteit Concept", compute='_compute_activiteit_counts')
    activiteit_submitted = fields.Integer(
        string="Activiteit Ingediend", compute='_compute_activiteit_counts')
    activiteit_approved = fields.Integer(
        string="Activiteit Goedgekeurd", compute='_compute_activiteit_counts')
    activiteit_done = fields.Integer(
        string="Activiteit Afgerond", compute='_compute_activiteit_counts')

    # Counts professionalisering
    prof_total = fields.Integer(
        string="Prof. Totaal", compute='_compute_professionalisering_counts')
    prof_draft = fields.Integer(
        string="Prof. Concept", compute='_compute_professionalisering_counts')
    prof_submitted = fields.Integer(
        string="Prof. Ingediend", compute='_compute_professionalisering_counts')
    prof_approved = fields.Integer(
        string="Prof. Goedgekeurd", compute='_compute_professionalisering_counts')
    prof_done = fields.Integer(
        string="Prof. Afgerond", compute='_compute_professionalisering_counts')

    nascholing_ids = fields.Many2many(
        'nascholingsaanvraag.record', string="Nascholingsaanvragen",
        compute='_compute_nascholing_ids')
    activiteit_ids = fields.Many2many(
        'aanvraag_buitenschoolse_activiteit.record',
        string="Buitenschoolse Activiteiten",
        compute='_compute_activiteit_ids')
    professionalisering_ids = fields.Many2many(
        'professionalisering.record', string="Professionalisering",
        compute='_compute_professionalisering_ids')

    # Map each comodel to its directie group (admin implies directie)
    _DIRECTIE_GROUPS = {
        'nascholingsaanvraag.record':
            'nascholingsaanvraag.group_nascholingsaanvraag_directie',
        'aanvraag_buitenschoolse_activiteit.record':
            'aanvraag_buitenschoolse_activiteit.group_buitenschoolse_activiteit_directie',
        'professionalisering.record':
            'professionalisering.group_professionalisering_directie',
    }

    # --- Bypass ACL on read so computed fields can access comodels ---

    def read(self, fields=None, load='_classic_read'):
        return super(
            MySchoolDashboard, self.with_env(self.env(su=True))
        ).read(fields, load)

    def web_read(self, specification, **kwargs):
        return super(
            MySchoolDashboard, self.with_env(self.env(su=True))
        ).web_read(specification, **kwargs)

    # --- Access checks (always use real user, not su) ---

    def _has_access(self, model_name):
        env_real = self.env(su=False)
        try:
            env_real[model_name].check_access('read')
            return True
        except Exception:
            return False

    def _is_directie_or_admin(self, model_name):
        group_xmlid = self._DIRECTIE_GROUPS.get(model_name)
        if not group_xmlid:
            return False
        return self.env(su=False).user.has_group(group_xmlid)

    def _get_base_domain(self, model_name):
        """Directie/admin see all records, medewerker only their own."""
        if self._is_directie_or_admin(model_name):
            return []
        return [('employee_id.user_id', '=', self.env.uid)]

    @api.depends_context('uid')
    def _compute_access_rights(self):
        nascholing = self._has_access('nascholingsaanvraag.record')
        activiteit = self._has_access(
            'aanvraag_buitenschoolse_activiteit.record')
        professionalisering = self._has_access('professionalisering.record')
        for rec in self:
            rec.has_nascholing_access = nascholing
            rec.has_activiteit_access = activiteit
            rec.has_professionalisering_access = professionalisering

    # --- Counts ---

    def _get_state_counts(self, model_name):
        if not self._has_access(model_name):
            return {}
        domain = self._get_base_domain(model_name)
        state_counts = self.env[model_name]._read_group(
            domain, groupby=['state'], aggregates=['__count'],
        )
        return {state: count for state, count in state_counts}

    def _set_counts(self, rec, prefix, counts):
        setattr(rec, f'{prefix}_draft', counts.get('draft', 0))
        setattr(rec, f'{prefix}_submitted', counts.get('submitted', 0))
        setattr(rec, f'{prefix}_approved', counts.get('approved', 0))
        setattr(rec, f'{prefix}_done', counts.get('done', 0))
        setattr(rec, f'{prefix}_total', sum(counts.values()))

    @api.depends_context('uid')
    def _compute_nascholing_counts(self):
        counts = self._get_state_counts('nascholingsaanvraag.record')
        for rec in self:
            rec._set_counts(rec, 'nascholing', counts)

    @api.depends_context('uid')
    def _compute_activiteit_counts(self):
        counts = self._get_state_counts(
            'aanvraag_buitenschoolse_activiteit.record')
        for rec in self:
            rec._set_counts(rec, 'activiteit', counts)

    @api.depends_context('uid')
    def _compute_professionalisering_counts(self):
        raw = self._get_state_counts('professionalisering.record')
        counts = {
            'draft': raw.get('selection_of_form', 0),
            'submitted': (
                raw.get('fill_in_form_binnenschoolse', 0)
                + raw.get('fill_in_form_buitenschoolse', 0)
                + raw.get('fill_in_form_externe', 0)
            ),
            'approved': raw.get('bevestiging', 0),
            'done': raw.get('done', 0),
        }
        for rec in self:
            rec._set_counts(rec, 'prof', counts)

    # --- Record lists ---

    def _search_records(self, model_name):
        if not self._has_access(model_name):
            return False
        domain = self._get_base_domain(model_name)
        if self.state_filter and self.state_filter != 'all':
            domain.append(('state', '=', self.state_filter))
        return self.env[model_name].search(domain)

    @api.depends('module_filter', 'state_filter')
    @api.depends_context('uid')
    def _compute_nascholing_ids(self):
        for rec in self:
            if rec.module_filter in ('all', 'nascholingsaanvraag'):
                rec.nascholing_ids = rec._search_records(
                    'nascholingsaanvraag.record')
            else:
                rec.nascholing_ids = False

    @api.depends('module_filter', 'state_filter')
    @api.depends_context('uid')
    def _compute_activiteit_ids(self):
        for rec in self:
            if rec.module_filter in ('all', 'buitenschoolse_activiteit'):
                rec.activiteit_ids = rec._search_records(
                    'aanvraag_buitenschoolse_activiteit.record')
            else:
                rec.activiteit_ids = False

    _PROF_STATE_MAP = {
        'draft': [('state', '=', 'selection_of_form')],
        'submitted': [('state', 'in', [
            'fill_in_form_binnenschoolse',
            'fill_in_form_buitenschoolse',
            'fill_in_form_externe',
        ])],
        'approved': [('state', '=', 'bevestiging')],
        'done': [('state', '=', 'done')],
    }

    @api.depends('module_filter', 'state_filter')
    @api.depends_context('uid')
    def _compute_professionalisering_ids(self):
        for rec in self:
            if rec.module_filter in ('all', 'professionalisering'):
                if not self._has_access('professionalisering.record'):
                    rec.professionalisering_ids = False
                    continue
                domain = self._get_base_domain('professionalisering.record')
                if rec.state_filter and rec.state_filter != 'all':
                    domain += self._PROF_STATE_MAP.get(
                        rec.state_filter, [('state', '=', rec.state_filter)])
                rec.professionalisering_ids = self.env[
                    'professionalisering.record'].search(domain)
            else:
                rec.professionalisering_ids = False

    # --- Actions ---

    def action_select_all(self):
        self.module_filter = 'all'

    def action_select_nascholing(self):
        self.module_filter = 'nascholingsaanvraag'

    def action_select_activiteit(self):
        self.module_filter = 'buitenschoolse_activiteit'

    def action_create_nascholing(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Nieuwe Nascholingsaanvraag',
            'res_model': 'nascholingsaanvraag.record',
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_activiteit(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Nieuwe Buitenschoolse Activiteit',
            'res_model': 'aanvraag_buitenschoolse_activiteit.record',
            'view_mode': 'form',
            'target': 'current',
        }

    def action_select_professionalisering(self):
        self.module_filter = 'professionalisering'

    def action_create_professionalisering(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Nieuwe Professionalisering',
            'res_model': 'professionalisering.record',
            'view_mode': 'form',
            'target': 'current',
        }
