import re
import logging

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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
    ], string='State', default='draft', required=True, tracking=True)
    version = fields.Integer(string='Version', default=1)
    org_id = fields.Many2one('myschool.org', string='Organization')

    lane_ids = fields.One2many('process.map.lane', 'map_id', string='Lanes')
    step_ids = fields.One2many('process.map.step', 'map_id', string='Steps')
    connection_ids = fields.One2many('process.map.connection', 'map_id', string='Connections')

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
            result.append({
                'name': f.name,
                'type': mapped_type,
                'label': f.field_description,
                'required': f.required,
                'relation': relation,
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
            })

        connections = []
        for conn in self.connection_ids:
            connections.append({
                'id': conn.id,
                'source_step_id': conn.source_step_id.id,
                'target_step_id': conn.target_step_id.id,
                'label': conn.label or '',
                'connection_type': conn.connection_type,
            })

        return {
            'id': self.id,
            'name': self.name,
            'description': self.description or '',
            'state': self.state,
            'lanes': lanes,
            'steps': steps,
            'connections': connections,
        }

    def save_diagram_data(self, data):
        self.ensure_one()

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

        for step_data in data.get('steps', []):
            sid = step_data.get('id')
            lane_id = step_data.get('lane_id') or False
            if lane_id and lane_id in id_map:
                lane_id = id_map[lane_id]

            vals = {
                'name': step_data.get('name', 'Step'),
                'description': step_data.get('description', ''),
                'step_type': step_data.get('step_type', 'task'),
                'x_position': step_data.get('x_position', 100),
                'y_position': step_data.get('y_position', 100),
                'width': step_data.get('width', 140),
                'height': step_data.get('height', 60),
                'lane_id': lane_id,
                'role_id': step_data.get('role_id') or False,
                'responsible': step_data.get('responsible', ''),
                'system_action': step_data.get('system_action', ''),
                'data_fields': step_data.get('data_fields', ''),
                'map_id': self.id,
            }
            if isinstance(sid, int) and sid > 0 and sid in existing_step_ids:
                Step.browse(sid).write(vals)
                incoming_step_ids.add(sid)
            else:
                new_step = Step.create(vals)
                if sid:
                    id_map[sid] = new_step.id
                incoming_step_ids.add(new_step.id)

        to_delete = existing_step_ids - incoming_step_ids
        if to_delete:
            Step.browse(list(to_delete)).unlink()

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
                if step.responsible:
                    lines.append(f"  Responsible: {step.responsible}")
                if step.system_action:
                    lines.append(f"  System action: {step.system_action}")
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

        # Derive data models
        lines.append("## Suggested Data Models")
        models_info = self._derive_models(module_name)
        for model_info in models_info:
            lines.append(f"\n### Model: {model_info['name']}")
            lines.append(f"Technical name: {model_info['technical_name']}")
            if model_info.get('fields'):
                lines.append("Fields:")
                for field in model_info['fields']:
                    lines.append(f"  - {field}")
            if model_info.get('states'):
                lines.append(f"Workflow states: {', '.join(model_info['states'])}")
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
            lines.append(f"- {model_info['technical_name']}: form view, tree view, search view")
        lines.append("")

        # Menu
        lines.append("## Menu Structure")
        lines.append(f"- Root menu: {self.name}")
        for model_info in models_info:
            lines.append(f"  - {model_info['name']}")
        lines.append("")

        # Instructions for LLM
        lines.append("## Generation Instructions")
        lines.append("Generate a complete Odoo 19 module with:")
        lines.append("1. __manifest__.py with proper dependencies (base, mail)")
        lines.append("2. Python model files for each model listed above")
        lines.append("3. XML view files (form, tree, search) for each model")
        lines.append("4. Security groups XML and ir.model.access.csv")
        lines.append("5. Menu items XML")
        lines.append("6. Workflow logic with state transitions and button actions")
        lines.append("7. Inherit mail.thread for the main model for chatter support")
        lines.append("")
        lines.append("Follow Odoo 19 conventions:")
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
            if step.step_type == 'task':
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

        # Main process model
        main_fields = ['name: Char (required)', 'description: Text', 'state: Selection']
        task_steps = self.step_ids.filtered(lambda s: s.step_type == 'task')
        for step in task_steps:
            if step.data_fields:
                for line in step.data_fields.strip().split('\n'):
                    line = line.strip()
                    if line:
                        main_fields.append(line)

        states = self._derive_workflow_states()
        models.append({
            'name': self.name,
            'technical_name': f"{module_name}.record",
            'fields': main_fields,
            'states': states,
        })

        return models
