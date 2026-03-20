from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        if self.env.user._is_internal():
            for company in self.env.user.company_ids.with_context(bin_size=True):
                updates = {
                    'has_background_image': bool(company.background_image),
                }
                if company.short_name:
                    updates['name'] = company.short_name
                result['user_companies']['allowed_companies'][company.id].update(updates)
        return result
