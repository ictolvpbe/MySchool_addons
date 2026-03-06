from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class AssetAsset(models.Model):
    _name = 'asset.asset'
    _description = 'Asset'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
    )
    asset_tag = fields.Char(
        string='Asset Tag',
        copy=False,
        help='Unique identifier / barcode for the asset',
    )
    category_id = fields.Many2one(
        'asset.category',
        string='Category',
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('procurement', 'Procurement'),
            ('received', 'Received'),
            ('deployed', 'Deployed'),
            ('maintenance', 'Maintenance'),
            ('retired', 'Retired'),
            ('disposed', 'Disposed'),
        ],
        string='State',
        default='draft',
        required=True,
        tracking=True,
    )
    description = fields.Text(
        string='Description',
    )
    serial_number = fields.Char(
        string='Serial Number',
    )
    model_name = fields.Char(
        string='Model',
    )
    manufacturer = fields.Char(
        string='Manufacturer',
    )
    purchase_date = fields.Date(
        string='Purchase Date',
    )
    purchase_price = fields.Float(
        string='Purchase Price',
    )
    warranty_expiry = fields.Date(
        string='Warranty Expiry',
    )
    depreciation_method = fields.Selection(
        [
            ('straight_line', 'Straight Line'),
            ('declining', 'Declining Balance'),
        ],
        string='Depreciation Method',
    )
    useful_life_years = fields.Integer(
        string='Useful Life (Years)',
    )
    residual_value = fields.Float(
        string='Residual Value',
    )
    current_value = fields.Float(
        string='Current Value',
        compute='_compute_current_value',
        store=True,
    )
    location_building = fields.Char(
        string='Building',
    )
    location_room = fields.Char(
        string='Room',
    )
    org_id = fields.Many2one(
        'myschool.org',
        string='Organization',
        tracking=True,
    )
    assigned_to_id = fields.Many2one(
        'myschool.person',
        string='Assigned To',
        tracking=True,
    )
    parent_id = fields.Many2one(
        'asset.asset',
        string='Parent Asset',
    )
    child_ids = fields.One2many(
        'asset.asset',
        'parent_id',
        string='Child Assets',
    )
    license_ids = fields.One2many(
        'asset.license',
        'asset_id',
        string='Licenses',
    )
    checkout_ids = fields.One2many(
        'asset.checkout',
        'asset_id',
        string='Checkouts',
    )
    barcode = fields.Char(
        string='Barcode',
    )
    image = fields.Image(
        string='Image',
        max_width=256,
        max_height=256,
    )
    notes = fields.Html(
        string='Notes',
    )
    supplier = fields.Char(
        string='Supplier',
    )
    supplier_contact = fields.Char(
        string='Supplier Contact',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )

    _asset_tag_unique = models.Constraint('UNIQUE(asset_tag)', 'The asset tag must be unique!')

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends(
        'purchase_price', 'depreciation_method', 'useful_life_years',
        'purchase_date', 'residual_value',
    )
    def _compute_current_value(self):
        """Compute the current depreciated value of the asset."""
        today = fields.Date.today()
        for asset in self:
            if not asset.purchase_price or not asset.purchase_date or not asset.useful_life_years:
                asset.current_value = asset.purchase_price or 0.0
                continue

            elapsed_years = (today - asset.purchase_date).days / 365.25
            if elapsed_years < 0:
                asset.current_value = asset.purchase_price
                continue

            residual = asset.residual_value or 0.0

            if elapsed_years >= asset.useful_life_years:
                asset.current_value = residual
                continue

            method = asset.depreciation_method or 'straight_line'

            if method == 'straight_line':
                annual_depreciation = (asset.purchase_price - residual) / asset.useful_life_years
                value = asset.purchase_price - (annual_depreciation * elapsed_years)
                asset.current_value = max(value, residual)

            elif method == 'declining':
                rate = 2.0 / asset.useful_life_years
                value = asset.purchase_price
                full_years = int(elapsed_years)
                for _i in range(full_years):
                    depreciation = value * rate
                    value -= depreciation
                    if value <= residual:
                        value = residual
                        break
                # Apply partial year depreciation
                partial = elapsed_years - full_years
                if value > residual and partial > 0:
                    depreciation = value * rate * partial
                    value -= depreciation
                asset.current_value = max(value, residual)
            else:
                asset.current_value = asset.purchase_price

    # ------------------------------------------------------------------
    # State transition actions
    # ------------------------------------------------------------------

    def action_receive(self):
        for record in self:
            record.state = 'received'

    def action_deploy(self):
        for record in self:
            record.state = 'deployed'

    def action_maintenance(self):
        for record in self:
            record.state = 'maintenance'

    def action_retire(self):
        for record in self:
            record.state = 'retired'

    def action_dispose(self):
        for record in self:
            record.state = 'disposed'

    def action_reset_draft(self):
        for record in self:
            record.state = 'draft'

    # ------------------------------------------------------------------
    # Cron methods
    # ------------------------------------------------------------------

    @api.model
    def _check_warranty_expiry(self):
        """Cron job: find assets with warranty expiring within 30 days and log an activity."""
        today = fields.Date.today()
        deadline = today + relativedelta(days=30)
        assets = self.search([
            ('warranty_expiry', '>=', today),
            ('warranty_expiry', '<=', deadline),
            ('state', 'not in', ['retired', 'disposed']),
        ])
        activity_type = self.env.ref('mail.mail_activity_data_warning', raise_if_not_found=False)
        for asset in assets:
            existing = self.env['mail.activity'].search([
                ('res_model', '=', self._name),
                ('res_id', '=', asset.id),
                ('activity_type_id', '=', activity_type.id if activity_type else False),
                ('summary', '=', 'Warranty Expiring Soon'),
            ], limit=1)
            if not existing:
                asset.activity_schedule(
                    'mail.mail_activity_data_warning',
                    date_deadline=asset.warranty_expiry,
                    summary='Warranty Expiring Soon',
                    note=f'Warranty for asset <b>{asset.name}</b> ({asset.asset_tag or "N/A"}) '
                         f'expires on {asset.warranty_expiry}.',
                )
        _logger.info('Warranty expiry check completed: %d asset(s) flagged.', len(assets))
