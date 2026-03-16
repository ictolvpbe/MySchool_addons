import logging
import re
from collections import OrderedDict

from markupsafe import Markup
from lxml import etree

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class AppfoundryProject(models.Model):
    _name = 'appfoundry.project'
    _description = 'AppFoundry Project'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(string='Code', required=True, help='Short code used as item prefix, e.g. MSA')
    description = fields.Html()
    responsible_id = fields.Many2one('res.users', string='Project Lead')
    member_ids = fields.Many2many('res.users', string='Team Members')
    item_ids = fields.One2many(
        'appfoundry.item', 'project_id', string='Items',
        domain=[('stage_id.is_done', '=', False), ('stage_id.is_cancelled', '=', False)],
    )
    story_ids = fields.One2many(
        'appfoundry.item', 'project_id', string='User Stories',
        domain=[('item_type', '=', 'story'), ('stage_id.is_done', '=', False), ('stage_id.is_cancelled', '=', False)],
    )
    bug_ids = fields.One2many(
        'appfoundry.item', 'project_id', string='Bugs',
        domain=[('item_type', '=', 'bug'), ('stage_id.is_done', '=', False), ('stage_id.is_cancelled', '=', False)],
    )
    improvement_ids = fields.One2many(
        'appfoundry.item', 'project_id', string='Improvements',
        domain=[('item_type', '=', 'improvement'), ('stage_id.is_done', '=', False), ('stage_id.is_cancelled', '=', False)],
    )
    sprint_ids = fields.One2many('appfoundry.sprint', 'project_id', string='Sprints')
    release_ids = fields.One2many('appfoundry.release', 'project_id', string='Releases')
    current_release_id = fields.Many2one(
        'appfoundry.release', string='Release Version',
        domain="[('project_id', '=', id), ('state', '!=', 'cancelled')]",
    )
    process_map_ids = fields.Many2many('process.map', string='Process Maps')
    process_map_count = fields.Integer(compute='_compute_process_map_count', string='Process Maps')
    module_ids = fields.Many2many(
        'ir.module.module', 'appfoundry_project_module_rel',
        string='Linked Modules',
    )
    test_item_ids = fields.One2many('appfoundry.test.item', 'project_id', string='Test Items')
    test_item_count = fields.Integer(compute='_compute_test_item_count', string='Test Items')
    test_progress = fields.Float(compute='_compute_test_progress', string='Test Progress')
    phase = fields.Selection([
        ('new', 'New'),
        ('dev', 'Dev'),
        ('test', 'Test'),
        ('stable', 'Stable'),
        ('eol', 'E.O.L.'),
    ], string='Phase', default='new', required=True, tracking=True)
    is_active = fields.Boolean(default=True)

    def action_phase_dev(self):
        self.write({'phase': 'dev'})

    def action_phase_test(self):
        self.write({'phase': 'test'})

    def action_phase_stable(self):
        self.write({'phase': 'stable'})

    def action_phase_eol(self):
        self.write({'phase': 'eol'})

    def action_new_release(self):
        self.ensure_one()
        Release = self.env['appfoundry.release']
        self.env['appfoundry.release'].create({
            'name': Release._next_version_name(self.id),
            'project_id': self.id,
        })

    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)
        for project in projects:
            self.env['appfoundry.release'].create({
                'name': 'v0.1.0',
                'project_id': project.id,
                'state': 'draft',
            })
        return projects

    def _item_action(self, name, extra_domain=None, extra_context=None):
        """Helper to open release-scoped item views."""
        self.ensure_one()
        domain = [
            ('project_id', '=', self.id),
            ('release_id', '=', self.current_release_id.id),
        ]
        if extra_domain:
            domain += extra_domain
        context = {
            'default_project_id': self.id,
            'default_release_id': self.current_release_id.id,
        }
        if extra_context:
            context.update(extra_context)
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'appfoundry.item',
            'view_mode': 'kanban,list,form',
            'domain': domain,
            'context': context,
        }

    def action_open_items(self):
        return self._item_action(f'{self.name} — Items')

    def action_open_bugs(self):
        return self._item_action(
            f'{self.name} — Bugs',
            extra_domain=[('item_type', '=', 'bug')],
            extra_context={'default_item_type': 'bug'},
        )

    def action_open_improvements(self):
        return self._item_action(
            f'{self.name} — Improvements',
            extra_domain=[('item_type', '=', 'improvement')],
            extra_context={'default_item_type': 'improvement'},
        )

    item_count = fields.Integer(compute='_compute_item_count', string='Item Count')
    open_bug_count = fields.Integer(compute='_compute_open_bug_count', string='Open Bugs')

    # Documentation generation
    doc_user_html = fields.Html(string='End-User Documentation', readonly=True, sanitize=False)
    doc_technical_html = fields.Html(string='Technical Documentation', readonly=True, sanitize=False)
    doc_generated_date = fields.Datetime(string='Documentation Generated', readonly=True)

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Project code must be unique.'),
    ]

    @api.depends('item_ids')
    def _compute_item_count(self):
        for project in self:
            project.item_count = len(project.item_ids)

    @api.depends('item_ids', 'item_ids.item_type', 'item_ids.stage_id',
                 'item_ids.stage_id.is_done', 'item_ids.stage_id.is_cancelled')
    def _compute_open_bug_count(self):
        for project in self:
            project.open_bug_count = len(project.item_ids.filtered(
                lambda i: i.item_type == 'bug'
                and not i.stage_id.is_done
                and not i.stage_id.is_cancelled
            ))

    @api.depends('test_item_ids')
    def _compute_test_item_count(self):
        for project in self:
            project.test_item_count = len(project.test_item_ids)

    @api.depends('test_item_ids', 'test_item_ids.state')
    def _compute_test_progress(self):
        for project in self:
            items = project.test_item_ids
            if items:
                passed = len(items.filtered(lambda t: t.state == 'passed'))
                project.test_progress = (passed / len(items)) * 100
            else:
                project.test_progress = 0.0

    @api.depends('process_map_ids')
    def _compute_process_map_count(self):
        for project in self:
            project.process_map_count = len(project.process_map_ids)

    def action_save_form(self):
        """Explicit save — the record is already saved before this method runs."""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Saved',
                'message': 'Project saved successfully.',
                'type': 'success',
                'sticky': False,
            },
        }

    def action_open_process_maps(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - Process Maps',
            'res_model': 'process.map',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.process_map_ids.ids)],
        }

    def action_create_process_map(self):
        self.ensure_one()
        new_map = self.env['process.map'].create({
            'name': self.name,
        })
        self.process_map_ids = [(4, new_map.id)]
        return {
            'type': 'ir.actions.act_window',
            'name': 'Process Map',
            'res_model': 'process.map',
            'view_mode': 'form',
            'res_id': new_map.id,
        }

    def action_open_or_create_process_map(self):
        """Quick-action: open existing process map or create one."""
        self.ensure_one()
        if self.process_map_ids:
            return self.action_open_process_maps()
        return self.action_create_process_map()

    def action_open_test_items(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - Things To Test',
            'res_model': 'appfoundry.test.item',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'search_default_group_type': 1,
                'search_default_group_view': 1,
            },
        }

    # ------------------------------------------------------------------
    # 3T Auto-Generation Engine
    # ------------------------------------------------------------------

    def _get_test_type(self, name, cache):
        """Get or cache a test type by name."""
        if name not in cache:
            tt = self.env['appfoundry.test.type'].search([('name', '=', name)], limit=1)
            cache[name] = tt.id if tt else False
        return cache[name]

    def _test_item_exists(self, existing_keys, project_id, module_id, view_name, element_info):
        """Check if a test item already exists for dedup."""
        return (project_id, module_id, view_name or '', element_info or '') in existing_keys

    def action_generate_test_items(self):
        """Auto-generate test items from linked modules' views, menus, and actions."""
        self.ensure_one()
        TestItem = self.env['appfoundry.test.item']
        type_cache = {}

        # Build existing keys for dedup
        existing = TestItem.search([('project_id', '=', self.id), ('source', '=', 'auto')])
        existing_keys = {
            (r.project_id.id, r.module_id.id, r.view_name or '', r.element_info or '')
            for r in existing
        }

        vals_list = []
        seq = 10  # running sequence counter

        for module in self.module_ids:
            module_name = module.name

            # --- Views ---
            view_data = self.env['ir.model.data'].search([
                ('module', '=', module_name),
                ('model', '=', 'ir.ui.view'),
            ])
            view_ids = view_data.mapped('res_id')
            views = self.env['ir.ui.view'].browse(view_ids).exists()

            for view in views:
                xml_id = f"{view_data.filtered(lambda d: d.res_id == view.id)[:1].name}"
                full_xml_id = f"{module_name}.{xml_id}" if xml_id else str(view.id)

                # Test item for the view itself
                view_type_map = {
                    'form': 'Form View',
                    'tree': 'List View',
                    'list': 'List View',
                    'kanban': 'Kanban View',
                    'search': 'Search View',
                }
                view_type_label = view_type_map.get(view.type, f'{view.type} View')
                element_info = f"view:{full_xml_id}"

                if not self._test_item_exists(existing_keys, self.id, module.id, full_xml_id, element_info):
                    vals_list.append({
                        'name': f"{view_type_label}: {view.name}",
                        'project_id': self.id,
                        'module_id': module.id,
                        'view_name': full_xml_id,
                        'element_info': element_info,
                        'test_type_id': self._get_test_type(view_type_label, type_cache),
                        'source': 'auto',
                        'state': 'not_tested',
                        'sequence': seq,
                    })
                    existing_keys.add((self.id, module.id, full_xml_id, element_info))
                    seq += 10

                # Parse arch XML for testable elements
                try:
                    arch_tree = etree.fromstring(view.arch) if isinstance(view.arch, str) else etree.fromstring(view.arch.encode())
                except Exception:
                    _logger.warning("Could not parse arch for view %s", full_xml_id)
                    continue

                seq = self._extract_elements_from_arch(
                    arch_tree, full_xml_id, module, existing_keys, vals_list, type_cache, seq,
                )

            # --- Menus ---
            menu_data = self.env['ir.model.data'].search([
                ('module', '=', module_name),
                ('model', '=', 'ir.ui.menu'),
            ])
            menu_ids = menu_data.mapped('res_id')
            menus = self.env['ir.ui.menu'].browse(menu_ids).exists()

            for menu in menus:
                menu_xml = menu_data.filtered(lambda d: d.res_id == menu.id)[:1].name
                full_menu_xml = f"{module_name}.{menu_xml}" if menu_xml else str(menu.id)
                element_info = f"menu:{full_menu_xml}"

                if not self._test_item_exists(existing_keys, self.id, module.id, '', element_info):
                    vals_list.append({
                        'name': f"Menu Item: {menu.complete_name or menu.name}",
                        'project_id': self.id,
                        'module_id': module.id,
                        'view_name': '',
                        'element_info': element_info,
                        'test_type_id': self._get_test_type('Menu Item', type_cache),
                        'source': 'auto',
                        'state': 'not_tested',
                        'sequence': seq,
                    })
                    existing_keys.add((self.id, module.id, '', element_info))
                    seq += 10

            # --- Server Actions ---
            action_data = self.env['ir.model.data'].search([
                ('module', '=', module_name),
                ('model', '=', 'ir.actions.server'),
            ])
            action_ids = action_data.mapped('res_id')
            actions = self.env['ir.actions.server'].browse(action_ids).exists()

            for action in actions:
                action_xml = action_data.filtered(lambda d: d.res_id == action.id)[:1].name
                full_action_xml = f"{module_name}.{action_xml}" if action_xml else str(action.id)
                element_info = f"server_action:{full_action_xml}"

                if not self._test_item_exists(existing_keys, self.id, module.id, '', element_info):
                    vals_list.append({
                        'name': f"Server Action: {action.name}",
                        'project_id': self.id,
                        'module_id': module.id,
                        'view_name': '',
                        'element_info': element_info,
                        'test_type_id': self._get_test_type('Server Action', type_cache),
                        'source': 'auto',
                        'state': 'not_tested',
                        'sequence': seq,
                    })
                    existing_keys.add((self.id, module.id, '', element_info))
                    seq += 10

        if vals_list:
            TestItem.create(vals_list)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Test Items Generated',
                'message': f'{len(vals_list)} new test item(s) created.',
                'type': 'success',
                'sticky': False,
            },
        }

    # ------------------------------------------------------------------
    # Documentation Generation
    # ------------------------------------------------------------------

    def action_generate_user_doc(self):
        """Generate end-user documentation HTML."""
        self.ensure_one()
        html = self._build_user_doc()
        self.write({
            'doc_user_html': html,
            'doc_generated_date': fields.Datetime.now(),
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Documentation Generated',
                'message': 'End-user documentation has been generated.',
                'type': 'success',
                'sticky': False,
            },
        }

    def action_generate_tech_doc(self):
        """Generate technical documentation HTML."""
        self.ensure_one()
        html = self._build_tech_doc()
        self.write({
            'doc_technical_html': html,
            'doc_generated_date': fields.Datetime.now(),
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Documentation Generated',
                'message': 'Technical documentation has been generated.',
                'type': 'success',
                'sticky': False,
            },
        }

    @staticmethod
    def _slugify(text):
        text = text.lower().strip()
        text = re.sub(r'[^a-z0-9]+', '_', text)
        return text.strip('_')

    def _esc(self, text):
        """Escape HTML entities in plain text."""
        if not text:
            return ''
        return Markup.escape(str(text))

    # -- End-User Documentation ------------------------------------------

    def _build_user_doc(self):
        """Assemble end-user documentation HTML."""
        parts = []
        style = self._doc_inline_style()
        parts.append(f'<div class="appfoundry-doc appfoundry-doc-user" style="{style}">')

        # 1. Title
        now = fields.Datetime.now()
        parts.append(f'<h1>{self._esc(self.name)}</h1>')
        parts.append(f'<p style="color:#666;">Project code: <strong>{self._esc(self.code)}</strong> '
                     f'&mdash; Generated: {now.strftime("%Y-%m-%d %H:%M")}</p>')
        parts.append('<hr/>')

        # 2. Introduction
        parts.append('<h2>1. Introduction</h2>')
        if self.description:
            parts.append(f'<div>{self.description}</div>')
        else:
            parts.append('<p style="color:#888;"><em>No project description provided.</em></p>')

        # 3. Roles & Actors
        parts.append('<h2>2. Roles &amp; Actors</h2>')
        roles = self._collect_roles_and_actors()
        if roles:
            parts.append('<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">')
            parts.append('<tr style="background:#f5f5f5;">'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Role / Lane</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Organisation</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Process Maps</th></tr>')
            for role in roles:
                parts.append(
                    f'<tr><td style="border:1px solid #ddd;padding:8px;">{self._esc(role["name"])}</td>'
                    f'<td style="border:1px solid #ddd;padding:8px;">{self._esc(role["org"])}</td>'
                    f'<td style="border:1px solid #ddd;padding:8px;">{self._esc(role["maps"])}</td></tr>')
            parts.append('</table>')
        else:
            parts.append('<p style="color:#888;"><em>No roles or actors defined in process maps.</em></p>')

        # 4. Process Workflows
        parts.append('<h2>3. Process Workflows</h2>')
        maps = self.process_map_ids.sorted(lambda m: (0 if m.state == 'approved' else 1, m.name))
        if maps:
            for pmap in maps:
                state_badge = f' <span style="background:#4CAF50;color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">{self._esc(pmap.state)}</span>' if pmap.state == 'approved' else f' <span style="background:#FF9800;color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;">{self._esc(pmap.state)}</span>'
                parts.append(f'<h3>{self._esc(pmap.name)}{state_badge}</h3>')
                if pmap.description:
                    parts.append(f'<p>{self._esc(pmap.description)}</p>')
                flow = self._trace_process_flow(pmap)
                if flow:
                    parts.append('<ol style="margin-bottom:16px;">')
                    for step_info in flow:
                        lane_tag = f' <span style="background:#E3F2FD;padding:1px 6px;border-radius:3px;font-size:11px;">{self._esc(step_info["lane"])}</span>' if step_info.get('lane') else ''
                        label = self._esc(step_info['name'])
                        if step_info['type'] == 'condition':
                            parts.append(f'<li><strong>Decision:</strong> {label}{lane_tag}')
                            if step_info.get('branches'):
                                parts.append('<ul>')
                                for branch in step_info['branches']:
                                    parts.append(f'<li>{self._esc(branch)}</li>')
                                parts.append('</ul>')
                            parts.append('</li>')
                        elif step_info['type'] in ('gateway_exclusive', 'gateway_parallel'):
                            gw_label = 'Exclusive' if step_info['type'] == 'gateway_exclusive' else 'Parallel'
                            parts.append(f'<li><strong>{gw_label} Gateway:</strong> {label}{lane_tag}</li>')
                        elif step_info['type'] == 'start':
                            parts.append(f'<li><strong>Start:</strong> {label}{lane_tag}</li>')
                        elif step_info['type'] == 'end':
                            parts.append(f'<li><strong>End:</strong> {label}{lane_tag}</li>')
                        else:
                            desc = ''
                            if step_info.get('description'):
                                desc = f' &mdash; {self._esc(step_info["description"])}'
                            parts.append(f'<li>{label}{lane_tag}{desc}</li>')
                    parts.append('</ol>')
                else:
                    parts.append('<p style="color:#888;"><em>No steps defined.</em></p>')
        else:
            parts.append('<p style="color:#888;"><em>No process maps linked to this project.</em></p>')

        # 5. Features (user stories grouped by release)
        parts.append('<h2>4. Features</h2>')
        stories = self.story_ids
        if stories:
            # Group by release
            release_groups = OrderedDict()
            for story in stories.sorted(lambda s: (s.release_id.name or '', s.priority, s.sequence)):
                key = story.release_id.name if story.release_id else '__unassigned__'
                release_groups.setdefault(key, []).append(story)
            for release_name, group in release_groups.items():
                if release_name == '__unassigned__':
                    parts.append('<h3>Unassigned to Release</h3>')
                else:
                    parts.append(f'<h3>Release: {self._esc(release_name)}</h3>')
                parts.append('<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">')
                parts.append('<tr style="background:#f5f5f5;">'
                             '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Story</th>'
                             '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Priority</th>'
                             '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Status</th></tr>')
                priority_map = {'0': 'Low', '1': 'Normal', '2': 'High', '3': 'Critical'}
                for story in group:
                    prio = priority_map.get(story.priority, story.priority)
                    prio_color = {'Critical': '#f44336', 'High': '#FF9800', 'Normal': '#2196F3', 'Low': '#9E9E9E'}.get(prio, '#666')
                    parts.append(
                        f'<tr><td style="border:1px solid #ddd;padding:8px;">{self._esc(story.display_name)}</td>'
                        f'<td style="border:1px solid #ddd;padding:8px;"><span style="color:{prio_color};font-weight:bold;">{prio}</span></td>'
                        f'<td style="border:1px solid #ddd;padding:8px;">{self._esc(story.stage_id.name or "")}</td></tr>')
                parts.append('</table>')
        else:
            parts.append('<p style="color:#888;"><em>No user stories defined.</em></p>')

        # 6. Glossary
        parts.append('<h2>5. Glossary</h2>')
        glossary = self._build_glossary()
        if glossary:
            parts.append('<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">')
            parts.append('<tr style="background:#f5f5f5;">'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Term</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Source</th></tr>')
            for term, source in glossary:
                parts.append(
                    f'<tr><td style="border:1px solid #ddd;padding:8px;">{self._esc(term)}</td>'
                    f'<td style="border:1px solid #ddd;padding:8px;">{self._esc(source)}</td></tr>')
            parts.append('</table>')
        else:
            parts.append('<p style="color:#888;"><em>No glossary terms available.</em></p>')

        parts.append('</div>')
        return Markup('\n'.join(parts))

    # -- Technical Documentation -----------------------------------------

    def _build_tech_doc(self):
        """Assemble technical documentation HTML."""
        parts = []
        style = self._doc_inline_style()
        parts.append(f'<div class="appfoundry-doc appfoundry-doc-tech" style="{style}">')

        # 1. Title
        now = fields.Datetime.now()
        parts.append(f'<h1>{self._esc(self.name)} &mdash; Technical Reference</h1>')
        parts.append(f'<p style="color:#666;">Code: <strong>{self._esc(self.code)}</strong> '
                     f'&mdash; Generated: {now.strftime("%Y-%m-%d %H:%M")}</p>')
        parts.append('<hr/>')

        # 2. Architecture — linked modules
        parts.append('<h2>1. Architecture</h2>')
        if self.module_ids:
            parts.append('<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">')
            parts.append('<tr style="background:#f5f5f5;">'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Module</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Summary</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">State</th></tr>')
            for mod in self.module_ids:
                parts.append(
                    f'<tr><td style="border:1px solid #ddd;padding:8px;"><code>{self._esc(mod.name)}</code></td>'
                    f'<td style="border:1px solid #ddd;padding:8px;">{self._esc(mod.summary or "")}</td>'
                    f'<td style="border:1px solid #ddd;padding:8px;">{self._esc(mod.state or "")}</td></tr>')
            parts.append('</table>')
        else:
            parts.append('<p style="color:#888;"><em>No modules linked.</em></p>')

        # 3. Data Models — from process map field definitions
        parts.append('<h2>2. Data Models</h2>')
        maps = self.process_map_ids
        if maps:
            has_fields = False
            for pmap in maps:
                steps_with_fields = pmap.step_ids.filtered(
                    lambda s: s.step_type in ('task', 'subprocess') and s.field_ids)
                if not steps_with_fields:
                    continue
                has_fields = True
                parts.append(f'<h3>Model: {self._esc(pmap.name)}</h3>')
                parts.append(self._build_field_table(steps_with_fields))
            if not has_fields:
                parts.append('<p style="color:#888;"><em>No field definitions in process maps.</em></p>')
        else:
            parts.append('<p style="color:#888;"><em>No process maps linked.</em></p>')

        # 4. Workflow States
        parts.append('<h2>3. Workflow States</h2>')
        if maps:
            for pmap in maps:
                states = pmap._derive_workflow_states()
                if states:
                    parts.append(f'<h3>{self._esc(pmap.name)}</h3>')
                    parts.append('<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">')
                    parts.append('<tr style="background:#f5f5f5;">'
                                 '<th style="border:1px solid #ddd;padding:8px;text-align:left;">#</th>'
                                 '<th style="border:1px solid #ddd;padding:8px;text-align:left;">State</th>'
                                 '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Label</th></tr>')
                    for idx, state in enumerate(states, 1):
                        label = state.replace('_', ' ').title()
                        parts.append(
                            f'<tr><td style="border:1px solid #ddd;padding:8px;">{idx}</td>'
                            f'<td style="border:1px solid #ddd;padding:8px;"><code>{self._esc(state)}</code></td>'
                            f'<td style="border:1px solid #ddd;padding:8px;">{self._esc(label)}</td></tr>')
                    parts.append('</table>')

                    # Transitions table
                    transitions = self._derive_transitions(pmap)
                    if transitions:
                        parts.append(f'<h4>Transitions</h4>')
                        parts.append('<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">')
                        parts.append('<tr style="background:#f5f5f5;">'
                                     '<th style="border:1px solid #ddd;padding:8px;text-align:left;">From</th>'
                                     '<th style="border:1px solid #ddd;padding:8px;text-align:left;">To</th>'
                                     '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Condition</th></tr>')
                        for t in transitions:
                            parts.append(
                                f'<tr><td style="border:1px solid #ddd;padding:8px;"><code>{self._esc(t["from"])}</code></td>'
                                f'<td style="border:1px solid #ddd;padding:8px;"><code>{self._esc(t["to"])}</code></td>'
                                f'<td style="border:1px solid #ddd;padding:8px;">{self._esc(t["label"])}</td></tr>')
                        parts.append('</table>')
        else:
            parts.append('<p style="color:#888;"><em>No process maps linked.</em></p>')

        # 5. Business Rules
        parts.append('<h2>4. Business Rules</h2>')
        if maps:
            has_rules = False
            for pmap in maps:
                steps_with_annotations = pmap.step_ids.filtered(lambda s: s.annotation)
                conn_with_labels = pmap.connection_ids.filtered(lambda c: c.label)
                if not steps_with_annotations and not conn_with_labels:
                    continue
                has_rules = True
                parts.append(f'<h3>{self._esc(pmap.name)}</h3>')
                parts.append('<ul>')
                for step in steps_with_annotations:
                    parts.append(f'<li><strong>{self._esc(step.name)}:</strong> {self._esc(step.annotation)}</li>')
                for conn in conn_with_labels:
                    src = conn.source_step_id.name or '?'
                    tgt = conn.target_step_id.name or '?'
                    parts.append(f'<li><strong>{self._esc(src)} &rarr; {self._esc(tgt)}:</strong> {self._esc(conn.label)}</li>')
                parts.append('</ul>')
            if not has_rules:
                parts.append('<p style="color:#888;"><em>No business rules annotated.</em></p>')
        else:
            parts.append('<p style="color:#888;"><em>No process maps linked.</em></p>')

        # 6. Security
        parts.append('<h2>5. Security</h2>')
        roles = self._collect_roles_and_actors()
        if roles:
            parts.append('<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">')
            parts.append('<tr style="background:#f5f5f5;">'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Lane / Role</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Suggested Group</th></tr>')
            for role in roles:
                slug = self._slugify(role['name'])
                parts.append(
                    f'<tr><td style="border:1px solid #ddd;padding:8px;">{self._esc(role["name"])}</td>'
                    f'<td style="border:1px solid #ddd;padding:8px;"><code>group_{slug}</code></td></tr>')
            parts.append('</table>')
        else:
            parts.append('<p style="color:#888;"><em>No roles defined.</em></p>')

        # 7. Process Specifications
        parts.append('<h2>6. Process Specifications</h2>')
        if maps:
            for pmap in maps:
                parts.append(f'<h3>{self._esc(pmap.name)}</h3>')
                # Steps grouped by lane
                lanes = pmap.lane_ids.sorted('sequence')
                if lanes:
                    for lane in lanes:
                        lane_steps = pmap.step_ids.filtered(lambda s: s.lane_id.id == lane.id)
                        if not lane_steps:
                            continue
                        parts.append(f'<h4>Lane: {self._esc(lane.name)}</h4>')
                        parts.append('<table style="width:100%;border-collapse:collapse;margin-bottom:12px;">')
                        parts.append('<tr style="background:#f5f5f5;">'
                                     '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Step</th>'
                                     '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Type</th>'
                                     '<th style="border:1px solid #ddd;padding:6px;text-align:left;">System Action</th>'
                                     '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Annotation</th></tr>')
                        for step in lane_steps:
                            parts.append(
                                f'<tr><td style="border:1px solid #ddd;padding:6px;">{self._esc(step.name)}</td>'
                                f'<td style="border:1px solid #ddd;padding:6px;">{self._esc(step.step_type)}</td>'
                                f'<td style="border:1px solid #ddd;padding:6px;">{self._esc(step.system_action or "")}</td>'
                                f'<td style="border:1px solid #ddd;padding:6px;">{self._esc(step.annotation or "")}</td></tr>')
                        parts.append('</table>')
                # Unassigned steps
                unassigned = pmap.step_ids.filtered(lambda s: not s.lane_id)
                if unassigned:
                    parts.append('<h4>Unassigned Steps</h4>')
                    parts.append('<table style="width:100%;border-collapse:collapse;margin-bottom:12px;">')
                    parts.append('<tr style="background:#f5f5f5;">'
                                 '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Step</th>'
                                 '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Type</th></tr>')
                    for step in unassigned:
                        parts.append(
                            f'<tr><td style="border:1px solid #ddd;padding:6px;">{self._esc(step.name)}</td>'
                            f'<td style="border:1px solid #ddd;padding:6px;">{self._esc(step.step_type)}</td></tr>')
                    parts.append('</table>')
                # Connections
                if pmap.connection_ids:
                    parts.append('<h4>Connections</h4>')
                    parts.append('<table style="width:100%;border-collapse:collapse;margin-bottom:12px;">')
                    parts.append('<tr style="background:#f5f5f5;">'
                                 '<th style="border:1px solid #ddd;padding:6px;text-align:left;">From</th>'
                                 '<th style="border:1px solid #ddd;padding:6px;text-align:left;">To</th>'
                                 '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Type</th>'
                                 '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Label</th></tr>')
                    for conn in pmap.connection_ids:
                        parts.append(
                            f'<tr><td style="border:1px solid #ddd;padding:6px;">{self._esc(conn.source_step_id.name or "")}</td>'
                            f'<td style="border:1px solid #ddd;padding:6px;">{self._esc(conn.target_step_id.name or "")}</td>'
                            f'<td style="border:1px solid #ddd;padding:6px;">{self._esc(conn.connection_type)}</td>'
                            f'<td style="border:1px solid #ddd;padding:6px;">{self._esc(conn.label or "")}</td></tr>')
                    parts.append('</table>')
        else:
            parts.append('<p style="color:#888;"><em>No process maps linked.</em></p>')

        # 8. Development Status
        parts.append('<h2>7. Development Status</h2>')
        sprints = self.sprint_ids.sorted('date_start')
        if sprints:
            parts.append('<h3>Sprints</h3>')
            parts.append('<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">')
            parts.append('<tr style="background:#f5f5f5;">'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Sprint</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Period</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">State</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:right;">Points</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:right;">Completed</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:right;">Velocity</th></tr>')
            for sprint in sprints:
                start = sprint.date_start.strftime('%Y-%m-%d') if sprint.date_start else '—'
                end = sprint.date_end.strftime('%Y-%m-%d') if sprint.date_end else '—'
                parts.append(
                    f'<tr><td style="border:1px solid #ddd;padding:8px;">{self._esc(sprint.name)}</td>'
                    f'<td style="border:1px solid #ddd;padding:8px;">{start} — {end}</td>'
                    f'<td style="border:1px solid #ddd;padding:8px;">{self._esc(sprint.state)}</td>'
                    f'<td style="border:1px solid #ddd;padding:8px;text-align:right;">{sprint.total_points}</td>'
                    f'<td style="border:1px solid #ddd;padding:8px;text-align:right;">{sprint.completed_points}</td>'
                    f'<td style="border:1px solid #ddd;padding:8px;text-align:right;">{sprint.velocity:.0f}%</td></tr>')
            parts.append('</table>')
        else:
            parts.append('<p style="color:#888;"><em>No sprints defined.</em></p>')

        releases = self.release_ids.sorted('date_planned')
        if releases:
            parts.append('<h3>Releases</h3>')
            parts.append('<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">')
            parts.append('<tr style="background:#f5f5f5;">'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Release</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Planned</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">State</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:right;">Progress</th>'
                         '<th style="border:1px solid #ddd;padding:8px;text-align:left;">Notes</th></tr>')
            for rel in releases:
                date_str = rel.date_planned.strftime('%Y-%m-%d') if rel.date_planned else '—'
                notes_text = ''
                if rel.notes:
                    # Strip HTML tags for table cell
                    notes_text = re.sub(r'<[^>]+>', '', str(rel.notes))[:120]
                parts.append(
                    f'<tr><td style="border:1px solid #ddd;padding:8px;">{self._esc(rel.name)}</td>'
                    f'<td style="border:1px solid #ddd;padding:8px;">{date_str}</td>'
                    f'<td style="border:1px solid #ddd;padding:8px;">{self._esc(rel.state)}</td>'
                    f'<td style="border:1px solid #ddd;padding:8px;text-align:right;">{rel.progress:.0f}%</td>'
                    f'<td style="border:1px solid #ddd;padding:8px;">{self._esc(notes_text)}</td></tr>')
            parts.append('</table>')

        # 9. Test Coverage
        parts.append('<h2>8. Test Coverage</h2>')
        test_items = self.test_item_ids
        if test_items:
            total = len(test_items)
            passed = len(test_items.filtered(lambda t: t.state == 'passed'))
            failed = len(test_items.filtered(lambda t: t.state == 'failed'))
            blocked = len(test_items.filtered(lambda t: t.state == 'blocked'))
            not_tested = len(test_items.filtered(lambda t: t.state == 'not_tested'))
            coverage = (passed / total * 100) if total else 0
            parts.append('<table style="width:auto;border-collapse:collapse;margin-bottom:16px;">')
            parts.append(f'<tr><td style="border:1px solid #ddd;padding:8px;font-weight:bold;">Total</td>'
                         f'<td style="border:1px solid #ddd;padding:8px;">{total}</td></tr>')
            parts.append(f'<tr><td style="border:1px solid #ddd;padding:8px;color:#4CAF50;font-weight:bold;">Passed</td>'
                         f'<td style="border:1px solid #ddd;padding:8px;">{passed}</td></tr>')
            parts.append(f'<tr><td style="border:1px solid #ddd;padding:8px;color:#f44336;font-weight:bold;">Failed</td>'
                         f'<td style="border:1px solid #ddd;padding:8px;">{failed}</td></tr>')
            parts.append(f'<tr><td style="border:1px solid #ddd;padding:8px;color:#FF9800;font-weight:bold;">Blocked</td>'
                         f'<td style="border:1px solid #ddd;padding:8px;">{blocked}</td></tr>')
            parts.append(f'<tr><td style="border:1px solid #ddd;padding:8px;color:#9E9E9E;">Not Tested</td>'
                         f'<td style="border:1px solid #ddd;padding:8px;">{not_tested}</td></tr>')
            parts.append(f'<tr><td style="border:1px solid #ddd;padding:8px;font-weight:bold;">Coverage</td>'
                         f'<td style="border:1px solid #ddd;padding:8px;font-weight:bold;">{coverage:.1f}%</td></tr>')
            parts.append('</table>')
        else:
            parts.append('<p style="color:#888;"><em>No test items defined.</em></p>')

        # 10. Item Inventory
        parts.append('<h2>9. Item Inventory</h2>')
        all_items = self.item_ids
        if all_items:
            type_labels = {'story': 'User Story', 'bug': 'Bug', 'task': 'Task', 'improvement': 'Improvement'}
            for item_type in ('story', 'bug', 'task', 'improvement'):
                typed_items = all_items.filtered(lambda i: i.item_type == item_type)
                if not typed_items:
                    continue
                parts.append(f'<h3>{type_labels.get(item_type, item_type)} ({len(typed_items)})</h3>')
                parts.append('<table style="width:100%;border-collapse:collapse;margin-bottom:12px;">')
                parts.append('<tr style="background:#f5f5f5;">'
                             '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Item</th>'
                             '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Status</th>'
                             '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Sprint</th>'
                             '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Assigned</th></tr>')
                for item in typed_items.sorted('sequence'):
                    parts.append(
                        f'<tr><td style="border:1px solid #ddd;padding:6px;">{self._esc(item.display_name)}</td>'
                        f'<td style="border:1px solid #ddd;padding:6px;">{self._esc(item.stage_id.name or "")}</td>'
                        f'<td style="border:1px solid #ddd;padding:6px;">{self._esc(item.sprint_id.name or "")}</td>'
                        f'<td style="border:1px solid #ddd;padding:6px;">{self._esc(item.assigned_id.name or "")}</td></tr>')
                parts.append('</table>')
        else:
            parts.append('<p style="color:#888;"><em>No items defined.</em></p>')

        parts.append('</div>')
        return Markup('\n'.join(parts))

    # -- Helpers ---------------------------------------------------------

    @staticmethod
    def _doc_inline_style():
        """Base inline styles for the documentation wrapper div."""
        return 'font-family:sans-serif;line-height:1.6;color:#333;max-width:960px;'

    def _trace_process_flow(self, process_map):
        """Trace the process flow from start to end, returning an ordered step list."""
        start_steps = process_map.step_ids.filtered(lambda s: s.step_type == 'start')
        if not start_steps:
            return []

        result = []
        visited = set()

        def trace(step):
            if step.id in visited:
                return
            visited.add(step.id)
            info = {
                'name': step.name,
                'type': step.step_type,
                'lane': step.lane_id.name if step.lane_id else '',
                'description': step.description or '',
            }
            # For conditions/gateways, collect outgoing branch labels
            if step.step_type in ('condition', 'gateway_exclusive'):
                outgoing = process_map.connection_ids.filtered(
                    lambda c: c.source_step_id.id == step.id)
                info['branches'] = [c.label or c.target_step_id.name for c in outgoing]
            result.append(info)
            outgoing = process_map.connection_ids.filtered(
                lambda c: c.source_step_id.id == step.id)
            for conn in outgoing:
                trace(conn.target_step_id)

        for start in start_steps:
            trace(start)

        return result

    def _collect_roles_and_actors(self):
        """Collect unique roles/lanes across all linked process maps."""
        seen = set()
        roles = []
        for pmap in self.process_map_ids:
            for lane in pmap.lane_ids:
                key = lane.name
                if key in seen:
                    continue
                seen.add(key)
                org_name = lane.org_id.name if lane.org_id else ''
                roles.append({
                    'name': lane.name,
                    'org': org_name,
                    'maps': pmap.name,
                })
        return roles

    def _build_field_table(self, steps):
        """Build an HTML table of process.map.field records from given steps."""
        parts = []
        parts.append('<table style="width:100%;border-collapse:collapse;margin-bottom:16px;">')
        parts.append('<tr style="background:#f5f5f5;">'
                     '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Step</th>'
                     '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Field</th>'
                     '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Type</th>'
                     '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Required</th>'
                     '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Relation</th>'
                     '<th style="border:1px solid #ddd;padding:6px;text-align:left;">Description</th></tr>')
        for step in steps:
            for field in step.field_ids.sorted('sequence'):
                req = 'Yes' if field.required else ''
                parts.append(
                    f'<tr><td style="border:1px solid #ddd;padding:6px;">{self._esc(step.name)}</td>'
                    f'<td style="border:1px solid #ddd;padding:6px;"><code>{self._esc(field.name)}</code></td>'
                    f'<td style="border:1px solid #ddd;padding:6px;">{self._esc(field.ttype)}</td>'
                    f'<td style="border:1px solid #ddd;padding:6px;">{req}</td>'
                    f'<td style="border:1px solid #ddd;padding:6px;">{self._esc(field.relation or "")}</td>'
                    f'<td style="border:1px solid #ddd;padding:6px;">{self._esc(field.field_description or "")}</td></tr>')
        parts.append('</table>')
        return '\n'.join(parts)

    def _derive_transitions(self, process_map):
        """Derive state transitions from connections between task/subprocess steps."""
        transitions = []
        for conn in process_map.connection_ids:
            src = conn.source_step_id
            tgt = conn.target_step_id
            if src.step_type in ('task', 'subprocess', 'condition', 'gateway_exclusive') and \
               tgt.step_type in ('task', 'subprocess', 'end', 'condition', 'gateway_exclusive'):
                from_state = self._slugify(src.name) if src.step_type in ('task', 'subprocess') else f'check_{self._slugify(src.name)}'
                to_state = self._slugify(tgt.name) if tgt.step_type in ('task', 'subprocess') else ('end' if tgt.step_type == 'end' else f'check_{self._slugify(tgt.name)}')
                transitions.append({
                    'from': from_state,
                    'to': to_state,
                    'label': conn.label or '',
                })
        return transitions

    def _build_glossary(self):
        """Build alphabetized glossary from tags, role names, and lane names."""
        terms = set()
        # Tags
        for item in self.item_ids:
            for tag in item.tag_ids:
                terms.add((tag.name, 'Tag'))
        # Lane/role names from process maps
        for pmap in self.process_map_ids:
            for lane in pmap.lane_ids:
                terms.add((lane.name, 'Role / Lane'))
                if lane.role_id:
                    terms.add((lane.role_id.name, 'Role'))
        return sorted(terms, key=lambda t: t[0].lower())

    def _extract_elements_from_arch(self, arch_tree, view_xml_id, module, existing_keys, vals_list, type_cache, seq):
        """Extract testable elements from a view's arch XML. Returns updated seq."""
        # Buttons
        for btn in arch_tree.iter('button'):
            btn_name = btn.get('name', '')
            btn_string = btn.get('string', btn_name)
            if not btn_name:
                continue
            element_info = f"button:{btn_name}"
            if not self._test_item_exists(existing_keys, self.id, module.id, view_xml_id, element_info):
                vals_list.append({
                    'name': f"Button: {btn_string}",
                    'project_id': self.id,
                    'module_id': module.id,
                    'view_name': view_xml_id,
                    'element_info': element_info,
                    'test_type_id': self._get_test_type('Button', type_cache),
                    'source': 'auto',
                    'state': 'not_tested',
                    'sequence': seq,
                })
                existing_keys.add((self.id, module.id, view_xml_id, element_info))
                seq += 1

        # Fields with widget or required
        for fld in arch_tree.iter('field'):
            fname = fld.get('name', '')
            widget = fld.get('widget', '')
            required = fld.get('required', '')
            if not fname:
                continue
            if widget == 'statusbar':
                element_info = f"statusbar:{fname}"
                if not self._test_item_exists(existing_keys, self.id, module.id, view_xml_id, element_info):
                    vals_list.append({
                        'name': f"Statusbar: {fname}",
                        'project_id': self.id,
                        'module_id': module.id,
                        'view_name': view_xml_id,
                        'element_info': element_info,
                        'test_type_id': self._get_test_type('Statusbar', type_cache),
                        'source': 'auto',
                        'state': 'not_tested',
                        'sequence': seq,
                    })
                    existing_keys.add((self.id, module.id, view_xml_id, element_info))
                    seq += 1
            elif widget or required:
                element_info = f"field:{fname}"
                if not self._test_item_exists(existing_keys, self.id, module.id, view_xml_id, element_info):
                    label = f"Field: {fname}"
                    if widget:
                        label += f" (widget={widget})"
                    if required:
                        label += " [required]"
                    vals_list.append({
                        'name': label,
                        'project_id': self.id,
                        'module_id': module.id,
                        'view_name': view_xml_id,
                        'element_info': element_info,
                        'test_type_id': self._get_test_type('Field', type_cache),
                        'source': 'auto',
                        'state': 'not_tested',
                        'sequence': seq,
                    })
                    existing_keys.add((self.id, module.id, view_xml_id, element_info))
                    seq += 1

        # Filters
        for flt in arch_tree.iter('filter'):
            flt_name = flt.get('name', '')
            flt_string = flt.get('string', flt_name)
            if not flt_name:
                continue
            element_info = f"filter:{flt_name}"
            if not self._test_item_exists(existing_keys, self.id, module.id, view_xml_id, element_info):
                vals_list.append({
                    'name': f"Filter: {flt_string}",
                    'project_id': self.id,
                    'module_id': module.id,
                    'view_name': view_xml_id,
                    'element_info': element_info,
                    'test_type_id': self._get_test_type('Filter', type_cache),
                    'source': 'auto',
                    'state': 'not_tested',
                    'sequence': seq,
                })
                existing_keys.add((self.id, module.id, view_xml_id, element_info))
                seq += 1

        # Tabs (notebook pages)
        for page in arch_tree.iter('page'):
            page_string = page.get('string', '')
            page_name = page.get('name', page_string)
            if not page_name:
                continue
            element_info = f"tab:{page_name}"
            if not self._test_item_exists(existing_keys, self.id, module.id, view_xml_id, element_info):
                vals_list.append({
                    'name': f"Tab: {page_string or page_name}",
                    'project_id': self.id,
                    'module_id': module.id,
                    'view_name': view_xml_id,
                    'element_info': element_info,
                    'test_type_id': self._get_test_type('Tab', type_cache),
                    'source': 'auto',
                    'state': 'not_tested',
                    'sequence': seq,
                })
                existing_keys.add((self.id, module.id, view_xml_id, element_info))
                seq += 1

        return seq
