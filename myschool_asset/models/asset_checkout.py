from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AssetCheckout(models.Model):
    _name = 'asset.checkout'
    _description = 'Asset Checkout'
    _order = 'checkout_date desc'

    asset_id = fields.Many2one(
        'asset.asset',
        string='Asset',
        required=True,
        ondelete='cascade',
    )
    person_id = fields.Many2one(
        'myschool.person',
        string='Person',
        required=True,
    )
    checkout_date = fields.Datetime(
        string='Checkout Date',
        default=fields.Datetime.now,
        required=True,
    )
    expected_return_date = fields.Date(
        string='Expected Return Date',
    )
    actual_return_date = fields.Datetime(
        string='Actual Return Date',
    )
    state = fields.Selection(
        [
            ('checked_out', 'Checked Out'),
            ('returned', 'Returned'),
            ('overdue', 'Overdue'),
        ],
        string='State',
        default='checked_out',
    )
    notes = fields.Text(
        string='Notes',
    )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_return(self):
        """Mark the checkout as returned."""
        for record in self:
            record.write({
                'actual_return_date': fields.Datetime.now(),
                'state': 'returned',
            })

    # ------------------------------------------------------------------
    # Cron methods
    # ------------------------------------------------------------------

    @api.model
    def _cron_check_overdue(self):
        """Cron job: find checkouts past expected return date and mark them overdue."""
        today = fields.Date.today()
        overdue = self.search([
            ('expected_return_date', '<', today),
            ('state', '=', 'checked_out'),
        ])
        if overdue:
            overdue.write({'state': 'overdue'})
        _logger.info('Overdue checkout check completed: %d checkout(s) marked overdue.', len(overdue))
