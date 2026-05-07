# -*- coding: utf-8 -*-
"""
Letter Template
===============

User-editable letter templates with field placeholders. The body is
HTML edited through Odoo's web_editor (rich text + images via the
toolbar). Placeholders use the standard Odoo inline-template syntax
``{{ object.<field> }}`` so dot-traversal of related records works
("{{ object.id_org_main.name }}" for school name).

Renders to PDF through a generic QWeb wrapper (``report_letter_document``)
that injects the substituted body inside ``web.external_layout`` —
same machinery as any other Odoo report, so paper-format and external
header/footer come for free.

Field-picker UX in the form view: pick a field from the dropdown
filtered on ``model_id`` and the read-only ``field_placeholder`` field
shows the exact ``{{ ... }}`` string ready to copy into the editor.
"""

import base64
import logging

from markupsafe import Markup

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class LetterTemplate(models.Model):
    _name = 'myschool.letter.template'
    _description = 'Letter Template'
    _inherit = ['mail.render.mixin']
    _order = 'sequence, name'

    # ---------------------------------------------------------------- identification
    name = fields.Char(string='Name', required=True, translate=True)

    code = fields.Char(
        string='Code', required=True, copy=False, index=True,
        help='Programmatic identifier — the betask cascade looks up '
             'a template by code (e.g. WELCOME_LETTER_EMPLOYEE).')

    sequence = fields.Integer(default=10)

    active = fields.Boolean(default=True)

    description = fields.Text()

    # ---------------------------------------------------------------- target model
    model_id = fields.Many2one(
        comodel_name='ir.model',
        string='Target Model',
        required=True,
        ondelete='cascade',
        domain=[('model', 'like', 'myschool.%')],
        help='The model whose records this template is rendered for. '
             'Determines which fields are available in the picker.')

    model = fields.Char(related='model_id.model', store=True, readonly=True,
                       string='Model Technical Name')

    # ---------------------------------------------------------------- person-type binding (auto-select)
    person_type_ids = fields.Many2many(
        comodel_name='myschool.person.type',
        relation='letter_template_person_type_rel',
        column1='template_id', column2='person_type_id',
        string='For Person Types',
        help='Used by the betask cascade to pick the right template '
             'after account creation. Leave empty to use this template '
             'as the fallback for all person types.')

    # ---------------------------------------------------------------- body
    body_html = fields.Html(
        string='Body',
        translate=True,
        sanitize=False,  # keep <style>, <table> etc. for richer letter layouts
        help='Letter body. Use the toolbar for formatting and images. '
             'Use {{ object.<field> }} placeholders for dynamic values; '
             'pick fields from the "Insert Field" panel below.')

    # ---------------------------------------------------------------- field picker UX
    field_picker_id = fields.Many2one(
        comodel_name='ir.model.fields',
        string='Insert Field',
        domain="[('model_id', '=', model_id), ('name', '!=', 'id')]",
        help='Pick a field to see its placeholder syntax in the box '
             'below. Copy it into the body where you want the value.',
        store=False)

    field_placeholder = fields.Char(
        string='Placeholder Syntax',
        compute='_compute_field_placeholder',
        readonly=True,
        store=False,
        help='Copy this string into the body where the field value '
             'should appear when the letter is rendered.')

    # ---------------------------------------------------------------- paper format
    paperformat_id = fields.Many2one(
        comodel_name='report.paperformat',
        string='Paper Format',
        help='Defaults to the company paper format when empty.')

    # ---------------------------------------------------------------- preview record
    preview_record_ref = fields.Reference(
        selection='_selection_preview_record',
        string='Preview Record',
        help='Pick a real record to test rendering. Used by the '
             '"Preview PDF" button — does NOT affect production rendering.')

    # =========================================================================
    # Computes
    # =========================================================================

    @api.depends('field_picker_id')
    def _compute_field_placeholder(self):
        for tpl in self:
            if tpl.field_picker_id:
                tpl.field_placeholder = (
                    '{{ object.' + tpl.field_picker_id.name + ' }}')
            else:
                tpl.field_placeholder = ''

    @api.model
    def _selection_preview_record(self):
        # Limit the Reference to myschool.* models so we don't expose
        # every model in the database in the picker.
        models_ = self.env['ir.model'].sudo().search(
            [('model', 'like', 'myschool.%')])
        return [(m.model, m.name) for m in models_]

    # =========================================================================
    # Constraints
    # =========================================================================

    _code_unique = models.Constraint(
        'UNIQUE(code)',
        'Letter template code must be unique.')

    # =========================================================================
    # Render
    # =========================================================================

    def render_html(self, record):
        """Render the body for a concrete record.

        Returns the HTML string with all ``{{ ... }}`` placeholders
        substituted. ``record`` must be of the model declared in
        ``model_id``.

        Uses Odoo's ``inline_template`` engine (Jinja-flavoured) via
        ``mail.render.mixin._render_template`` — same evaluator
        ``mail.template`` uses. Supports dot-traversal and the helpers
        ``user``, ``ctx`` etc.
        """
        self.ensure_one()
        if not record:
            raise UserError(_('No record provided for rendering.'))
        if record._name != self.model:
            raise UserError(_(
                'Record model %(rec)s does not match template model %(tpl)s'
            ) % {'rec': record._name, 'tpl': self.model})
        if not self.body_html:
            return ''
        rendered = self._render_template(
            self.body_html, record._name, [record.id],
            engine='inline_template')
        return rendered.get(record.id, '') or ''

    def render_pdf(self, record):
        """Render the template for ``record`` and return PDF bytes.

        Uses the generic ``ir.actions.report`` registered at
        ``myschool_core.action_report_letter_template``. The QWeb
        wrapper view (``report_letter_document``) calls back into
        ``render_html`` so the same substitution logic is used in
        preview and production paths.
        """
        self.ensure_one()
        report = self.env.ref(
            'myschool_core.action_report_letter_template',
            raise_if_not_found=False)
        if not report:
            raise UserError(_(
                'Letter report action is missing. Re-install / upgrade '
                'myschool_core to seed it.'))
        # The wrapper view reads target_model + target_record_id from
        # the data dict to call back into render_html.
        report_sudo = report.sudo()
        if self.paperformat_id:
            report_sudo = report_sudo.with_context(
                paperformat_id=self.paperformat_id.id)
        pdf_content, _content_type = report_sudo._render_qweb_pdf(
            report.report_name,
            res_ids=[self.id],
            data={
                'target_model': record._name,
                'target_record_id': record.id,
            })
        return pdf_content

    def generate_letter_attachment(self, record, attach=True):
        """Generate the PDF and (optionally) attach it to ``record``.

        Returns the ``ir.attachment`` record. When ``attach=False`` the
        attachment lives on the template itself instead — useful for
        previews where we don't want to litter the target record.
        """
        self.ensure_one()
        pdf_bytes = self.render_pdf(record)
        filename = self._build_attachment_filename(record)
        vals = {
            'name': filename,
            'datas': base64.b64encode(pdf_bytes),
            'mimetype': 'application/pdf',
        }
        if attach:
            vals.update({
                'res_model': record._name,
                'res_id': record.id,
            })
        else:
            vals.update({
                'res_model': self._name,
                'res_id': self.id,
            })
        attachment = self.env['ir.attachment'].sudo().create(vals)
        _logger.info(
            '[LETTER] Generated attachment %s (template=%s, record=%s/%s)',
            attachment.id, self.code, record._name, record.id)
        return attachment

    def _build_attachment_filename(self, record):
        """Build a human-friendly filename for the generated PDF.

        ``<template-code>_<record-display>_YYYYMMDD.pdf``. Spaces in
        the display name are replaced by underscores so the filename
        survives strict filesystem / email gateway checks.
        """
        from datetime import date
        record_label = (record.display_name or str(record.id)).strip()
        safe = ''.join(
            c if c.isalnum() or c in '-_.' else '_'
            for c in record_label)
        return f'{self.code}_{safe}_{date.today().strftime("%Y%m%d")}.pdf'

    # =========================================================================
    # Selection helpers used by the cascade
    # =========================================================================

    @api.model
    def find_for_person(self, person):
        """Pick the right template for a given person.

        Resolution order:
          1. Active template targeting ``myschool.person`` whose
             ``person_type_ids`` includes the person's type.
          2. Active template targeting ``myschool.person`` with empty
             ``person_type_ids`` (acts as fallback).
          3. ``False`` — caller decides whether to skip or warn.
        """
        if not person:
            return self.browse()
        Tpl = self.search([
            ('active', '=', True),
            ('model', '=', 'myschool.person'),
        ], order='sequence')
        if person.person_type_id:
            specific = Tpl.filtered(
                lambda t: person.person_type_id in t.person_type_ids)
            if specific:
                return specific[0]
        fallback = Tpl.filtered(lambda t: not t.person_type_ids)
        return fallback[0] if fallback else self.browse()

    # =========================================================================
    # UI actions
    # =========================================================================

    def action_preview_pdf(self):
        """Generate a one-off preview using ``preview_record_ref``."""
        self.ensure_one()
        if not self.preview_record_ref:
            raise UserError(_(
                'Pick a Preview Record on this template before previewing.'))
        attachment = self.generate_letter_attachment(
            self.preview_record_ref, attach=False)
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
