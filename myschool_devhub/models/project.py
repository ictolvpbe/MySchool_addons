import logging

from lxml import etree

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class DevhubProject(models.Model):
    _name = 'devhub.project'
    _description = 'DevHub Project'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(string='Code', required=True, help='Short code used as item prefix, e.g. MSA')
    description = fields.Html()
    responsible_id = fields.Many2one('res.users', string='Project Lead')
    member_ids = fields.Many2many('res.users', string='Team Members')
    item_ids = fields.One2many('devhub.item', 'project_id', string='Items')
    story_ids = fields.One2many(
        'devhub.item', 'project_id', string='User Stories',
        domain=[('item_type', '=', 'story')],
    )
    bug_ids = fields.One2many(
        'devhub.item', 'project_id', string='Bugs',
        domain=[('item_type', '=', 'bug')],
    )
    improvement_ids = fields.One2many(
        'devhub.item', 'project_id', string='Improvements',
        domain=[('item_type', '=', 'improvement')],
    )
    sprint_ids = fields.One2many('devhub.sprint', 'project_id', string='Sprints')
    release_ids = fields.One2many('devhub.release', 'project_id', string='Releases')
    process_map_ids = fields.Many2many('process.map', string='Process Maps')
    module_ids = fields.Many2many(
        'ir.module.module', 'devhub_project_module_rel',
        string='Linked Modules',
    )
    test_item_ids = fields.One2many('devhub.test.item', 'project_id', string='Test Items')
    test_item_count = fields.Integer(compute='_compute_test_item_count', string='Test Items')
    test_progress = fields.Float(compute='_compute_test_progress', string='Test Progress')
    is_active = fields.Boolean(default=True)
    item_count = fields.Integer(compute='_compute_item_count', string='Item Count')
    open_bug_count = fields.Integer(compute='_compute_open_bug_count', string='Open Bugs')

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

    def action_open_test_items(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - Things To Test',
            'res_model': 'devhub.test.item',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'search_default_group_view': 1,
            },
        }

    # ------------------------------------------------------------------
    # 3T Auto-Generation Engine
    # ------------------------------------------------------------------

    def _get_test_type(self, name, cache):
        """Get or cache a test type by name."""
        if name not in cache:
            tt = self.env['devhub.test.type'].search([('name', '=', name)], limit=1)
            cache[name] = tt.id if tt else False
        return cache[name]

    def _test_item_exists(self, existing_keys, project_id, module_id, view_name, element_info):
        """Check if a test item already exists for dedup."""
        return (project_id, module_id, view_name or '', element_info or '') in existing_keys

    def action_generate_test_items(self):
        """Auto-generate test items from linked modules' views, menus, and actions."""
        self.ensure_one()
        TestItem = self.env['devhub.test.item']
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
