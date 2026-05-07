from odoo import _, models, fields
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = 'res.company'

    school_id = fields.Many2one('myschool.org', string='School')
    short_name = fields.Char(
        string='Korte naam',
        help='Verkorte naam voor de bedrijfskiezer (rechts bovenaan). '
             'Indien leeg wordt de volledige naam gebruikt.',
    )
    email_domain = fields.Char(
        string='E-mail domein',
        help='Extern e-maildomein van de gekoppelde organisatie. '
             'Beheerd door de bedrijfssync (myschool.org.domain_external).',
    )

    def write(self, vals):
        # Lock the company name when it is sync-managed: the linked
        # myschool.org's displayname is the single source of truth, and
        # diverging the two breaks the sync's match-by-name fallback.
        # The sync itself bypasses this guard via context.
        if 'name' in vals and not self.env.context.get('skip_school_rename_guard'):
            for company in self:
                if company.school_id and company.name != vals['name']:
                    raise UserError(_(
                        "De naam van Company '%(current)s' wordt beheerd "
                        "via de gekoppelde organisatie '%(org)s' "
                        "(displayname). Pas de displayname op de "
                        "organisatie aan i.p.v. de Company-naam.",
                        current=company.name,
                        org=company.school_id.display_name or company.school_id.name,
                    ))
        return super().write(vals)
