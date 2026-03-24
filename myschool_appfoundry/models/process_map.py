import json
import re

from odoo import models, fields, api, Command
from odoo.exceptions import UserError

# Mapping from Field Builder notation to Odoo Python field definitions
_FB_TYPE_MAP = {
    'Char': 'fields.Char',
    'Text': 'fields.Text',
    'Html': 'fields.Html',
    'Integer': 'fields.Integer',
    'Float': 'fields.Float',
    'Monetary': 'fields.Monetary',
    'Boolean': 'fields.Boolean',
    'Date': 'fields.Date',
    'Datetime': 'fields.Datetime',
    'Selection': 'fields.Selection',
    'Many2one': 'fields.Many2one',
    'One2many': 'fields.One2many',
    'Many2many': 'fields.Many2many',
    'Binary': 'fields.Binary',
    'Image': 'fields.Image',
}


class ProcessMap(models.Model):
    _name = 'process.map'
    _description = 'Process Map'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('review', 'Review'),
        ('approved', 'Approved'),
    ], string='State', default='draft', required=True)
    version = fields.Integer(string='Version', default=1)
    org_id = fields.Many2one('myschool.org', string='Organization')

    lane_ids = fields.One2many('process.map.lane', 'map_id', string='Lanes')
    step_ids = fields.One2many('process.map.step', 'map_id', string='Steps')
    connection_ids = fields.One2many('process.map.connection', 'map_id', string='Connections')
    version_ids = fields.One2many('process.map.version', 'map_id', string='Version History')

    generated_prompt = fields.Text(string='Generated Prompt', readonly=True)

    def action_set_review(self):
        for rec in self:
            if not rec.step_ids:
                raise UserError("Cannot set to review: the process map has no steps.")
            rec.state = 'review'

    def action_approve(self):
        for rec in self:
            rec.state = 'approved'

    def action_reset_to_draft(self):
        for rec in self:
            rec.state = 'draft'
            rec.generated_prompt = False

    def action_open_canvas(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'process_mapper_canvas',
            'name': self.name,
            'context': {'active_id': self.id},
        }

    # ------------------------------------------------------------------
    # Model browser API (called from Field Builder)
    # ------------------------------------------------------------------

    @api.model
    def search_models(self, query):
        """Search ir.model by name or technical name."""
        domain = ['|',
                  ('model', 'ilike', query),
                  ('name', 'ilike', query)]
        models = self.env['ir.model'].search(domain, limit=30, order='model')
        return [{'id': m.id, 'model': m.model, 'name': m.name} for m in models]

    @api.model
    def get_model_fields(self, model_name):
        """Return fields for a given model, mapped to Odoo field type names."""
        ir_model = self.env['ir.model'].search([('model', '=', model_name)], limit=1)
        if not ir_model:
            return []

        TYPE_MAP = {
            'char': 'Char', 'text': 'Text', 'html': 'Html',
            'integer': 'Integer', 'float': 'Float', 'monetary': 'Monetary',
            'boolean': 'Boolean', 'date': 'Date', 'datetime': 'Datetime',
            'selection': 'Selection', 'many2one': 'Many2one',
            'one2many': 'One2many', 'many2many': 'Many2many',
            'binary': 'Binary',
        }
        result = []
        for f in ir_model.field_id.sorted('name'):
            if f.name.startswith('__') or f.name in ('id', 'create_uid', 'create_date',
                                                       'write_uid', 'write_date'):
                continue
            mapped_type = TYPE_MAP.get(f.ttype, 'Char')
            relation = f.relation or ''
            # Build groups string from group XML IDs
            group_names = ''
            if f.groups:
                try:
                    group_names = ','.join(
                        g.get_external_id().get(g.id, '') for g in f.groups
                    )
                except Exception:
                    group_names = ''
            # Build selection values
            sel_vals = ''
            if f.ttype == 'selection' and hasattr(f, 'selection_ids') and f.selection_ids:
                try:
                    sel_vals = json.dumps(
                        [[s.value, s.name] for s in f.selection_ids]
                    )
                except Exception:
                    sel_vals = ''
            result.append({
                'name': f.name,
                'type': mapped_type,
                'label': f.field_description,
                'required': f.required,
                'relation': relation,
                'readonly': f.readonly,
                'store': f.store,
                'index': getattr(f, 'index_type', '') or '',
                'copy': f.copied if hasattr(f, 'copied') else True,
                'translate': f.translate,
                'relation_field': f.relation_field or '',
                'relation_table': f.relation_table or '',
                'domain': f.domain or '[]',
                'on_delete': getattr(f, 'on_delete', 'set null') or 'set null',
                'help': f.help or '',
                'groups': group_names,
                'size': getattr(f, 'size', 0) or 0,
                'selection_values': sel_vals,
                'source_model': model_name,
            })
        return result

    # ------------------------------------------------------------------
    # Diagram data API (called from OWL frontend)
    # ------------------------------------------------------------------

    def get_diagram_data(self):
        self.ensure_one()
        lanes = []
        for lane in self.lane_ids.sorted('sequence'):
            lanes.append({
                'id': lane.id,
                'name': lane.name,
                'sequence': lane.sequence,
                'color': lane.color or '#E3F2FD',
                'y_position': lane.y_position,
                'height': lane.height,
                'org_id': lane.org_id.id if lane.org_id else False,
                'org_name': lane.org_id.name if lane.org_id else '',
                'role_id': lane.role_id.id if lane.role_id else False,
                'role_name': lane.role_id.name if lane.role_id else '',
            })

        steps = []
        for step in self.step_ids:
            field_records = []
            for f in step.field_ids.sorted('sequence'):
                field_records.append({
                    'id': f.id,
                    'sequence': f.sequence,
                    'name': f.name,
                    'field_description': f.field_description or '',
                    'ttype': f.ttype,
                    'required': f.required,
                    'readonly': f.readonly,
                    'store': f.store,
                    'index': f.index or '',
                    'copy': f.copy,
                    'translate': f.translate,
                    'relation': f.relation or '',
                    'relation_field': f.relation_field or '',
                    'relation_table': f.relation_table or '',
                    'domain': f.domain or '[]',
                    'on_delete': f.on_delete or 'set null',
                    'help_text': f.help_text or '',
                    'groups': f.groups or '',
                    'size': f.size or 0,
                    'digits': f.digits or '',
                    'selection_values': f.selection_values or '',
                    'default_value': f.default_value or '',
                    'source_model': f.source_model or '',
                })
            steps.append({
                'id': step.id,
                'name': step.name,
                'description': step.description or '',
                'step_type': step.step_type,
                'x_position': step.x_position,
                'y_position': step.y_position,
                'width': step.width,
                'height': step.height,
                'lane_id': step.lane_id.id if step.lane_id else False,
                'role_id': step.role_id.id if step.role_id else False,
                'role_name': step.role_id.name if step.role_id else '',
                'responsible': step.responsible or '',
                'system_action': step.system_action or '',
                'data_fields': step.data_fields or '',
                'field_records': field_records,
                'color': step.color or '',
                'icon': step.icon or '',
                'annotation': step.annotation or '',
                'sub_process_id': step.sub_process_id.id if step.sub_process_id else False,
                'sub_process_name': step.sub_process_id.name if step.sub_process_id else '',
                'form_layout': step.form_layout or '',
                'appfoundry_item_id': step.appfoundry_item_id.id if step.appfoundry_item_id else False,
                'appfoundry_item_name': step.appfoundry_item_id.display_name if step.appfoundry_item_id else '',
            })

        connections = []
        for conn in self.connection_ids:
            connections.append({
                'id': conn.id,
                'source_step_id': conn.source_step_id.id,
                'target_step_id': conn.target_step_id.id,
                'label': conn.label or '',
                'connection_type': conn.connection_type,
                'waypoints': json.loads(conn.waypoints or '[]'),
                'source_port': conn.source_port or False,
                'target_port': conn.target_port or False,
                'label_offset': json.loads(conn.label_offset or '{}'),
            })

        # Lane presets (global)
        lane_presets = []
        for preset in self.env['process.map.lane.preset'].search([]):
            lane_presets.append({
                'id': preset.id,
                'name': preset.name,
                'color': preset.color or '#E3F2FD',
            })

        return {
            'id': self.id,
            'name': self.name,
            'description': self.description or '',
            'state': self.state,
            'lanes': lanes,
            'steps': steps,
            'connections': connections,
            'lane_presets': lane_presets,
        }

    def save_diagram_data(self, data):
        self.ensure_one()

        # Create version snapshot before saving
        self._create_version_snapshot()

        Lane = self.env['process.map.lane']
        Step = self.env['process.map.step']
        Connection = self.env['process.map.connection']

        # --- Process lanes ---
        existing_lane_ids = set(self.lane_ids.ids)
        incoming_lane_ids = set()
        id_map = {}  # temp_id -> real_id

        for lane_data in data.get('lanes', []):
            lid = lane_data.get('id')
            vals = {
                'name': lane_data.get('name', 'Lane'),
                'sequence': lane_data.get('sequence', 10),
                'color': lane_data.get('color', '#E3F2FD'),
                'y_position': lane_data.get('y_position', 0),
                'height': lane_data.get('height', 150),
                'org_id': lane_data.get('org_id') or False,
                'role_id': lane_data.get('role_id') or False,
                'map_id': self.id,
            }
            if isinstance(lid, int) and lid > 0 and lid in existing_lane_ids:
                Lane.browse(lid).write(vals)
                incoming_lane_ids.add(lid)
            else:
                new_lane = Lane.create(vals)
                if lid:
                    id_map[lid] = new_lane.id
                incoming_lane_ids.add(new_lane.id)

        # Delete removed lanes
        to_delete = existing_lane_ids - incoming_lane_ids
        if to_delete:
            Lane.browse(list(to_delete)).unlink()

        # --- Process steps ---
        existing_step_ids = set(self.step_ids.ids)
        incoming_step_ids = set()
        Field = self.env['process.map.field']

        # Collect appfoundry_item_id mapping for new steps (temp IDs)
        appfoundry_by_attrs = {}
        for step_data in data.get('steps', []):
            if 'appfoundry_item_id' not in step_data:
                continue
            sid = step_data.get('id')
            item_id = step_data.get('appfoundry_item_id') or False
            if not (isinstance(sid, int) and sid > 0):
                key = (
                    step_data.get('name', ''),
                    round(step_data.get('x_position', 0)),
                    round(step_data.get('y_position', 0)),
                )
                appfoundry_by_attrs[key] = item_id

        for step_data in data.get('steps', []):
            sid = step_data.get('id')
            lane_id = step_data.get('lane_id') or False
            if lane_id and lane_id in id_map:
                lane_id = id_map[lane_id]

            sub_process_id = step_data.get('sub_process_id') or False

            # If field_records present, don't write data_fields directly
            # (let the computed field handle it)
            has_field_records = 'field_records' in step_data

            valid_step_types = {'start', 'end', 'task', 'subprocess',
                                'condition', 'gateway_exclusive', 'gateway_parallel'}
            raw_type = step_data.get('step_type', 'task')
            step_type = raw_type if raw_type in valid_step_types else 'task'

            vals = {
                'name': step_data.get('name', 'Step'),
                'description': step_data.get('description', ''),
                'step_type': step_type,
                'x_position': step_data.get('x_position', 100),
                'y_position': step_data.get('y_position', 100),
                'width': step_data.get('width', 140),
                'height': step_data.get('height', 60),
                'lane_id': lane_id,
                'role_id': step_data.get('role_id') or False,
                'responsible': step_data.get('responsible', ''),
                'system_action': step_data.get('system_action', ''),
                'color': step_data.get('color', ''),
                'icon': step_data.get('icon', ''),
                'annotation': step_data.get('annotation', ''),
                'sub_process_id': sub_process_id,
                'form_layout': step_data.get('form_layout', ''),
                'map_id': self.id,
            }
            if 'appfoundry_item_id' in step_data:
                vals['appfoundry_item_id'] = step_data.get('appfoundry_item_id') or False
            if not has_field_records:
                vals['data_fields'] = step_data.get('data_fields', '')

            if isinstance(sid, int) and sid > 0 and sid in existing_step_ids:
                step_rec = Step.browse(sid)
                step_rec.write(vals)
                incoming_step_ids.add(sid)
            else:
                step_rec = Step.create(vals)
                if sid:
                    id_map[sid] = step_rec.id
                incoming_step_ids.add(step_rec.id)

            # Process field_records if present
            if has_field_records:
                self._save_field_records(step_rec, step_data.get('field_records', []), id_map)

        to_delete = existing_step_ids - incoming_step_ids
        if to_delete:
            Step.browse(list(to_delete)).unlink()

        # Apply appfoundry_item_id to newly created steps (matched by attributes)
        if appfoundry_by_attrs:
            for step in self.step_ids:
                if step.appfoundry_item_id:
                    continue
                key = (step.name, round(step.x_position), round(step.y_position))
                item_id = appfoundry_by_attrs.get(key)
                if item_id:
                    step.appfoundry_item_id = item_id

        # --- Process connections ---
        existing_conn_ids = set(self.connection_ids.ids)
        incoming_conn_ids = set()

        for conn_data in data.get('connections', []):
            cid = conn_data.get('id')
            source_id = conn_data.get('source_step_id')
            target_id = conn_data.get('target_step_id')
            if source_id and source_id in id_map:
                source_id = id_map[source_id]
            if target_id and target_id in id_map:
                target_id = id_map[target_id]

            vals = {
                'source_step_id': source_id,
                'target_step_id': target_id,
                'label': conn_data.get('label', ''),
                'connection_type': conn_data.get('connection_type', 'sequence'),
                'waypoints': json.dumps(conn_data.get('waypoints', [])),
                'source_port': conn_data.get('source_port') or False,
                'target_port': conn_data.get('target_port') or False,
                'label_offset': json.dumps(conn_data.get('label_offset', {})),
                'map_id': self.id,
            }
            if isinstance(cid, int) and cid > 0 and cid in existing_conn_ids:
                Connection.browse(cid).write(vals)
                incoming_conn_ids.add(cid)
            else:
                new_conn = Connection.create(vals)
                incoming_conn_ids.add(new_conn.id)

        to_delete = existing_conn_ids - incoming_conn_ids
        if to_delete:
            Connection.browse(list(to_delete)).unlink()

        return True

    # ------------------------------------------------------------------
    # Field records helper
    # ------------------------------------------------------------------

    def _save_field_records(self, step_rec, field_records_data, id_map):
        """Create/update/delete process.map.field records for a step.

        Uses Odoo Command API for reliable One2many writes.
        """
        FIELD_ATTRS = [
            'sequence', 'name', 'field_description', 'ttype', 'required',
            'readonly', 'store', 'index', 'copy', 'translate',
            'relation', 'relation_field', 'relation_table', 'domain', 'on_delete',
            'help_text', 'groups', 'size', 'digits', 'selection_values',
            'default_value', 'source_model',
        ]

        existing_field_ids = set(step_rec.field_ids.ids)
        incoming_field_ids = set()
        explicit_deletes = set()
        commands = []

        for seq, fdata in enumerate(field_records_data):
            # Handle explicit delete markers from frontend
            if fdata.get('_delete'):
                fid = fdata.get('id')
                if isinstance(fid, int) and fid > 0 and fid in existing_field_ids:
                    explicit_deletes.add(fid)
                continue

            fid = fdata.get('id')
            vals = {'sequence': fdata.get('sequence', (seq + 1) * 10)}
            for attr in FIELD_ATTRS:
                if attr in fdata and attr != 'sequence':
                    vals[attr] = fdata[attr]
            vals.setdefault('name', 'field')
            vals.setdefault('ttype', 'char')

            if isinstance(fid, int) and fid > 0 and fid in existing_field_ids:
                # Update existing field
                commands.append(Command.update(fid, vals))
                incoming_field_ids.add(fid)
            else:
                # Create new field
                commands.append(Command.create(vals))

        # Delete: explicit deletes + any existing fields not in incoming set
        to_delete = explicit_deletes | (existing_field_ids - incoming_field_ids)
        for fid in to_delete:
            commands.append(Command.delete(fid))

        if commands:
            step_rec.write({'field_ids': commands})

    # ------------------------------------------------------------------
    # Version history
    # ------------------------------------------------------------------

    def _create_version_snapshot(self):
        """Create a version snapshot of the current diagram state."""
        self.ensure_one()
        if not self.step_ids and not self.lane_ids:
            return
        data = self.get_diagram_data()
        last_version = self.env['process.map.version'].search(
            [('map_id', '=', self.id)], limit=1, order='version_number desc')
        next_num = (last_version.version_number + 1) if last_version else 1
        self.env['process.map.version'].create({
            'map_id': self.id,
            'version_number': next_num,
            'snapshot': json.dumps(data),
        })

    def get_versions(self):
        """Return version list for the frontend version panel."""
        self.ensure_one()
        versions = self.env['process.map.version'].search([('map_id', '=', self.id)], order='version_number desc')
        return [{
            'id': v.id,
            'version_number': v.version_number,
            'create_date': fields.Datetime.to_string(v.create_date),
            'create_uid_name': v.create_uid.name if v.create_uid else '',
            'note': v.note or '',
        } for v in versions]

    def restore_version(self, version_id):
        """Restore diagram from a version snapshot."""
        self.ensure_one()
        version = self.env['process.map.version'].browse(version_id)
        if not version.exists() or version.map_id.id != self.id:
            raise UserError("Invalid version.")
        data = json.loads(version.snapshot)
        self.save_diagram_data(data)
        return True

    # ------------------------------------------------------------------
    # Prompt generation
    # ------------------------------------------------------------------

    def action_generate_prompt(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError("Process must be approved before generating a prompt.")

        module_name = self._slugify(self.name)
        prompt = self._build_prompt(module_name)
        self.generated_prompt = prompt
        return True

    def _slugify(self, text):
        text = text.lower().strip()
        text = re.sub(r'[^a-z0-9]+', '_', text)
        return text.strip('_')

    def _parse_field_builder_line(self, line):
        """Parse a Field Builder line like 'field_name: Type (relation, required)'
        into a proper Odoo field definition string."""
        line = line.strip()
        if not line:
            return None
        match = re.match(r'^(\w+)\s*:\s*(\w+)\s*(.*)$', line)
        if not match:
            return f"    # {line}"
        name = match.group(1)
        ftype = match.group(2)
        options = match.group(3).strip().strip('()').strip() if match.group(3) else ''

        odoo_type = _FB_TYPE_MAP.get(ftype, 'fields.Char')
        parts = [p.strip() for p in options.split(',') if p.strip()] if options else []

        required = 'required' in parts
        relation = ''
        other_parts = []
        for p in parts:
            if p == 'required':
                continue
            if ftype in ('Many2one', 'One2many', 'Many2many') and '.' in p:
                relation = p
            else:
                other_parts.append(p)

        # Build field definition
        string_label = name.replace('_', ' ').title()
        args = []
        if ftype in ('Many2one', 'One2many', 'Many2many') and relation:
            args.append(f"'{relation}'")
        args.append(f"string='{string_label}'")
        if required:
            args.append("required=True")

        return f"    {name} = {odoo_type}({', '.join(args)})"

    def _build_prompt(self, module_name):
        lines = []
        lines.append(f"# Odoo 19 Module Specification: {module_name}")
        lines.append("")
        lines.append("## Purpose")
        lines.append(f"Module name: {module_name}")
        lines.append(f"Display name: {self.name}")
        if self.description:
            lines.append(f"Description: {self.description}")
        if self.org_id:
            lines.append(f"Organization: {self.org_id.name}")
        lines.append("")

        # Lanes → roles / departments
        lines.append("## Actors / Departments (derived from swimlanes)")
        for lane in self.lane_ids.sorted('sequence'):
            role_info = f" (Role: {lane.role_id.name})" if lane.role_id else ""
            org_info = f" (Org: {lane.org_id.name})" if lane.org_id else ""
            lines.append(f"- {lane.name}{role_info}{org_info}")
        lines.append("")

        # Steps → grouped by lane
        lines.append("## Process Steps")
        lane_map = {}
        for step in self.step_ids:
            lane_name = step.lane_id.name if step.lane_id else '(No lane)'
            lane_map.setdefault(lane_name, []).append(step)

        for lane_name, steps in lane_map.items():
            lines.append(f"\n### {lane_name}")
            for step in steps:
                type_label = dict(step._fields['step_type'].selection).get(step.step_type, step.step_type)
                lines.append(f"- **{step.name}** [{type_label}]")
                if step.description:
                    lines.append(f"  Description: {step.description}")
                if step.annotation:
                    lines.append(f"  Business rule: {step.annotation}")
                if step.responsible:
                    lines.append(f"  Responsible: {step.responsible}")
                if step.system_action:
                    lines.append(f"  System action: {step.system_action}")
                if step.sub_process_id:
                    lines.append(f"  Sub-process: {step.sub_process_id.name}")
                if step.data_fields:
                    lines.append(f"  Data/fields needed: {step.data_fields}")
        lines.append("")

        # Connections → workflow flow
        lines.append("## Process Flow (connections)")
        for conn in self.connection_ids:
            label = f' [{conn.label}]' if conn.label else ''
            lines.append(f"- {conn.source_step_id.name} --> {conn.target_step_id.name}{label}")
        lines.append("")

        # Derive workflow states from flow
        lines.append("## Suggested Workflow States")
        states = self._derive_workflow_states()
        for i, state in enumerate(states):
            lines.append(f"{i + 1}. {state}")
        lines.append("")

        # Derive data models with proper field definitions
        lines.append("## Suggested Data Models")
        models_info = self._derive_models(module_name)
        for model_info in models_info:
            lines.append(f"\n### Model: {model_info['name']}")
            lines.append(f"Technical name: {model_info['technical_name']}")
            if model_info.get('field_definitions'):
                lines.append("```python")
                for fdef in model_info['field_definitions']:
                    lines.append(fdef)
                lines.append("```")
            elif model_info.get('fields'):
                lines.append("Fields:")
                for field in model_info['fields']:
                    lines.append(f"  - {field}")
            if model_info.get('states'):
                lines.append(f"Workflow states: {', '.join(model_info['states'])}")
        lines.append("")

        # Business rules from annotations
        annotated_steps = self.step_ids.filtered(lambda s: s.annotation)
        if annotated_steps:
            lines.append("## Business Rules (from step annotations)")
            for step in annotated_steps:
                lines.append(f"- **{step.name}**: {step.annotation}")
            lines.append("")

        # Security groups
        lines.append("## Security Groups")
        for lane in self.lane_ids.sorted('sequence'):
            group_name = self._slugify(lane.name)
            lines.append(f"- group_{group_name}: Access for {lane.name}")
        lines.append("")

        # Views
        lines.append("## Views Required")
        for model_info in models_info:
            lines.append(f"- {model_info['technical_name']}: form view, list view, search view")
        lines.append("")

        # Menu
        lines.append("## Menu Structure")
        lines.append(f"- Root menu: {self.name}")
        for model_info in models_info:
            lines.append(f"  - {model_info['name']}")
        lines.append("")

        # --- Appfoundry: User Stories / Requirements ---
        linked_stories = self.step_ids.mapped('appfoundry_item_id').filtered(
            lambda s: s.item_type == 'story')
        project = self.env['appfoundry.project'].search(
            [('process_map_ids', 'in', self.ids)], limit=1)
        unlinked_stories = self.env['appfoundry.item']
        if project:
            all_project_stories = project.story_ids
            unlinked_stories = all_project_stories - linked_stories

        if linked_stories or unlinked_stories:
            lines.append("")
            lines.append("## User Stories / Requirements")
            if project:
                lines.append(f"Project: {project.name} ({project.code})")
            lines.append("")

            priority_map = {'0': 'Low', '1': 'Normal', '2': 'High', '3': 'Critical'}

            if linked_stories:
                lines.append("### Stories linked to process steps")
                for story in linked_stories.sorted('sequence'):
                    prio = priority_map.get(story.priority, story.priority)
                    steps = self.step_ids.filtered(
                        lambda s: s.appfoundry_item_id.id == story.id)
                    step_names = ', '.join(steps.mapped('name'))
                    lines.append(f"- **{story.display_name}** [Priority: {prio}]")
                    lines.append(f"  Linked steps: {step_names}")
                    if story.description:
                        desc = re.sub(r'<[^>]+>', '', str(story.description)).strip()
                        if desc:
                            lines.append(f"  Description: {desc}")
                    if story.story_points:
                        lines.append(f"  Story points: {story.story_points}")
                    if story.tag_ids:
                        lines.append(f"  Tags: {', '.join(story.tag_ids.mapped('name'))}")
                lines.append("")

            if unlinked_stories:
                lines.append("### Additional stories (not linked to process steps)")
                for story in unlinked_stories.sorted('sequence'):
                    prio = priority_map.get(story.priority, story.priority)
                    lines.append(f"- **{story.display_name}** [Priority: {prio}]")
                    if story.description:
                        desc = re.sub(r'<[^>]+>', '', str(story.description)).strip()
                        if desc:
                            lines.append(f"  Description: {desc}")
                    if story.story_points:
                        lines.append(f"  Story points: {story.story_points}")
                lines.append("")

        # Inject user story references into Process Steps section
        # (done as a post-pass on the accumulated prompt text)
        step_story_map = {}
        for step in self.step_ids:
            if step.appfoundry_item_id:
                step_story_map[step.name] = step.appfoundry_item_id.display_name
        if step_story_map:
            prompt_so_far = '\n'.join(lines)
            for step_name, story_name in step_story_map.items():
                marker = f"- **{step_name}**"
                if marker in prompt_so_far:
                    prompt_so_far = prompt_so_far.replace(
                        marker,
                        f"{marker}\n  User story: {story_name}",
                        1,
                    )
            lines = prompt_so_far.split('\n')

        # Instructions for LLM
        lines.append("## Generation Instructions")
        lines.append("Generate a complete Odoo 19 module with:")
        lines.append("1. __manifest__.py with proper dependencies (base, mail)")
        lines.append("2. Python model files for each model listed above")
        lines.append("3. XML view files (form, list, search) for each model")
        lines.append("4. Security groups XML and ir.model.access.csv")
        lines.append("5. Menu items XML")
        lines.append("6. Workflow logic with state transitions and button actions")
        lines.append("7. Inherit mail.thread for the main model for chatter support")
        lines.append("")
        lines.append("Follow Odoo 19 conventions:")
        lines.append("- Use <list> tag (NOT <tree>) for list views")
        lines.append("- Use OWL2 for any custom frontend components")
        lines.append("- Use statusbar widget for state fields")
        lines.append("- Use proper field types (Many2one, One2many, Selection, etc.)")

        return '\n'.join(lines)

    def _derive_workflow_states(self):
        """Trace the process flow from start to end to derive workflow states."""
        start_steps = self.step_ids.filtered(lambda s: s.step_type == 'start')
        if not start_steps:
            return ['draft', 'done']

        states = []
        visited = set()

        def trace(step):
            if step.id in visited:
                return
            visited.add(step.id)
            if step.step_type in ('task', 'subprocess'):
                state_name = self._slugify(step.name)
                states.append(state_name)
            elif step.step_type == 'condition':
                states.append(f"check_{self._slugify(step.name)}")
            outgoing = self.connection_ids.filtered(lambda c: c.source_step_id.id == step.id)
            for conn in outgoing:
                trace(conn.target_step_id)

        for start in start_steps:
            trace(start)

        if not states:
            states = ['draft', 'done']
        return states

    def _derive_models(self, module_name):
        """Derive suggested data models from the process steps."""
        models = []

        # Main process model - try to produce proper field definitions
        base_field_defs = [
            "    name = fields.Char(string='Name', required=True)",
            "    description = fields.Text(string='Description')",
            "    state = fields.Selection([], string='State', default='draft', required=True)",
        ]
        raw_fields = ['name: Char (required)', 'description: Text', 'state: Selection']
        field_definitions = list(base_field_defs)

        task_steps = self.step_ids.filtered(lambda s: s.step_type in ('task', 'subprocess'))
        seen_names = {'name', 'description', 'state'}
        for step in task_steps:
            if step.data_fields:
                for line in step.data_fields.strip().split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    # Check for duplicate field names
                    match = re.match(r'^(\w+)\s*:', line)
                    fname = match.group(1) if match else None
                    if fname and fname in seen_names:
                        continue
                    if fname:
                        seen_names.add(fname)
                    raw_fields.append(line)
                    parsed = self._parse_field_builder_line(line)
                    if parsed:
                        field_definitions.append(parsed)

        states = self._derive_workflow_states()
        models.append({
            'name': self.name,
            'technical_name': f"{module_name}.record",
            'fields': raw_fields,
            'field_definitions': field_definitions,
            'states': states,
        })

        return models

    # ------------------------------------------------------------------
    # Appfoundry: user story helpers (called from OWL frontend)
    # ------------------------------------------------------------------

    @api.model
    def search_user_stories(self, query='', project_id=False):
        """Search user stories for the canvas properties panel."""
        domain = [('item_type', '=', 'story')]
        if query:
            domain.append(('display_name', 'ilike', query))
        if project_id:
            domain.append(('project_id', '=', project_id))
        stories = self.env['appfoundry.item'].search(domain, limit=20, order='sequence')
        return [{'id': s.id, 'name': s.display_name} for s in stories]

    @api.model
    def create_user_story(self, name, project_id):
        """Create a new user story and return its data."""
        project = self.env['appfoundry.project'].browse(project_id)
        story = self.env['appfoundry.item'].create({
            'name': name,
            'item_type': 'story',
            'project_id': project_id,
            'release_id': project.current_release_id.id,
        })
        return {'id': story.id, 'name': story.display_name}
