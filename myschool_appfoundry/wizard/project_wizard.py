import re

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AppfoundryProjectWizard(models.TransientModel):
    _name = 'appfoundry.project.wizard'
    _description = 'New Project Wizard'

    step = fields.Integer(default=1)

    # Step 1 — Project basics
    project_name = fields.Char('Project Name')
    project_code = fields.Char('Code', help='Short code used as item prefix, e.g. MSA')
    project_responsible_id = fields.Many2one(
        'res.users', 'Project Lead', default=lambda self: self.env.user,
    )

    # Created project reference
    project_id = fields.Many2one('appfoundry.project', 'Project', readonly=True)
    current_release_id = fields.Many2one(related='project_id.current_release_id')

    # Step 2 — App User Story
    project_description = fields.Html('App User Story')

    # Step 3 — Process Map
    create_process_map = fields.Boolean('Create a Process Map')
    process_map_name = fields.Char('Process Map Name')
    created_process_map_id = fields.Many2one('process.map', readonly=True)

    # Step 4 — User Stories
    item_ids = fields.Many2many('appfoundry.item', string='User Stories')

    # Step 5 — Prompt
    generated_prompt = fields.Text('Generated Prompt')

    step_label = fields.Char(compute='_compute_step_label')

    @api.depends('step')
    def _compute_step_label(self):
        labels = {
            1: 'Step 1 of 6 — Project Setup',
            2: 'Step 2 of 6 — App User Story',
            3: 'Step 3 of 6 — Process Map',
            4: 'Step 4 of 6 — User Stories',
            5: 'Step 5 of 6 — Review Prompt',
            6: 'Step 6 of 6 — Ready!',
        }
        for wiz in self:
            wiz.step_label = labels.get(wiz.step, '')

    # -- Navigation --

    def action_next(self):
        self.ensure_one()
        if self.step == 1:
            self._do_step_1()
        elif self.step == 2:
            self._do_step_2()
        elif self.step == 3:
            self._do_step_3()
        elif self.step == 4:
            self._do_step_4()
        self.step += 1
        if self.step == 4:
            self._refresh_items()
        return self._reopen()

    def action_previous(self):
        self.ensure_one()
        if self.step > 1:
            self.step -= 1
        if self.step == 4:
            self._refresh_items()
        return self._reopen()

    def action_skip(self):
        self.ensure_one()
        self.step += 1
        if self.step == 4:
            self._refresh_items()
        return self._reopen()

    def action_done(self):
        self.ensure_one()
        if self.project_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'appfoundry.project',
                'res_id': self.project_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {'type': 'ir.actions.act_window_close'}

    def action_skip_wizard(self):
        """Skip wizard. Create the project first if name+code are given."""
        if self.project_name and self.project_code:
            project = self.env['appfoundry.project'].create({
                'name': self.project_name,
                'code': self.project_code,
                'responsible_id': self.project_responsible_id.id or self.env.user.id,
            })
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'appfoundry.project',
                'res_id': project.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'appfoundry.project',
            'view_mode': 'form',
            'target': 'current',
        }

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'New Project Wizard',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # -- Step logic --

    def _do_step_1(self):
        if not self.project_name:
            raise ValidationError("Please enter a project name.")
        if not self.project_code:
            raise ValidationError("Please enter a project code.")
        if not self.project_id:
            project = self.env['appfoundry.project'].create({
                'name': self.project_name,
                'code': self.project_code,
                'responsible_id': self.project_responsible_id.id,
            })
            self.project_id = project
        else:
            self.project_id.write({
                'name': self.project_name,
                'code': self.project_code,
                'responsible_id': self.project_responsible_id.id,
            })

    def _do_step_2(self):
        if self.project_id:
            self.project_id.write({'description': self.project_description})

    def _do_step_3(self):
        if self.create_process_map and self.process_map_name:
            existing = self.project_id.process_map_ids.filtered(
                lambda m: m.name == self.process_map_name
            )
            if not existing:
                new_map = self.env['process.map'].create({
                    'name': self.process_map_name,
                })
                self.project_id.process_map_ids = [(4, new_map.id)]
                self.created_process_map_id = new_map

    def _do_step_4(self):
        """Re-fetch stories and generate prompt."""
        self._refresh_items()
        self._generate_prompt()

    def _refresh_items(self):
        stories = self.env['appfoundry.item'].search([
            ('project_id', '=', self.project_id.id),
            ('item_type', '=', 'story'),
        ], order='sequence')
        self.item_ids = [(6, 0, stories.ids)]

    def _generate_prompt(self):
        project = self.project_id
        stories = self.item_ids.sorted('sequence')

        lines = []
        lines.append(f'# Odoo 19 Module: {project.name} ({project.code})')
        lines.append('')

        # Description
        lines.append('## Project Description')
        if project.description:
            desc = re.sub(r'<[^>]+>', '', str(project.description)).strip()
            lines.append(desc)
        else:
            lines.append('(No description provided)')
        lines.append('')

        # User stories
        lines.append('## User Stories')
        lines.append('')
        if stories:
            priority_map = {'0': 'Low', '1': 'Normal', '2': 'High', '3': 'Critical'}
            for idx, story in enumerate(stories, 1):
                prio = priority_map.get(story.priority, 'Normal')
                lines.append(f'### {idx}. {story.display_name}')
                lines.append(f'Priority: {prio}')
                if story.description:
                    desc = re.sub(r'<[^>]+>', '', str(story.description)).strip()
                    if desc:
                        lines.append(desc)
                lines.append('')
        else:
            lines.append('(No user stories defined)')
            lines.append('')

        # Process maps
        if project.process_map_ids:
            lines.append('## Process Maps')
            for pmap in project.process_map_ids:
                lines.append(f'- {pmap.name}')
                if pmap.description:
                    lines.append(f'  {pmap.description}')
            lines.append('')

        # Implementation instructions
        lines.append('## Implementation Instructions')
        lines.append('')
        code_lower = re.sub(r'[^a-z0-9]+', '_', project.code.lower()).strip('_')
        lines.append(
            f'Build an Odoo 19 module named `{code_lower}` that implements '
            f'the user stories above.'
        )
        lines.append('')
        lines.append('Odoo 19 conventions:')
        lines.append('- Use `<list>` tag for list views (not `<tree>`)')
        lines.append('- Use `list,form` in `view_mode` (not `tree,form`)')
        lines.append('- Data files: `<odoo><data noupdate="1">...</data></odoo>`')
        lines.append('- Do NOT use `type="qweb"` on `<field>` elements in data XML')
        lines.append('- Do NOT use `<group>` inside `<search>` views')
        lines.append('- Use `widget="badge"` with decorations (not `widget="label_selection"`)')
        lines.append('')
        lines.append('Module structure:')
        lines.append('- `__manifest__.py` with proper dependencies')
        lines.append('- Models in `models/`')
        lines.append('- Views in `views/`')
        lines.append('- Security groups and access rules in `security/`')
        lines.append('')
        lines.append('Write clean, maintainable code following Odoo best practices.')

        self.generated_prompt = '\n'.join(lines)


