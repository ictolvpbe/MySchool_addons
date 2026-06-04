from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class MyschoolAsset(models.Model):
    _name = 'myschool.asset'
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
    asset_type_id = fields.Many2one(
        'myschool.asset.type',
        string='Asset Type',
        required=True,
        tracking=True,
    )
    asset_type_category_id = fields.Many2one(
        related='asset_type_id.category_id',
        string='Type Category',
        store=True,
        readonly=True,
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
    cloud_device_id = fields.Char(
        string='Google Device ID',
        help='Opaque deviceId from Google Workspace (set by the ChromeOS '
             'inventory sync). Used by CLOUD/DEVICE/MOVE betasks to '
             'translate asset_ids → API call.',
        copy=False,
        index=True,
    )
    cloud_serial = fields.Char(
        string='Google Serial Number',
        help='Serial number as reported by Google. May differ in case '
             'or formatting from the on-device sticker — keep both for '
             'reliable matching during sync.',
        copy=False,
    )
    cloud_org_unit_path = fields.Char(
        string='Google OU Path',
        help='Last-known orgUnitPath (e.g. /olvp/baple/Klas-3A). '
             'Mirrored from Google by the inventory sync, not authoritative.',
        readonly=True,
    )
    cloud_last_sync = fields.Datetime(
        string='Cloud Sync — Last Run',
        readonly=True,
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
    owner_id = fields.Many2one(
        'myschool.org',
        string='Owner (School)',
        required=True,
        tracking=True,
    )
    user_id = fields.Many2one(
        'myschool.person',
        string='User',
        tracking=True,
    )
    location_id = fields.Many2one(
        'myschool.asset',
        string='Location',
        domain="[('asset_type_id.is_room', '=', True)]",
        help='Link to a room-type asset as the physical location of this asset.',
    )
    parent_id = fields.Many2one(
        'myschool.asset',
        string='Parent Asset',
    )
    child_ids = fields.One2many(
        'myschool.asset',
        'parent_id',
        string='Child Assets',
    )
    license_ids = fields.One2many(
        'myschool.asset.license',
        'asset_id',
        string='Licenses',
    )
    checkout_ids = fields.One2many(
        'myschool.asset.checkout',
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

    # Access policy computed fields
    allowed_group_read_ids = fields.Many2many(
        'res.groups',
        'myschool_asset_read_groups_rel',
        'asset_id',
        'group_id',
        string='Groups with Read Access',
        compute='_compute_allowed_groups',
        store=True,
    )
    allowed_group_write_ids = fields.Many2many(
        'res.groups',
        'myschool_asset_write_groups_rel',
        'asset_id',
        'group_id',
        string='Groups with Write Access',
        compute='_compute_allowed_groups',
        store=True,
    )

    _asset_tag_unique = models.Constraint(
        'UNIQUE(asset_tag)',
        'The asset tag must be unique!',
    )

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends('asset_type_id', 'asset_type_id.category_id', 'owner_id')
    def _compute_allowed_groups(self):
        all_policies = self.env['myschool.access.policy'].sudo().search([])
        # Pre-compute category descendants for each policy with a category filter
        policy_cat_children = {}
        for policy in all_policies:
            if policy.asset_type_category_id:
                policy_cat_children[policy.id] = (
                    self.env['myschool.asset.type.category']
                    .search([('id', 'child_of', policy.asset_type_category_id.id)])
                )

        for asset in self:
            read_groups = self.env['res.groups']
            write_groups = self.env['res.groups']
            for policy in all_policies:
                # Check org match (empty org_id = all orgs)
                if policy.org_id and policy.org_id != asset.owner_id:
                    continue
                # Check type match (empty = all types)
                if policy.asset_type_id and policy.asset_type_id != asset.asset_type_id:
                    continue
                # Check category match including hierarchy (empty = all categories)
                if policy.asset_type_category_id:
                    if asset.asset_type_id.category_id not in policy_cat_children[policy.id]:
                        continue
                # Policy matches this asset
                read_groups |= policy.group_id
                if policy.access_level == 'write':
                    write_groups |= policy.group_id
            asset.allowed_group_read_ids = read_groups
            asset.allowed_group_write_ids = write_groups

    @api.depends(
        'purchase_price', 'depreciation_method', 'useful_life_years',
        'purchase_date', 'residual_value',
    )
    def _compute_current_value(self):
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
