from odoo import models, fields, api


class AppfoundryTestRun(models.Model):
    """Eén geautomatiseerde test-run van een app (bv. een Odoo
    ``--test-enable``-run). Samenvattende tellers per run; aangemaakt via de
    MCP-tool ``appfoundry_report_test_run`` of handmatig. Staat náást de
    handmatige 3T-checklist (``appfoundry.test.item``)."""

    _name = 'appfoundry.test.run'
    _description = 'AppFoundry Automated Test Run'
    _order = 'run_date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    project_id = fields.Many2one(
        'appfoundry.project', required=True, ondelete='cascade', index=True)
    release_id = fields.Many2one(
        'appfoundry.release', string='Release',
        domain="[('project_id', '=', project_id)]")
    run_date = fields.Datetime(
        default=fields.Datetime.now, required=True, index=True)
    test_tag = fields.Char(
        string='Test Tag / Module',
        help='De --test-tags-waarde of module die gedraaid is.')
    total = fields.Integer(string='Total')
    failed = fields.Integer(string='Failed')
    errors = fields.Integer(string='Errors')
    skipped = fields.Integer(string='Skipped')
    passed = fields.Integer(
        string='Passed', compute='_compute_passed', store=True)
    success = fields.Boolean(compute='_compute_success', store=True)
    duration = fields.Float(string='Duration (s)')
    branch = fields.Char()
    commit = fields.Char()
    log = fields.Text(string='Output')

    @api.depends('total', 'failed', 'errors', 'skipped')
    def _compute_passed(self):
        for run in self:
            run.passed = max(
                run.total - run.failed - run.errors - run.skipped, 0)

    @api.depends('failed', 'errors')
    def _compute_success(self):
        for run in self:
            run.success = run.failed == 0 and run.errors == 0

    @api.depends('test_tag', 'project_id.code', 'project_id.name',
                 'passed', 'total', 'success')
    def _compute_name(self):
        for run in self:
            label = run.test_tag or run.project_id.code or run.project_id.name or 'run'
            status = 'OK' if run.success else 'FAIL'
            run.name = f'{label} — {status} ({run.passed}/{run.total})'