class AppfoundryUserStoryWizard(models.TransientModel):
    _name = 'appfoundry.user.story.wizard'
    _description = 'Edit App User Story'

    project_id = fields.Many2one('appfoundry.project', required=True, readonly=True)
    description = fields.Html('App User Story')

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        project_id = defaults.get('project_id')
        if project_id:
            project = self.env['appfoundry.project'].browse(project_id)
            defaults['description'] = project.description
        return defaults

    def action_save(self):
        self.project_id.write({'description': self.description})
        return {'type': 'ir.actions.act_window_close'}


class AppfoundryPromptWizard(models.TransientModel):
    _name = 'appfoundry.prompt.wizard'
    _description = 'Generate Claude Code Prompt'

    project_id = fields.Many2one('appfoundry.project', required=True, readonly=True)
    generated_prompt = fields.Text('Generated Prompt')

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        project_id = defaults.get('project_id')
        if project_id:
            project = self.env['appfoundry.project'].browse(project_id)
            defaults['generated_prompt'] = project.generated_prompt or project._build_claude_prompt()
        return defaults


class AppfoundryIconWizard(models.TransientModel):
    _name = 'appfoundry.icon.wizard'
    _description = 'Icon Generator'

    project_id = fields.Many2one('appfoundry.project', required=True, readonly=True)
    icon_main_color = fields.Char(string='Hoofdkleur')
    icon_accent_color = fields.Char(string='Accentkleur')
    icon_module_name = fields.Char(
        string='Modulenaam',
        help='Technische modulenaam voor het icoon (bepaalt de vorm).',
    )
    icon_preview = fields.Binary(string='Icoon voorbeeld', readonly=True)

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        project_id = defaults.get('project_id')
        if project_id:
            project = self.env['appfoundry.project'].browse(project_id)
            defaults['icon_main_color'] = project.icon_main_color
            defaults['icon_accent_color'] = project.icon_accent_color
            defaults['icon_module_name'] = project.icon_module_name
            defaults['icon_preview'] = project.icon_preview
        return defaults

    def action_generate_preview(self):
        import base64
        from odoo.addons.myschool_theme.models.icon_generator import generate_icon
        for record in self:
            module_name = record.icon_module_name or record.project_id.code or ''
            icon_bytes = generate_icon(
                record.icon_main_color or '#007d8c',
                record.icon_accent_color or '#00C4D9',
                module_name=module_name.lower().replace(' ', '_'),
                display_name=record.project_id.name or module_name,
            )
            preview = base64.b64encode(icon_bytes)
            record.icon_preview = preview
            record.project_id.write({
                'icon_main_color': record.icon_main_color,
                'icon_accent_color': record.icon_accent_color,
                'icon_module_name': record.icon_module_name,
                'icon_preview': preview,
            })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Icon Generator',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply_to_menu(self):
        for record in self:
            record.project_id.write({
                'icon_main_color': record.icon_main_color,
                'icon_accent_color': record.icon_accent_color,
                'icon_module_name': record.icon_module_name,
            })
            record.project_id.action_apply_icon_to_menu()
        return {'type': 'ir.actions.act_window_close'}
