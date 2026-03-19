from markupsafe import Markup
from odoo.tools import html_escape

from odoo import models, fields, api


class MySchoolDashboard(models.Model):
    _name = 'myschool.dashboard'
    _description = 'Mijn Dashboard'

    name = fields.Char(default='My Dashboard')

    def _compute_display_name(self):
        for record in self:
            record.display_name = 'My Dashboard'

    # Access booleans
    has_professionalisering_access = fields.Boolean(
        compute='_compute_access_rights')
    has_activiteiten_access = fields.Boolean(
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
    is_only_aankoop = fields.Boolean(
        compute='_compute_access_rights')
    is_only_boekhouding = fields.Boolean(
        compute='_compute_access_rights')
    is_only_directie = fields.Boolean(
        compute='_compute_access_rights')
    is_only_medewerker = fields.Boolean(
        compute='_compute_access_rights')
    is_only_vervangingen = fields.Boolean(
        compute='_compute_access_rights')
    is_prof_directie = fields.Boolean(
        compute='_compute_access_rights')
    is_prof_boekhouding = fields.Boolean(
        compute='_compute_access_rights')
    is_prof_vervangingen = fields.Boolean(
        compute='_compute_access_rights')
    is_prof_only_directie = fields.Boolean(
        compute='_compute_access_rights')
    is_prof_only_boekhouding = fields.Boolean(
        compute='_compute_access_rights')
    is_prof_only_vervangingen = fields.Boolean(
        compute='_compute_access_rights')
    is_prof_only_medewerker = fields.Boolean(
        compute='_compute_access_rights')

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
    prof_payment_pending = fields.Integer(
        string="Prof. Betaling openstaand", compute='_compute_professionalisering_counts')

    # KPI: combined pending / action-needed / approved / rejected
    kpi_pending = fields.Integer(compute='_compute_kpi')
    kpi_action_needed = fields.Integer(compute='_compute_kpi')
    kpi_approved = fields.Integer(compute='_compute_kpi')
    kpi_rejected = fields.Integer(compute='_compute_kpi')

    # Recent activity (own aanvragen)
    recent_activity_html = fields.Html(
        compute='_compute_recent_activity_html', sanitize=False)

    _DIRECTIE_GROUPS = {
        'professionalisering.record':
            'professionalisering.group_professionalisering_directie',
        'activiteiten.record':
            'activiteiten.group_activiteiten_directie',
    }
    _ADMIN_GROUPS = {
        'professionalisering.record':
            'professionalisering.group_professionalisering_admin',
        'activiteiten.record':
            'activiteiten.group_activiteiten_admin',
    }
    _ALL_GROUPS = {
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
    _MANAGER_GROUPS = {
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

    def _is_manager(self, model_name):
        user = self.env(su=False).user
        for group_xmlid in self._MANAGER_GROUPS.get(model_name, []):
            if user.has_group(group_xmlid):
                return True
        return False

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

    @api.depends_context('uid')
    def _compute_access_rights(self):
        professionalisering = self._has_access('professionalisering.record')
        activiteiten = self._has_access('activiteiten.record')
        prof_mgr = self._is_manager('professionalisering.record')
        acti_mgr = self._is_manager('activiteiten.record')
        user = self.env(su=False).user
        is_admin = user.has_group('activiteiten.group_activiteiten_admin')
        prof_admin = user.has_group('professionalisering.group_professionalisering_admin')
        act_verv = is_admin or user.has_group('activiteiten.group_activiteiten_vervangingen')
        act_aank = is_admin or user.has_group('activiteiten.group_activiteiten_aankoop')
        act_boek = is_admin or user.has_group('activiteiten.group_activiteiten_boekhouding')
        act_dir = is_admin or user.has_group('activiteiten.group_activiteiten_directie')
        for rec in self:
            rec.has_professionalisering_access = professionalisering
            rec.has_activiteiten_access = activiteiten
            rec.is_prof_manager = prof_mgr
            rec.is_act_manager = acti_mgr
            rec.is_act_vervangingen = act_verv
            rec.is_act_aankoop = act_aank
            rec.is_act_boekhouding = act_boek
            rec.is_act_directie = act_dir
            rec.is_only_aankoop = act_aank and not act_dir and not act_boek and not act_verv
            rec.is_only_boekhouding = act_boek and not act_dir and not act_aank and not act_verv
            rec.is_only_directie = act_dir and not act_aank and not act_boek and not act_verv
            rec.is_only_medewerker = not act_dir and not act_aank and not act_boek and not act_verv
            rec.is_only_vervangingen = act_verv and not act_dir and not act_aank and not act_boek
            rec.is_prof_directie = prof_admin or user.has_group('professionalisering.group_professionalisering_directie')
            rec.is_prof_boekhouding = prof_admin or user.has_group('professionalisering.group_professionalisering_boekhouding')
            rec.is_prof_vervangingen = prof_admin or user.has_group('professionalisering.group_professionalisering_vervangingen')
            rec.is_prof_only_directie = rec.is_prof_directie and not rec.is_prof_boekhouding and not rec.is_prof_vervangingen
            rec.is_prof_only_boekhouding = rec.is_prof_boekhouding and not rec.is_prof_directie and not rec.is_prof_vervangingen
            rec.is_prof_only_vervangingen = rec.is_prof_vervangingen and not rec.is_prof_directie and not rec.is_prof_boekhouding
            rec.is_prof_only_medewerker = not rec.is_prof_directie and not rec.is_prof_boekhouding and not rec.is_prof_vervangingen

    # --- KPI ---

    @api.depends_context('uid')
    def _compute_kpi(self):
        act_raw = self._get_state_counts('activiteiten.record')
        prof_raw = self._get_state_counts('professionalisering.record')
        # Pending = draft + form_invullen + bus_check (act) + selection_of_form + fill_in_form_* (prof)
        pending = (
            act_raw.get('draft', 0) + act_raw.get('form_invullen', 0) +
            act_raw.get('bus_check', 0) +
            prof_raw.get('selection_of_form', 0) +
            prof_raw.get('fill_in_form_individueel', 0) +
            prof_raw.get('fill_in_form_teamleren', 0)
        )
        # Action needed = pending_approval + bus_refused (act) + wacht_op_goedkeuring (prof)
        action_needed = (
            act_raw.get('pending_approval', 0) +
            act_raw.get('bus_refused', 0) +
            act_raw.get('s_code', 0) +
            act_raw.get('vervanging', 0) +
            prof_raw.get('wacht_op_goedkeuring', 0)
        )
        # Approved (across both)
        approved = (
            act_raw.get('approved', 0) + act_raw.get('done', 0) +
            prof_raw.get('bevestiging', 0) + prof_raw.get('done', 0)
        )
        # Rejected
        rejected = (
            act_raw.get('rejected', 0) +
            prof_raw.get('weigering', 0)
        )
        for rec in self:
            rec.kpi_pending = pending
            rec.kpi_action_needed = action_needed
            rec.kpi_approved = approved
            rec.kpi_rejected = rejected

    # --- Counts ---

    def _get_state_counts(self, model_name):
        if not self._has_access(model_name):
            return {}
        domain = self._get_base_domain(model_name)
        state_counts = self.env[model_name]._read_group(
            domain, groupby=['state'], aggregates=['__count'],
        )
        return {state: count for state, count in state_counts}

    @api.depends_context('uid')
    def _compute_professionalisering_counts(self):
        raw = self._get_state_counts('professionalisering.record')
        is_manager = self._is_manager('professionalisering.record')
        counts = {
            'draft': raw.get('selection_of_form', 0),
            'submitted': (
                raw.get('fill_in_form_individueel', 0)
                + raw.get('fill_in_form_teamleren', 0)
            ),
            'approved': raw.get('bevestiging', 0),
            'rejected': raw.get('weigering', 0),
            'done': raw.get('done', 0),
        }
        for rec in self:
            rec.prof_draft = counts.get('draft', 0)
            rec.prof_submitted = counts.get('submitted', 0)
            rec.prof_approved = counts.get('approved', 0)
            rec.prof_rejected = counts.get('rejected', 0)
            rec.prof_done = counts.get('done', 0)
            rec.prof_payment_pending = 0
            if is_manager:
                rec.prof_total = sum(counts.values())
            else:
                rec.prof_total = sum(
                    v for k, v in counts.items() if k != 'done'
                )

    @api.depends_context('uid')
    def _compute_activiteiten_counts(self):
        raw = self._get_state_counts('activiteiten.record')
        # Determine which states are visible for this user
        user = self.env(su=False).user
        is_admin = user.has_group('activiteiten.group_activiteiten_admin')
        if is_admin:
            visible_states = set(raw.keys())
        else:
            visible_states = set()
            manager_role_checks = {
                'directie': 'activiteiten.group_activiteiten_directie',
                'aankoop': 'activiteiten.group_activiteiten_aankoop',
                'boekhouding': 'activiteiten.group_activiteiten_boekhouding',
                'vervangingen': 'activiteiten.group_activiteiten_vervangingen',
            }
            has_manager_role = False
            for role, group in manager_role_checks.items():
                if user.has_group(group):
                    visible_states.update(self._ROLE_STATES[role])
                    has_manager_role = True
            if not has_manager_role:
                visible_states.update(self._ROLE_STATES['medewerker'])
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
            rec.act_total = sum(
                count for state, count in raw.items()
                if state in visible_states
            )

    # --- Recent activity (own aanvragen) ---

    def _relative_time(self, dt):
        if not dt:
            return ''
        now = fields.Datetime.now()
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return 'Zojuist'
        minutes = seconds // 60
        if minutes < 60:
            return f'{minutes} min geleden'
        hours = minutes // 60
        if hours < 24:
            return f'{hours}u geleden'
        days = hours // 24
        if days == 1:
            return 'Gisteren'
        return f'{days} dagen geleden'

    _ACT_STATE_LABEL = {
        'draft': ('Concept', 'ms-badge-neutral'),
        'form_invullen': ('Formulier', 'ms-badge-info'),
        'bus_check': ('Bus controle', 'ms-badge-warning'),
        'bus_refused': ('Bus geweigerd', 'ms-badge-error'),
        'pending_approval': ('Wacht op goedkeuring', 'ms-badge-warning'),
        'approved': ('Goedgekeurd', 'ms-badge-success'),
        'rejected': ('Afgekeurd', 'ms-badge-error'),
        's_code': ('S-Code', 'ms-badge-info'),
        'vervanging': ('Vervanging', 'ms-badge-info'),
        'done': ('Afgerond', 'ms-badge-success'),
    }

    @api.depends_context('uid')
    def _compute_recent_activity_html(self):
        items = []
        # Recent activiteiten
        if self._has_access('activiteiten.record'):
            domain = self._get_base_domain('activiteiten.record')
            acts = self.env['activiteiten.record'].search(
                domain, limit=5, order='write_date desc')
            for a in acts:
                label, css = self._ACT_STATE_LABEL.get(a.state, ('', ''))
                titel = html_escape(a.titel or a.name or '')
                items.append((a.write_date, (
                    f'<li class="{"success" if a.state in ("approved", "done") else "error" if a.state in ("rejected", "bus_refused") else "info"}">'
                    f'<strong>{titel}</strong> '
                    f'<span class="ms-badge-status {css}">{label}</span><br>'
                    f'<span class="ms-time">{self._relative_time(a.write_date)}</span>'
                    f'</li>'
                )))
        # Recent professionalisering
        if self._has_access('professionalisering.record'):
            domain = self._get_base_domain('professionalisering.record')
            profs = self.env['professionalisering.record'].search(
                domain, limit=5, order='write_date desc')
            for p in profs:
                titel = html_escape(getattr(p, 'titel', '') or p.name or '')
                state = p.state or ''
                if state in ('bevestiging', 'done'):
                    dot = 'success'
                elif state == 'weigering':
                    dot = 'error'
                else:
                    dot = 'info'
                items.append((p.write_date, (
                    f'<li class="{dot}">'
                    f'<strong>{titel}</strong> '
                    f'<span class="ms-badge-status ms-badge-neutral">Prof.</span><br>'
                    f'<span class="ms-time">{self._relative_time(p.write_date)}</span>'
                    f'</li>'
                )))
        # Sort combined and take top 8
        items.sort(key=lambda x: x[0] or fields.Datetime.now(), reverse=True)
        items = items[:8]
        html = (
            '<ul class="ms-timeline">' + ''.join(i[1] for i in items) + '</ul>'
        ) if items else '<div class="ms-empty">Geen recente activiteit</div>'
        for rec in self:
            rec.recent_activity_html = Markup(html)

    # --- Actions ---

    def action_open_professionalisering(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'myschool_dashboard.action_open_professionalisering')
        model = 'professionalisering.record'
        user = self.env(su=False).user
        if self._is_admin(model):
            pass  # no filter for admin
        elif self._is_manager(model):
            visible_states = set()
            search_default = None
            role_checks = {
                'directie': ('professionalisering.group_professionalisering_directie', 'search_default_to_approve'),
                'boekhouding': ('professionalisering.group_professionalisering_boekhouding', 'search_default_payment_pending'),
                'vervangingen': ('professionalisering.group_professionalisering_vervangingen', 'search_default_replacement_pending'),
            }
            for role, (group, sd) in role_checks.items():
                if user.has_group(group):
                    visible_states.update(self._PROF_ROLE_STATES.get(role, []))
                    if not search_default:
                        search_default = sd
            if visible_states:
                action['domain'] = [('state', 'in', list(visible_states))]
            if search_default:
                action['context'] = {search_default: 1}
        else:
            action['context'] = {'search_default_my_requests': 1}
        return action

    # States visible per role (matching dashboard counter visibility)
    _ROLE_STATES = {
        'directie': ['pending_approval'],
        'aankoop': ['bus_check'],
        'boekhouding': ['approved', 's_code', 'vervanging', 'done', 'rejected'],
        'vervangingen': ['vervanging'],
        'medewerker': ['draft', 'form_invullen', 'bus_check', 'bus_refused', 'pending_approval', 'approved', 'rejected', 's_code', 'vervanging', 'done'],
    }

    # Professionalisering states visible per role
    _PROF_ROLE_STATES = {
        'directie': ['fill_in_form_individueel', 'fill_in_form_teamleren'],
        'boekhouding': ['bevestiging', 'done'],
        'vervangingen': ['bevestiging'],
        'medewerker': ['selection_of_form', 'fill_in_form_individueel', 'fill_in_form_teamleren', 'bevestiging', 'weigering', 'done'],
    }

    def action_open_activiteiten_list(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'myschool_dashboard.action_open_activiteiten_list')
        model = 'activiteiten.record'
        user = self.env(su=False).user
        if self._is_admin(model):
            pass  # no filter for admin
        elif self._is_manager(model):
            visible_states = set()
            search_default = None
            role_checks = {
                'directie': ('activiteiten.group_activiteiten_directie', 'search_default_to_approve'),
                'aankoop': ('activiteiten.group_activiteiten_aankoop', 'search_default_bus_check'),
                'boekhouding': ('activiteiten.group_activiteiten_boekhouding', 'search_default_s_code_pending'),
                'vervangingen': ('activiteiten.group_activiteiten_vervangingen', 'search_default_replacement_pending'),
            }
            for role, (group, sd) in role_checks.items():
                if user.has_group(group):
                    visible_states.update(self._ROLE_STATES[role])
                    if not search_default:
                        search_default = sd
            if visible_states:
                action['domain'] = [('state', 'in', list(visible_states))]
            if search_default:
                action['context'] = {search_default: 1}
        else:
            action['domain'] = [
                ('create_uid', '=', self.env.uid),
                ('state', 'in', self._ROLE_STATES['medewerker']),
            ]
            action['context'] = {'search_default_my_requests': 1}
        return action

    def action_new_activiteit(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Nieuwe activiteit',
            'res_model': 'activiteiten.record',
            'view_mode': 'form',
            'target': 'current',
        }

    def action_new_professionalisering(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Nieuwe professionalisering',
            'res_model': 'professionalisering.record',
            'view_mode': 'form',
            'target': 'current',
        }
