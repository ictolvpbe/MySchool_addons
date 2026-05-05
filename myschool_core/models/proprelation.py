# models/proprelation.py
from odoo import models, fields, api
from odoo.exceptions import ValidationError


# myschool.prop.relation (PropRelation.java)
class PropRelation(models.Model):
    _name = 'myschool.proprelation'
    _description = 'Persoon/Rol/Organisatie/Period Relatie'

    #Tijdelijk
    name = fields.Char(string='Naam')

    # Many2one Relaties (naar zichzelf of naar andere modellen)
    proprelation_type_id = fields.Many2one('myschool.proprelation.type', string='Relatie Type', ondelete='restrict')

    # Person Relaties
    id_person = fields.Many2one('myschool.person', string='Persoon')
    id_person_child = fields.Many2one('myschool.person', string='Child Persoon')
    id_person_parent = fields.Many2one('myschool.person', string='Parent Persoon')

    # Role Relaties
    id_role = fields.Many2one('myschool.role', string='Rol')
    id_role_parent = fields.Many2one('myschool.role', string='Parent Rol')  # Kind Rol (idRoleChild) mist in PropRelation.java
    id_role_child = fields.Many2one('myschool.role', string='Child Rol')

    # Org Relaties
    id_org = fields.Many2one('myschool.org', string='Organisatie')
    id_org_parent = fields.Many2one('myschool.org', string='Parent Organisatie')  # Kind Org (idOrgChild) mist in PropRelation.java
    id_org_child = fields.Many2one('myschool.org', string='Child Organgistation')
    id_org_name_tree = fields.Char(related='id_org.name_tree', string='Org Tree Name', readonly=True)
    id_org_parent_name_tree = fields.Char(related='id_org_parent.name_tree', string='Parent Org Tree Name', readonly=True)
    id_org_child_name_tree = fields.Char(related='id_org_child.name_tree', string='Child Org Tree Name', readonly=True)

    # Period Relaties
    id_period = fields.Many2one('myschool.period', string='Periode')
    id_period_parent = fields.Many2one('myschool.period', string='Parent Periode')  # Kind Periode (idPeriodChild) mist in PropRelation.java
    id_period_child = fields.Many2one('myschool.period', string='Child Periode')

    # Status & Datum
    priority = fields.Integer(string='Priority')
    is_administrative = fields.Boolean(string='Is Administratief', default=False)
    is_organisational = fields.Boolean(string='Is Organisatorisch', default=False)
    is_master = fields.Boolean(string='Is Master Relatie', default=False)
    is_active = fields.Boolean(string='Actief', default=True)
    start_date = fields.Datetime(string='Startdatum')
    end_date = fields.Datetime(string='Einddatum')
    automatic_sync = fields.Boolean(string='Auto Sync', default=True, required=True)
    # ``has_accounts`` / ``has_ldap_com_group`` / ``has_ldap_sec_group`` /
    # ``has_odoo_group`` used to live here. Removed in favour of the
    # target-org's ``has_comgroup`` / ``has_secgroup`` / ``has_accounts``
    # — single source of truth for "does this org have a group / does it
    # hold accounts?". See ``Org._migrate_group_flags_from_legacy``.

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains('is_master', 'id_person', 'is_active')
    def _check_single_master(self):
        """Only one active is_master=True proprelation per person."""
        for rec in self:
            if rec.is_master and rec.id_person and rec.is_active:
                others = self.search([
                    ('id_person', '=', rec.id_person.id),
                    ('is_master', '=', True),
                    ('is_active', '=', True),
                    ('id', '!=', rec.id),
                ])
                if others:
                    raise ValidationError(
                        f'Person {rec.id_person.name} already has a master relation: {others[0].name}. '
                        f'Only one active master relation per person is allowed.'
                    )

    # -------------------------------------------------------------------------
    # Onchange
    # -------------------------------------------------------------------------

    @api.onchange('is_master')
    def _onchange_is_master(self):
        """When is_master is set, disable automatic_sync (master = manually maintained)."""
        if self.is_master:
            self.automatic_sync = False

    # -------------------------------------------------------------------------
    # CRUD overrides
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            if vals.get('is_master'):
                vals['automatic_sync'] = False
            # Stamp start_date on every freshly-active record so the
            # lifecycle window (start..end) is always populated. Callers
            # that want a specific datum can still pass start_date
            # explicitly — that wins because we use setdefault.
            if vals.get('is_active', True) and 'start_date' not in vals:
                vals['start_date'] = now
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('is_master'):
            vals['automatic_sync'] = False

        # Auto-stamp end_date / start_date when is_active flips, so that
        # every deactivation path — manual DEACT, sync cascades, cleanup
        # routines, person.unlink cascade, group-cleanup — leaves a
        # readable timestamp behind. Callers that pass an explicit
        # end_date / start_date in `vals` win.
        if 'is_active' in vals:
            now = fields.Datetime.now()
            if vals['is_active'] is False:
                # Deactivation: stamp end_date on records that flip from
                # True → False. Keep records that were already inactive
                # untouched (preserve the original end_date).
                if 'end_date' not in vals:
                    flipping = self.filtered(lambda r: r.is_active)
                    if flipping:
                        super(PropRelation, flipping).write({'end_date': now})
            elif vals['is_active'] is True:
                # Reactivation: clear end_date and refresh start_date for
                # records that flip from False → True. Re-stamping
                # start_date keeps the lifecycle window meaningful for
                # the new active period.
                flipping = self.filtered(lambda r: not r.is_active)
                if flipping:
                    upd = {}
                    if 'end_date' not in vals:
                        upd['end_date'] = False
                    if 'start_date' not in vals:
                        upd['start_date'] = now
                    if upd:
                        super(PropRelation, flipping).write(upd)

        return super().write(vals)