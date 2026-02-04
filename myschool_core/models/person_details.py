# models/person_details.py
import json
import logging

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


# myschool.person.details (PersonDetails.java)
class PersonDetails(models.Model):
    _name = 'myschool.person.details'
    _description = 'Persoon Details (JSON Data)'

    # Relatie naar Person (ManyToOne) - verplicht en met cascade delete
    person_id = fields.Many2one(
        'myschool.person',
        string='Persoon',
        required=True,
        ondelete='cascade',
        index=True
    )

    # Detailvelden (JSON Data als TEXT)
    full_json_string = fields.Text(string='Volledige JSON String')
    addresses = fields.Text(string='Adressen (JSON)')
    emails = fields.Text(string='E-mails (JSON)')
    comnrs = fields.Text(string='Communicatienummers (JSON)')
    bank_accounts = fields.Text(string='Bankrekeningen (JSON)')
    relations = fields.Text(string='Relaties (JSON)')
    partner = fields.Text(string='Partner (JSON)')
    children = fields.Text(string='Kinderen (JSON)')
    assignments = fields.Text(string='Assignments (JSON)')

    hoofd_ambt = fields.Char(string='Hoofd Ambt')
    extra_field_1 = fields.Char(string='Extra Veld 1 / InstNr')  # Mapped from extraField1 in Java
    is_active = fields.Boolean(string='Is Actief', default=False)

    # Computed Html fields for formatted display
    full_json_string_html = fields.Html(string='JSON Data', compute='_compute_json_html', sanitize=False)
    addresses_html = fields.Html(string='Adressen', compute='_compute_json_html', sanitize=False)
    emails_html = fields.Html(string='E-mails', compute='_compute_json_html', sanitize=False)
    comnrs_html = fields.Html(string='Communicatienummers', compute='_compute_json_html', sanitize=False)
    bank_accounts_html = fields.Html(string='Bankrekeningen', compute='_compute_json_html', sanitize=False)
    relations_html = fields.Html(string='Relaties', compute='_compute_json_html', sanitize=False)
    partner_html = fields.Html(string='Partner', compute='_compute_json_html', sanitize=False)
    children_html = fields.Html(string='Kinderen', compute='_compute_json_html', sanitize=False)
    assignments_html = fields.Html(string='Assignments', compute='_compute_json_html', sanitize=False)

    @api.depends('full_json_string', 'addresses', 'emails', 'comnrs', 'bank_accounts',
                 'relations', 'partner', 'children', 'assignments')
    def _compute_json_html(self):
        """Convert JSON text fields to formatted HTML with <pre> tags."""
        import html
        for record in self:
            for field_name in self._JSON_FIELDS:
                value = getattr(record, field_name) or ''
                # Escape HTML entities and wrap in <pre> for formatting
                escaped = html.escape(value)
                html_value = f'<pre style="background-color: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; font-family: monospace; font-size: 12px;">{escaped}</pre>' if value else ''
                setattr(record, f'{field_name}_html', html_value)

    # JSON fields that should be pretty-printed
    _JSON_FIELDS = [
        'full_json_string', 'addresses', 'emails', 'comnrs',
        'bank_accounts', 'relations', 'partner', 'children', 'assignments'
    ]

    def _reformat_json_field(self, value):
        """Reformat a JSON string with pretty-printing."""
        if not value:
            return value
        try:
            parsed = json.loads(value)
            # Check if result is still a string (double-encoded JSON)
            if isinstance(parsed, str):
                try:
                    parsed = json.loads(parsed)
                except (json.JSONDecodeError, TypeError):
                    pass
            return json.dumps(parsed, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError) as e:
            _logger.warning(f'Failed to parse JSON: {e}, value starts with: {value[:100] if value else "None"}')
            return value

    def action_reformat_json(self):
        """Reformat all JSON fields in this record with pretty-printing."""
        self.ensure_one()
        updates = {}
        for field_name in self._JSON_FIELDS:
            value = getattr(self, field_name)
            _logger.info(f'Checking field {field_name}: has_value={bool(value)}')
            if value:
                reformatted = self._reformat_json_field(value)
                # Always update if we have a value (force reformat)
                if reformatted and reformatted != value:
                    updates[field_name] = reformatted
                    _logger.info(f'Field {field_name} will be updated')

        _logger.info(f'Total fields to update: {len(updates)}')
        if updates:
            self.write(updates)
            _logger.info(f'Reformatted {len(updates)} JSON fields for PersonDetails {self.id}')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('JSON Reformatted'),
                'message': _('Reformatted %d JSON fields.') % len(updates),
                'type': 'success',
            }
        }

    @api.model
    def action_reformat_all_json(self):
        """Reformat all JSON fields in ALL PersonDetails records."""
        all_records = self.search([])
        total_updated = 0
        total_fields = 0

        _logger.info(f'Starting JSON reformat for {len(all_records)} PersonDetails records')

        for record in all_records:
            updates = {}
            for field_name in self._JSON_FIELDS:
                value = getattr(record, field_name)
                if value:
                    reformatted = record._reformat_json_field(value)
                    if reformatted and reformatted != value:
                        updates[field_name] = reformatted
                        total_fields += 1

            if updates:
                record.write(updates)
                total_updated += 1

        _logger.info(f'Reformatted {total_fields} JSON fields in {total_updated} PersonDetails records')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('JSON Reformatted'),
                'message': _('Reformatted %d fields in %d records.') % (total_fields, total_updated),
                'type': 'success',
            }
        }