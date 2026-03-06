from odoo import models, fields, api


class MySchoolDashboard(models.Model):
    _name = 'myschool.dashboard'
    _description = 'Mijn Dashboard'

    module_filter = fields.Selection([
        ('all', 'Alle Aanvragen'),
        ('buitenschoolse_activiteit', 'Buitenschoolse Activiteiten'),
        ('professionalisering', 'Professionalisering'),
        ('activiteiten', 'Activiteiten'),
    ], string="Module", default='all')

    state_filter = fields.Selection([
        ('all', 'Alle'),
        ('draft', 'Concept'),
        ('submitted', 'Ingediend'),
        ('approved', 'Goedgekeurd'),
        ('rejected', 'Afgekeurd'),
        ('done', 'Afgerond'),
    ], string="Status", default='all')

    priority_filter = fields.Selection([
        ('all', 'Alle'),
        ('0', 'Normaal'),
        ('1', '\u2605'),
        ('2', '\u2605\u2605'),
        ('3', '\u2605\u2605\u2605'),
    ], string="Prioriteit", default='all')

    search_query = fields.Char(string="Zoeken")

    # Access booleans
    has_activiteit_access = fields.Boolean(
        compute='_compute_access_rights')
    has_professionalisering_access = fields.Boolean(
        compute='_compute_access_rights')
    has_activiteiten_access = fields.Boolean(
        compute='_compute_access_rights')
    is_directie = fields.Boolean(
        compute='_compute_access_rights')
    is_activiteit_manager = fields.Boolean(
        compute='_compute_access_rights')
    is_prof_manager = fields.Boolean(
        compute='_compute_access_rights')
    is_act_manager = fields.Boolean(
        compute='_compute_access_rights')
    is_act_vervangingen = fields.Boolean(
        compute='_compute_access_rights')
    is_act_aankoop = fields.Boolean(
        compute='_compute_access_rights')
    is_act_boekhouding = fields.Boolean(
        compute='_compute_access_rights')
    is_act_directie = fields.Boolean(
        compute='_compute_access_rights')
    # Counts buitenschoolse activiteit
    activiteit_total = fields.Integer(
        string="Activiteit Totaal", compute='_compute_activiteit_counts')
    activiteit_draft = fields.Integer(
        string="Activiteit Concept", compute='_compute_activiteit_counts')
    activiteit_submitted = fields.Integer(
        string="Activiteit Ingediend", compute='_compute_activiteit_counts')
    activiteit_approved = fields.Integer(
        string="Activiteit Goedgekeurd", compute='_compute_activiteit_counts')
    activiteit_rejected = fields.Integer(
        string="Activiteit Afgekeurd", compute='_compute_activiteit_counts')
    activiteit_done = fields.Integer(
        string="Activiteit Afgerond", compute='_compute_activiteit_counts')

    # Counts activiteiten (per actual state)
    act_total = fields.Integer(
        string="Act. Totaal", compute='_compute_activiteiten_counts')
    act_draft = fields.Integer(
        string="Act. Concept", compute='_compute_activiteiten_counts')
    act_form_invullen = fields.Integer(
        string="Act. Formulier invullen", compute='_compute_activiteiten_counts')
    act_bus_check = fields.Integer(
        string="Act. Controle bus", compute='_compute_activiteiten_counts')
    act_bus_refused = fields.Integer(
        string="Act. Bus geweigerd", compute='_compute_activiteiten_counts')
    act_pending_approval = fields.Integer(
        string="Act. Wacht op goedkeuring", compute='_compute_activiteiten_counts')
    act_approved = fields.Integer(
        string="Act. Goedgekeurd", compute='_compute_activiteiten_counts')
    act_rejected = fields.Integer(
        string="Act. Afgekeurd", compute='_compute_activiteiten_counts')
    act_s_code = fields.Integer(
        string="Act. S-Code", compute='_compute_activiteiten_counts')
    act_vervanging = fields.Integer(
        string="Act. Vervanging", compute='_compute_activiteiten_counts')
    act_done = fields.Integer(
        string="Act. Afgerond", compute='_compute_activiteiten_counts')

    # Counts professionalisering
    prof_total = fields.Integer(
        string="Prof. Totaal", compute='_compute_professionalisering_counts')
    prof_draft = fields.Integer(
        string="Prof. Concept", compute='_compute_professionalisering_counts')
    prof_submitted = fields.Integer(
        string="Prof. Ingediend", compute='_compute_professionalisering_counts')
    prof_approved = fields.Integer(
        string="Prof. Goedgekeurd", compute='_compute_professionalisering_counts')
    prof_rejected = fields.Integer(
        string="Prof. Afgekeurd", compute='_compute_professionalisering_counts')
    prof_done = fields.Integer(
        string="Prof. Afgerond", compute='_compute_professionalisering_counts')

    activiteit_ids = fields.Many2many(
        'aanvraag_buitenschoolse_activiteit.record',
        string="Buitenschoolse Activiteiten",
        compute='_compute_activiteit_ids')
    professionalisering_ids = fields.Many2many(
        'professionalisering.record', string="Professionalisering",
        compute='_compute_professionalisering_ids')
    activiteiten_ids = fields.Many2many(
        'activiteiten.record', string="Activiteiten",
        compute='_compute_activiteiten_ids')

    _DIRECTIE_GROUPS = {
        'aanvraag_buitenschoolse_activiteit.record':
            'aanvraag_buitenschoolse_activiteit.group_buitenschoolse_activiteit_directie',
        'professionalisering.record':
            'professionalisering.group_professionalisering_directie',
        'activiteiten.record':
            'activiteiten.group_activiteiten_directie',
    }
    _ADMIN_GROUPS = {
        'aanvraag_buitenschoolse_activiteit.record':
            'aanvraag_buitenschoolse_activiteit.group_buitenschoolse_activiteit_admin',
        'professionalisering.record':
            'professionalisering.group_professionalisering_admin',
        'activiteiten.record':
            'activiteiten.group_activiteiten_admin',
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

    _ALL_GROUPS = {
        'aanvraag_buitenschoolse_activiteit.record': [
            'aanvraag_buitenschoolse_activiteit.group_buitenschoolse_activiteit_user',
            'aanvraag_buitenschoolse_activiteit.group_buitenschoolse_activiteit_boekhouding',
            'aanvraag_buitenschoolse_activiteit.group_buitenschoolse_activiteit_vervangingen',
            'aanvraag_buitenschoolse_activiteit.group_buitenschoolse_activiteit_directie',
            'aanvraag_buitenschoolse_activiteit.group_buitenschoolse_activiteit_admin',
        ],
        'professionalisering.record': [
            'professionalisering.group_professionalisering_user',
            'professionalisering.group_professionalisering_boekhouding',
            'professionalisering.group_professionalisering_vervangingen',
            'professionalisering.group_professionalisering_directie',
            'professionalisering.group_professionalisering_admin',
        ],
        'activiteiten.record': [
            'activiteiten.group_activiteiten_personeelslid',
            'activiteiten.group_activiteiten_aankoop',
            'activiteiten.group_activiteiten_boekhouding',
            'activiteiten.group_activiteiten_vervangingen',
            'activiteiten.group_activiteiten_directie',
            'activiteiten.group_activiteiten_admin',
        ],
    }

    def _has_access(self, model_name):
        user = self.env(su=False).user
        for group_xmlid in self._ALL_GROUPS.get(model_name, []):
            if user.has_group(group_xmlid):
                return True
        return False

    def _is_directie_or_admin(self, model_name):
        group_xmlid = self._DIRECTIE_GROUPS.get(model_name)
        if not group_xmlid:
            return False
        return self.env(su=False).user.has_group(group_xmlid)

    def _is_admin(self, model_name):
        group_xmlid = self._ADMIN_GROUPS.get(model_name)
        if not group_xmlid:
            return False
        return self.env(su=False).user.has_group(group_xmlid)

    def _get_base_domain(self, model_name):
        """Admin sees all, directie sees unassigned + assigned-to-them, medewerker only their own."""
        if self._is_admin(model_name):
            return []
        if model_name == 'activiteiten.record':
            if self._is_directie_or_admin(model_name) or self._is_manager(model_name):
                return []
            return [('create_uid', '=', self.env.uid)]
        if self._is_directie_or_admin(model_name):
            return [
                '|',
                ('assigned_to', '=', False),
                ('assigned_to.user_id', '=', self.env.uid),
            ]
        return [('employee_id.user_id', '=', self.env.uid)]

    _MANAGER_GROUPS = {
        'aanvraag_buitenschoolse_activiteit.record': [
            'aanvraag_buitenschoolse_activiteit.group_buitenschoolse_activiteit_directie',
            'aanvraag_buitenschoolse_activiteit.group_buitenschoolse_activiteit_admin',
            'aanvraag_buitenschoolse_activiteit.group_buitenschoolse_activiteit_boekhouding',
            'aanvraag_buitenschoolse_activiteit.group_buitenschoolse_activiteit_vervangingen',
        ],
        'professionalisering.record': [
            'professionalisering.group_professionalisering_directie',
            'professionalisering.group_professionalisering_admin',
            'professionalisering.group_professionalisering_boekhouding',
            'professionalisering.group_professionalisering_vervangingen',
        ],
        'activiteiten.record': [
            'activiteiten.group_activiteiten_directie',
            'activiteiten.group_activiteiten_admin',
            'activiteiten.group_activiteiten_aankoop',
            'activiteiten.group_activiteiten_boekhouding',
            'activiteiten.group_activiteiten_vervangingen',
        ],
    }

    def _is_manager(self, model_name):
        user = self.env(su=False).user
        for group_xmlid in self._MANAGER_GROUPS.get(model_name, []):
            if user.has_group(group_xmlid):
                return True
        return False

    @api.depends_context('uid')
    def _compute_access_rights(self):
        activiteit = self._has_access(
            'aanvraag_buitenschoolse_activiteit.record')
        professionalisering = self._has_access('professionalisering.record')
        activiteiten = self._has_access('activiteiten.record')
        directie = (
            self._is_directie_or_admin('aanvraag_buitenschoolse_activiteit.record')
            or self._is_directie_or_admin('professionalisering.record')
            or self._is_directie_or_admin('activiteiten.record')
        )
        act_mgr = self._is_manager('aanvraag_buitenschoolse_activiteit.record')
        prof_mgr = self._is_manager('professionalisering.record')
        acti_mgr = self._is_manager('activiteiten.record')
        user = self.env(su=False).user
        is_admin = user.has_group('activiteiten.group_activiteiten_admin')
        act_verv = is_admin or user.has_group('activiteiten.group_activiteiten_vervangingen')
        act_aank = is_admin or user.has_group('activiteiten.group_activiteiten_aankoop')
        act_boek = is_admin or user.has_group('activiteiten.group_activiteiten_boekhouding')
        act_dir = is_admin or user.has_group('activiteiten.group_activiteiten_directie')
        for rec in self:
            rec.has_activiteit_access = activiteit
            rec.has_professionalisering_access = professionalisering
            rec.has_activiteiten_access = activiteiten
            rec.is_directie = directie
            rec.is_activiteit_manager = act_mgr
            rec.is_prof_manager = prof_mgr
            rec.is_act_manager = acti_mgr
            rec.is_act_vervangingen = act_verv
            rec.is_act_aankoop = act_aank
            rec.is_act_boekhouding = act_boek
            rec.is_act_directie = act_dir

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
        setattr(rec, f'{prefix}_rejected', counts.get('rejected', 0))
        setattr(rec, f'{prefix}_done', counts.get('done', 0))
        setattr(rec, f'{prefix}_total', sum(counts.values()))

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
            'rejected': raw.get('weigering', 0),
            'done': raw.get('done', 0),
        }
        for rec in self:
            rec._set_counts(rec, 'prof', counts)

    # --- Activiteiten counts ---

    _ACT_STATE_MAP = {
        'draft': [('state', 'in', ('draft', 'form_invullen'))],
        'submitted': [('state', 'in', ('bus_check', 'bus_refused', 'pending_approval'))],
        'approved': [('state', 'in', ('approved', 's_code', 'vervanging'))],
        'rejected': [('state', '=', 'rejected')],
        'done': [('state', '=', 'done')],
    }

    @api.depends_context('uid')
    def _compute_activiteiten_counts(self):
        raw = self._get_state_counts('activiteiten.record')
        for rec in self:
            rec.act_draft = raw.get('draft', 0)
            rec.act_form_invullen = raw.get('form_invullen', 0)
            rec.act_bus_check = raw.get('bus_check', 0)
            rec.act_bus_refused = raw.get('bus_refused', 0)
            rec.act_pending_approval = raw.get('pending_approval', 0)
            rec.act_approved = raw.get('approved', 0) + raw.get('s_code', 0) + raw.get('vervanging', 0) + raw.get('done', 0)
            rec.act_rejected = raw.get('rejected', 0)
            rec.act_s_code = raw.get('s_code', 0)
            rec.act_vervanging = raw.get('vervanging', 0)
            rec.act_done = raw.get('done', 0)
            rec.act_total = sum(raw.values())

    # --- Record lists ---

    def _add_priority_domain(self, domain):
        if self.priority_filter and self.priority_filter != 'all':
            domain.append(('priority', '=', self.priority_filter))

    def _add_search_domain(self, domain, model_name):
        if self.search_query:
            query = self.search_query.strip()
            if query:
                if model_name == 'aanvraag_buitenschoolse_activiteit.record':
                    domain += [
                        '|', '|', '|',
                        ('titel', 'ilike', query),
                        ('name', 'ilike', query),
                        ('bestemming', 'ilike', query),
                        ('employee_id.name', 'ilike', query),
                    ]
                elif model_name == 'activiteiten.record':
                    domain += [
                        '|',
                        ('titel', 'ilike', query),
                        ('name', 'ilike', query),
                    ]
                else:
                    domain += [
                        '|', '|',
                        ('titel', 'ilike', query),
                        ('name', 'ilike', query),
                        ('employee_id.name', 'ilike', query),
                    ]

    def _search_records(self, model_name):
        if not self._has_access(model_name):
            return False
        domain = self._get_base_domain(model_name)
        if self.state_filter and self.state_filter != 'all':
            domain.append(('state', '=', self.state_filter))
        self._add_priority_domain(domain)
        self._add_search_domain(domain, model_name)
        return self.env[model_name].search(domain)

    @api.depends('state_filter', 'priority_filter', 'search_query')
    @api.depends_context('uid')
    def _compute_activiteit_ids(self):
        for rec in self:
            rec.activiteit_ids = rec._search_records(
                'aanvraag_buitenschoolse_activiteit.record')

    _PROF_STATE_MAP = {
        'draft': [('state', '=', 'selection_of_form')],
        'submitted': [('state', 'in', [
            'fill_in_form_binnenschoolse',
            'fill_in_form_buitenschoolse',
            'fill_in_form_externe',
        ])],
        'approved': [('state', '=', 'bevestiging')],
        'rejected': [('state', '=', 'weigering')],
        'done': [('state', '=', 'done')],
    }

    @api.depends('state_filter', 'priority_filter', 'search_query')
    @api.depends_context('uid')
    def _compute_professionalisering_ids(self):
        for rec in self:
            if not self._has_access('professionalisering.record'):
                rec.professionalisering_ids = False
                continue
            domain = self._get_base_domain('professionalisering.record')
            if rec.state_filter and rec.state_filter != 'all':
                domain += self._PROF_STATE_MAP.get(
                    rec.state_filter, [('state', '=', rec.state_filter)])
            rec._add_priority_domain(domain)
            rec._add_search_domain(domain, 'professionalisering.record')
            rec.professionalisering_ids = self.env[
                'professionalisering.record'].search(domain)

    @api.depends('state_filter', 'priority_filter', 'search_query')
    @api.depends_context('uid')
    def _compute_activiteiten_ids(self):
        for rec in self:
            if not self._has_access('activiteiten.record'):
                rec.activiteiten_ids = False
                continue
            domain = self._get_base_domain('activiteiten.record')
            if rec.state_filter and rec.state_filter != 'all':
                domain += self._ACT_STATE_MAP.get(
                    rec.state_filter, [('state', '=', rec.state_filter)])
            rec._add_search_domain(domain, 'activiteiten.record')
            rec.activiteiten_ids = self.env[
                'activiteiten.record'].search(domain)

    # --- Actions ---

    # --- State filter actions ---

    def action_filter_state_all(self):
        self.state_filter = 'all'

    def action_filter_state_draft(self):
        self.state_filter = 'draft'

    def action_filter_state_submitted(self):
        self.state_filter = 'submitted'

    def action_filter_state_approved(self):
        self.state_filter = 'approved'

    def action_filter_state_rejected(self):
        self.state_filter = 'rejected'

    def action_filter_state_done(self):
        self.state_filter = 'done'

    # --- Priority filter actions ---

    def action_filter_priority_all(self):
        self.priority_filter = 'all'

    def action_filter_priority_0(self):
        self.priority_filter = '0'

    def action_filter_priority_1(self):
        self.priority_filter = '1'

    def action_filter_priority_2(self):
        self.priority_filter = '2'

    def action_filter_priority_3(self):
        self.priority_filter = '3'

    # --- Clear all filters ---

    def action_clear_filters(self):
        self.state_filter = 'all'
        self.priority_filter = 'all'
        self.search_query = False

    # --- Module actions ---

    def action_select_all(self):
        self.module_filter = 'all'

    def action_select_activiteit(self):
        self.module_filter = 'buitenschoolse_activiteit'

    def action_open_activiteiten(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'myschool_dashboard.action_open_activiteiten')
        model = 'aanvraag_buitenschoolse_activiteit.record'
        if self._is_admin(model):
            action['context'] = {'search_default_to_approve': 1}
        elif self._is_directie_or_admin(model):
            action['domain'] = [
                '|',
                ('assigned_to', '=', False),
                ('assigned_to.user_id', '=', self.env.uid),
            ]
            action['context'] = {'search_default_to_approve': 1}
        else:
            action['domain'] = [('employee_id.user_id', '=', self.env.uid)]
        return action

    def action_open_professionalisering(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'myschool_dashboard.action_open_professionalisering')
        model = 'professionalisering.record'
        if self._is_admin(model):
            action['context'] = {'search_default_to_approve': 1}
        elif self._is_directie_or_admin(model):
            action['domain'] = [
                '|',
                ('assigned_to', '=', False),
                ('assigned_to.user_id', '=', self.env.uid),
            ]
            action['context'] = {'search_default_to_approve': 1}
        else:
            action['domain'] = [('employee_id.user_id', '=', self.env.uid)]
        return action

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

    def action_select_activiteiten(self):
        self.module_filter = 'activiteiten'

    def action_open_activiteiten_list(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'myschool_dashboard.action_open_activiteiten_list')
        model = 'activiteiten.record'
        if self._is_admin(model):
            pass
        elif self.env(su=False).user.has_group('activiteiten.group_activiteiten_directie'):
            action['context'] = {'search_default_to_approve': 1}
        elif self.env(su=False).user.has_group('activiteiten.group_activiteiten_aankoop'):
            action['context'] = {'search_default_bus_check': 1}
        elif self.env(su=False).user.has_group('activiteiten.group_activiteiten_boekhouding'):
            action['context'] = {'search_default_s_code_pending': 1}
        elif self.env(su=False).user.has_group('activiteiten.group_activiteiten_vervangingen'):
            action['context'] = {'search_default_replacement_pending': 1}
        elif self._is_manager(model):
            pass
        else:
            action['domain'] = [('create_uid', '=', self.env.uid)]
        return action

    def action_create_activiteiten(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Nieuwe Activiteit',
            'res_model': 'activiteiten.record',
            'view_mode': 'form',
            'target': 'current',
        }
