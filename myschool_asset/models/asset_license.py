from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class AssetLicense(models.Model):
    _name = 'asset.license'
    _description = 'Asset License'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(
        string='Name',
        required=True,
    )
    asset_id = fields.Many2one(
        'asset.asset',
        string='Asset',
        ondelete='set null',
    )
    license_type = fields.Selection(
        [
            ('per_seat', 'Per Seat'),
            ('per_device', 'Per Device'),
            ('site', 'Site License'),
            ('subscription', 'Subscription'),
            ('open_source', 'Open Source'),
        ],
        string='License Type',
    )
    license_key = fields.Char(
        string='License Key',
    )
    vendor = fields.Char(
        string='Vendor',
    )
    total_seats = fields.Integer(
        string='Total Seats',
    )
    used_seats = fields.Integer(
        string='Used Seats',
    )
    available_seats = fields.Integer(
        string='Available Seats',
        compute='_compute_available_seats',
        store=True,
    )
    purchase_date = fields.Date(
        string='Purchase Date',
    )
    expiry_date = fields.Date(
        string='Expiry Date',
    )
    renewal_cost = fields.Float(
        string='Renewal Cost',
    )
    state = fields.Selection(
        [
            ('active', 'Active'),
            ('expired', 'Expired'),
            ('cancelled', 'Cancelled'),
        ],
        string='State',
        default='active',
        tracking=True,
    )
    notes = fields.Text(
        string='Notes',
    )
    org_id = fields.Many2one(
        'myschool.org',
        string='Organization',
    )

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends('total_seats', 'used_seats')
    def _compute_available_seats(self):
        for record in self:
            record.available_seats = (record.total_seats or 0) - (record.used_seats or 0)

    # ------------------------------------------------------------------
    # Cron methods
    # ------------------------------------------------------------------

    @api.model
    def _cron_check_license_expiry(self):
        """Cron job: check licenses expiring within 30 days and post a message."""
        today = fields.Date.today()
        deadline = today + relativedelta(days=30)
        licenses = self.search([
            ('expiry_date', '>=', today),
            ('expiry_date', '<=', deadline),
            ('state', '=', 'active'),
        ])
        for lic in licenses:
            lic.message_post(
                body=f'License <b>{lic.name}</b> is expiring on {lic.expiry_date}. '
                     f'Please review for renewal.',
                subject='License Expiring Soon',
                message_type='notification',
            )
        _logger.info('License expiry check completed: %d license(s) flagged.', len(licenses))
