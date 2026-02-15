import json
import uuid

from odoo import models, fields, api
from odoo.exceptions import UserError


class KnowledgeObject(models.Model):
    _name = 'knowledge.object'
    _description = 'Knowledge Object'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    KNOWLEDGE_TYPES = [
        ('procedure', 'Procedure'),
        ('qa', 'Q&A'),
        ('solution', 'Solution'),
        ('information', 'Information'),
    ]

    name = fields.Char(string='Title', required=True, tracking=True)
    details = fields.Html(string='Details')
    knowledge_type = fields.Selection(
        KNOWLEDGE_TYPES, string='Knowledge Type',
        required=True, default='information', tracking=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('review', 'Review'),
        ('published', 'Published'),
    ], string='State', default='draft', required=True, tracking=True)

    step_ids = fields.One2many(
        'knowledge.object.step', 'knowledge_object_id', string='Steps',
    )
    step_count = fields.Integer(
        string='Steps', compute='_compute_step_count', store=True,
    )
    tag_ids = fields.Many2many(
        'knowledge.tag', string='Tags',
    )
    version_ids = fields.One2many(
        'knowledge.object.version', 'knowledge_object_id', string='Versions',
    )
    version_number = fields.Integer(string='Current Version', default=0)
    share_token = fields.Char(string='Share Token', copy=False)
    share_url = fields.Char(string='Share URL', compute='_compute_share_url')

    @api.depends('step_ids')
    def _compute_step_count(self):
        for rec in self:
            rec.step_count = len(rec.step_ids)

    @api.depends('share_token')
    def _compute_share_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for rec in self:
            if rec.share_token:
                rec.share_url = f'{base_url}/knowledge/share/{rec.share_token}'
            else:
                rec.share_url = False

    # ------------------------------------------------------------------
    # State workflow
    # ------------------------------------------------------------------

    def action_submit_review(self):
        for rec in self:
            if not rec.step_ids:
                raise UserError("Cannot submit for review: no steps defined.")
            rec.state = 'review'

    def action_publish(self):
        for rec in self:
            rec.state = 'published'

    def action_reset_draft(self):
        for rec in self:
            rec.state = 'draft'

    # ------------------------------------------------------------------
    # Share link
    # ------------------------------------------------------------------

    def action_generate_share_link(self):
        self.ensure_one()
        if not self.share_token:
            self.share_token = str(uuid.uuid4())
        return {
            'type': 'ir.actions.act_url',
            'url': self.share_url,
            'target': 'new',
        }

    def action_revoke_share_link(self):
        self.ensure_one()
        self.share_token = False

    # ------------------------------------------------------------------
    # Editor actions
    # ------------------------------------------------------------------

    def action_open_editor(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'knowledge_builder_editor',
            'name': self.name,
            'context': {'active_id': self.id},
        }

    # ------------------------------------------------------------------
    # Editor API (called from OWL frontend)
    # ------------------------------------------------------------------

    def get_editor_data(self):
        self.ensure_one()
        Comment = self.env['knowledge.object.step.comment']
        steps = []
        for step in self.step_ids.sorted('sequence'):
            comments = Comment.search([('step_id', '=', step.id)], order='create_date desc')
            steps.append({
                'id': step.id,
                'name': step.name,
                'text': step.text or '',
                'image': step.image or False,
                'sequence': step.sequence,
                'comments': [{
                    'id': c.id,
                    'author': c.author_name,
                    'body': c.body,
                    'date': c.create_date.strftime('%Y-%m-%d %H:%M') if c.create_date else '',
                } for c in comments],
            })
        versions = [{
            'id': v.id,
            'version_number': v.version_number,
            'summary': v.summary or '',
            'date': v.create_date.strftime('%Y-%m-%d %H:%M') if v.create_date else '',
            'author': v.create_uid.name if v.create_uid else '',
        } for v in self.version_ids.sorted('version_number', reverse=True)[:20]]

        return {
            'id': self.id,
            'title': self.name,
            'details': self.details or '',
            'knowledge_type': self.knowledge_type,
            'state': self.state,
            'steps': steps,
            'tags': [{'id': t.id, 'name': t.name} for t in self.tag_ids],
            'versions': versions,
            'version_number': self.version_number,
            'share_token': self.share_token or False,
            'share_url': self.share_url or False,
        }

    def save_editor_data(self, data):
        self.ensure_one()
        Step = self.env['knowledge.object.step']
        Version = self.env['knowledge.object.version']

        # Create version snapshot before saving
        self.version_number += 1
        snapshot = {
            'title': self.name,
            'details': self.details or '',
            'knowledge_type': self.knowledge_type,
            'steps': [{
                'name': s.name,
                'text': s.text or '',
                'sequence': s.sequence,
            } for s in self.step_ids.sorted('sequence')],
        }
        Version.create({
            'knowledge_object_id': self.id,
            'version_number': self.version_number,
            'snapshot': json.dumps(snapshot),
            'summary': data.get('version_summary', f'Version {self.version_number}'),
        })

        # Update main object
        self.write({
            'name': data.get('title', self.name),
            'details': data.get('details', ''),
            'knowledge_type': data.get('knowledge_type', self.knowledge_type),
        })

        # Process steps
        existing_ids = set(self.step_ids.ids)
        incoming_ids = set()

        for idx, step_data in enumerate(data.get('steps', [])):
            sid = step_data.get('id')
            vals = {
                'name': step_data.get('name', 'New Step'),
                'text': step_data.get('text', ''),
                'image': step_data.get('image') or False,
                'sequence': (idx + 1) * 10,
                'knowledge_object_id': self.id,
            }
            if isinstance(sid, int) and sid > 0 and sid in existing_ids:
                Step.browse(sid).write(vals)
                incoming_ids.add(sid)
            else:
                new_step = Step.create(vals)
                incoming_ids.add(new_step.id)

        # Delete removed steps
        to_delete = existing_ids - incoming_ids
        if to_delete:
            Step.browse(list(to_delete)).unlink()

        return True

    # ------------------------------------------------------------------
    # Comments API
    # ------------------------------------------------------------------

    def add_step_comment(self, step_id, body):
        self.ensure_one()
        Comment = self.env['knowledge.object.step.comment']
        comment = Comment.create({
            'step_id': step_id,
            'body': body,
        })
        return {
            'id': comment.id,
            'author': comment.author_name,
            'body': comment.body,
            'date': comment.create_date.strftime('%Y-%m-%d %H:%M') if comment.create_date else '',
        }

    def delete_step_comment(self, comment_id):
        self.ensure_one()
        comment = self.env['knowledge.object.step.comment'].browse(comment_id)
        if comment.exists():
            comment.unlink()
        return True

    # ------------------------------------------------------------------
    # Version restore
    # ------------------------------------------------------------------

    def restore_version(self, version_id):
        self.ensure_one()
        version = self.env['knowledge.object.version'].browse(version_id)
        if not version.exists() or version.knowledge_object_id.id != self.id:
            raise UserError("Version not found.")
        data = version.get_snapshot_data()
        if data:
            self.write({
                'name': data.get('title', self.name),
                'details': data.get('details', ''),
                'knowledge_type': data.get('knowledge_type', self.knowledge_type),
            })
            # Recreate steps from snapshot
            self.step_ids.unlink()
            Step = self.env['knowledge.object.step']
            for step_data in data.get('steps', []):
                Step.create({
                    'name': step_data.get('name', 'Step'),
                    'text': step_data.get('text', ''),
                    'sequence': step_data.get('sequence', 10),
                    'knowledge_object_id': self.id,
                })
        return True

    # ------------------------------------------------------------------
    # Portal / share data
    # ------------------------------------------------------------------

    @api.model
    def get_shared_data(self, token):
        obj = self.sudo().search([('share_token', '=', token)], limit=1)
        if not obj:
            return False
        steps = []
        for step in obj.step_ids.sorted('sequence'):
            steps.append({
                'name': step.name,
                'text': step.text or '',
                'image': step.image or False,
            })
        return {
            'title': obj.name,
            'details': obj.details or '',
            'knowledge_type': obj.knowledge_type,
            'steps': steps,
        }
