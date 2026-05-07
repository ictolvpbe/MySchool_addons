# -*- coding: utf-8 -*-
"""
Letter Template
===============

User-editable letter templates with field placeholders. The body is
HTML edited through Odoo's web_editor (rich text + images via the
toolbar). Placeholders use the standard Odoo inline-template syntax
``{{ object.<field> }}`` so dot-traversal of related records works
("{{ object.current_school_id.name }}" for school name).

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

try:
    from weasyprint import HTML as WeasyHTML
    WEASYPRINT_AVAILABLE = True
except ImportError:  # pragma: no cover
    WEASYPRINT_AVAILABLE = False
    _logger.warning(
        'weasyprint is not installed. Letter PDFs cannot be generated. '
        'Install with: pip install weasyprint')


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

    # ---------------------------------------------------------------- workflow trigger
    # Drives auto-selection by the cascade. Each lifecycle event has
    # its own pool of templates; resolution is scoped by trigger first,
    # then by person_type, then to the catch-all per-trigger fallback.
    trigger_event = fields.Selection(
        selection=[
            ('account_created', 'Account Created (welcome)'),
            ('account_suspended', 'Account Suspended (employee leaves)'),
            ('account_deleted', 'Account Deleted (final farewell)'),
            ('password_reset', 'Password Reset'),
            ('manual', 'Manual (admin trigger only)'),
        ],
        string='Trigger Event',
        required=True,
        default='account_created',
        index=True,
        help='When this template fires automatically. "manual" is '
             'only used via the explicit "Generate Letter" button on '
             'the person form. Templates with no trigger match for an '
             'event simply skip — no error, no fallback to a different '
             'event.')

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
        ondelete='set null',
        copy=False)
    # Note: stored as a regular Many2one. Odoo 19's webclient won't
    # render a non-stored non-computed M2O, so the cleanest path is
    # to persist the picker selection — costs one extra int column.

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

    # ---------------------------------------------------------------- email delivery
    # Auto-send the rendered PDF as an email attachment. When False the
    # cascade still generates+attaches the PDF to the target record but
    # leaves notification to the admin (manual download / print).
    auto_send_email = fields.Boolean(
        string='Auto-Send Email',
        default=False,
        help='When checked, the betask cascade emails the PDF to the '
             'address resolved through ``email_to_field`` after '
             'generation. Only honoured when the email subject/body '
             'are filled in.')

    email_to_field = fields.Char(
        string='Recipient Field',
        default='email_cloud',
        help='Field name on the target model to read the recipient '
             'email address from. Dot-traversal supported '
             '(e.g. "current_school_id.email") for related records.')

    email_subject = fields.Char(
        string='Email Subject',
        translate=True,
        help='Rendered with the same {{ object.<field> }} placeholders '
             'as the body. Required for auto-send.')

    email_body_html = fields.Html(
        string='Email Body',
        translate=True,
        sanitize=True,
        help='Body of the cover email that ships the PDF. Use the '
             'same {{ object.<field> }} placeholder syntax as the '
             'letter body. The PDF is always attached automatically.')

    email_from = fields.Char(
        string='From',
        help='Sender address. Defaults to the company email when empty.')

    # ---------------------------------------------------------------- preview record
    # Many2oneReference renders as a Many2one widget but uses the value
    # of ``model_field`` to choose which model to query at runtime.
    # That gives the picker a single dropdown of *records* of the
    # template's target model — no two-step "first pick model, then
    # record" dance like fields.Reference forces.
    preview_record_id = fields.Many2oneReference(
        string='Preview Record',
        model_field='model',
        help='Pick a real record of the target model to test rendering. '
             'Used by the "Preview PDF" button — does NOT affect '
             'production rendering.')

    # =========================================================================
    # Computes
    # =========================================================================

    @api.depends('field_picker_id')
    def _compute_field_placeholder(self):
        """Build the placeholder syntax for the picked field.

        - Binary fields → wrap in ``<img src="{{ image_url(...) }}" />``
          so admins can paste a ready-to-use image tag.
        - Anything else → plain ``{{ object.<field> }}``.

        The ``image_url`` helper is injected into the render context
        by ``_letter_render_context``; admins don't need to import or
        configure anything.
        """
        for tpl in self:
            f = tpl.field_picker_id
            if not f:
                tpl.field_placeholder = ''
                continue
            if f.ttype == 'binary':
                tpl.field_placeholder = (
                    '<img src="{{ image_url(object.' + f.name +
                    ') }}" alt="' + (f.field_description or f.name) +
                    '" style="max-width: 200px;" />')
            else:
                tpl.field_placeholder = '{{ object.' + f.name + ' }}'

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
        ``user``, ``ctx`` etc., plus our injected ``image_url`` helper
        for embedding Binary fields as ``data:`` URLs.
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
            engine='inline_template',
            add_context=self._letter_render_context())
        return rendered.get(record.id, '') or ''

    def _letter_render_context(self):
        """Extra helpers injected into inline_template eval context.

        ``image_url(value)`` — turn a Binary field value into a
        self-contained ``data:image/...;base64,...`` URL. Auto-detects
        the MIME type from the magic-byte prefix (PNG / JPEG / GIF /
        WebP / SVG). Returns an empty string when ``value`` is falsy
        so a missing logo just collapses the surrounding ``<img>``
        instead of injecting garbage.
        """
        return {
            'image_url': self._helper_image_url,
        }

    @staticmethod
    def _helper_image_url(value):
        """Convert a Binary field value to a data URL.

        Accepts both raw bytes (Odoo returns ``bytes`` for Binary
        fields stored inline) and base64-encoded ``str`` (when
        ``attachment=True`` the framework can hand back a string).
        Falls back gracefully on unknown formats.
        """
        if not value:
            return ''
        # Normalise to bytes for magic-byte sniffing.
        if isinstance(value, str):
            try:
                raw = base64.b64decode(value)
            except Exception:
                return ''
            b64_payload = value
        else:
            raw = value
            b64_payload = base64.b64encode(value).decode('ascii')
        mime = 'image/png'
        if raw.startswith(b'\x89PNG'):
            mime = 'image/png'
        elif raw.startswith(b'\xff\xd8\xff'):
            mime = 'image/jpeg'
        elif raw.startswith(b'GIF8'):
            mime = 'image/gif'
        elif raw.startswith(b'RIFF') and raw[8:12] == b'WEBP':
            mime = 'image/webp'
        elif raw.lstrip().startswith(b'<svg') or raw.lstrip().startswith(b'<?xml'):
            mime = 'image/svg+xml'
        return f'data:{mime};base64,{b64_payload}'

    def render_pdf(self, record):
        """Render the template for ``record`` and return PDF bytes.

        Uses **WeasyPrint** for HTML→PDF conversion — pure Python, no
        wkhtmltopdf system binary required. Pages, margins and page
        size are controlled through ``@page`` CSS injected from
        ``paperformat_id`` (when set) or hard-coded A4 defaults.
        """
        self.ensure_one()
        if not WEASYPRINT_AVAILABLE:
            raise UserError(_(
                'WeasyPrint is not installed on the Odoo host. '
                'Install with: pip install weasyprint'))
        body = self.render_html(record) or ''
        full_html = self._wrap_html_document(body, record)
        return WeasyHTML(string=full_html).write_pdf()

    def _wrap_html_document(self, body_html, record):
        """Wrap the rendered body in a full HTML5 document with @page
        CSS for paper format / margins.

        WeasyPrint reads CSS from ``<style>`` blocks (and from
        ``@page`` rules in particular) — that's the canonical way to
        set page size and margins in a Python-only PDF pipeline.
        Falls back to A4 with 2cm margins when no paperformat is set.
        """
        page_css = self._build_page_css()
        # Pull base CSS from ir.qweb (mostly font definitions) only if
        # we want to mirror Odoo's report look — for v1 we keep the
        # output minimal so the template's own <style> drives the
        # layout. Admins who want the corporate header/footer layout
        # can paste it into the body.
        return f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8"/>
<title>{self.code}</title>
<style>{page_css}</style>
</head>
<body>{body_html}</body>
</html>"""

    def _build_page_css(self):
        """Translate the linked ``report.paperformat`` (if any) to
        ``@page`` CSS that WeasyPrint understands.

        The Odoo paperformat record stores dimensions in mm and
        margins as numeric (also mm). WeasyPrint accepts ``cm``,
        ``mm``, ``in`` etc. directly. Defaults: A4 portrait + 2cm
        margins.
        """
        pf = self.paperformat_id
        if pf and pf.format == 'custom':
            size = f'{pf.page_width or 210}mm {pf.page_height or 297}mm'
        elif pf and pf.format:
            size = pf.format  # 'A4', 'Letter', etc — valid CSS values
        else:
            size = 'A4'
        orientation = (pf.orientation or 'Portrait').lower() if pf else 'portrait'
        if orientation == 'landscape':
            size += ' landscape'
        margin_top = (pf.margin_top if pf else None) or 20
        margin_bottom = (pf.margin_bottom if pf else None) or 20
        margin_left = (pf.margin_left if pf else None) or 20
        margin_right = (pf.margin_right if pf else None) or 20
        return (
            f'@page {{ size: {size}; '
            f'margin: {margin_top}mm {margin_right}mm '
            f'{margin_bottom}mm {margin_left}mm; }}'
        )

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
    # Email delivery
    # =========================================================================

    def _resolve_recipient_email(self, record):
        """Resolve the recipient email for ``record``.

        Walks the ``email_to_field`` path on the record using
        dot-traversal so ``"current_school_id.email"`` looks up the org's
        email address. Returns the empty string when the value is
        missing — the caller decides whether to skip or warn.
        """
        self.ensure_one()
        path = (self.email_to_field or '').strip()
        if not path:
            return ''
        target = record
        for part in path.split('.'):
            if not target:
                return ''
            target = getattr(target, part, None)
        return (target or '').strip() if isinstance(target, str) else ''

    def _render_inline(self, source, record):
        """Render ``source`` (HTML or plain text) for ``record`` using
        the same ``inline_template`` engine ``render_html`` uses.

        Same helper context (``image_url``) is injected so the email
        body can embed images alongside the body of the letter.
        """
        self.ensure_one()
        if not source or not record:
            return source or ''
        rendered = self._render_template(
            source, record._name, [record.id], engine='inline_template',
            add_context=self._letter_render_context())
        return rendered.get(record.id, '') or ''

    def send_email(self, record, attachment=None):
        """Send the rendered PDF as a cover email.

        Generates a fresh attachment if none is provided. Sends a
        ``mail.mail`` rather than threading on the record so the
        send is independent of the record's mail-thread settings —
        admins can still see the message through the message archive.

        Returns the ``mail.mail`` record (not yet sent — outbound is
        scheduled by the standard mail cron).
        """
        self.ensure_one()
        recipient = self._resolve_recipient_email(record)
        if not recipient:
            raise UserError(_(
                'No recipient email could be resolved on field "%(f)s" '
                'of record %(r)s.'
            ) % {'f': self.email_to_field, 'r': record.display_name})
        if not (self.email_subject or '').strip():
            raise UserError(_(
                'Letter template %s has no email subject — fill it in '
                'before enabling auto-send.') % self.code)

        if attachment is None:
            attachment = self.generate_letter_attachment(record, attach=True)

        subject = self._render_inline(self.email_subject, record)
        body = self._render_inline(self.email_body_html or '', record)
        sender = (self.email_from or '').strip() \
            or (self.env.company.email or '').strip() \
            or self.env.user.email or ''

        Mail = self.env['mail.mail'].sudo()
        mail = Mail.create({
            'subject': subject or self.code,
            'body_html': body or '',
            'email_from': sender,
            'email_to': recipient,
            'attachment_ids': [(4, attachment.id)],
            'auto_delete': False,
        })
        mail.send()
        _logger.info(
            '[LETTER] Sent email mail_id=%s template=%s to=%s record=%s/%s',
            mail.id, self.code, recipient, record._name, record.id)
        return mail

    # =========================================================================
    # Selection helpers used by the cascade
    # =========================================================================

    @api.model
    def find_for_person(self, person, trigger_event='account_created'):
        """Pick the right template for ``person`` and ``trigger_event``.

        Resolution order (per ``trigger_event``):
          1. Template whose ``person_type_ids`` includes the person's
             type (most specific).
          2. Template with empty ``person_type_ids`` (fallback for all
             types within this trigger).
          3. ``False`` — caller decides whether to skip or warn.

        No cross-trigger fallback: if no ``account_suspended`` template
        exists for an EMPLOYEE, the cascade skips silently rather than
        falling back to ``account_created``. Sending a "welcome" email
        when someone leaves would be incorrect.
        """
        if not person:
            return self.browse()
        Tpl = self.search([
            ('active', '=', True),
            ('model', '=', 'myschool.person'),
            ('trigger_event', '=', trigger_event),
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
        """Generate a one-off preview using ``preview_record_id``."""
        self.ensure_one()
        if not self.preview_record_id or not self.model:
            raise UserError(_(
                'Pick a Preview Record on this template before previewing.'))
        record = self.env[self.model].browse(self.preview_record_id).exists()
        if not record:
            raise UserError(_(
                'Preview Record %(rid)s of model %(model)s no longer exists.'
            ) % {'rid': self.preview_record_id, 'model': self.model})
        attachment = self.generate_letter_attachment(record, attach=False)
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
