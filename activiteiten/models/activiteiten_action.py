import ast

from odoo import models


class IrActionsActWindow(models.Model):
    _inherit = 'ir.actions.act_window'

    def _get_action_dict(self):
        result = super()._get_action_dict()
        if result.get('res_model') == 'activiteiten.record':
            raw_ctx = result.get('context') or '{}'
            if isinstance(raw_ctx, str):
                try:
                    ctx = ast.literal_eval(raw_ctx)
                except (ValueError, SyntaxError):
                    ctx = {}
            else:
                ctx = dict(raw_ctx)
            # Only inject defaults if no search_default is already set
            if not any(k.startswith('search_default_') for k in ctx):
                user = self.env.user
                if user.has_group('activiteiten.group_activiteiten_admin'):
                    pass  # no filter for admin
                elif user.has_group('activiteiten.group_activiteiten_boekhouding'):
                    ctx['search_default_s_code_pending'] = 1
                elif user.has_group('activiteiten.group_activiteiten_directie'):
                    ctx['search_default_to_approve'] = 1
                elif user.has_group('activiteiten.group_activiteiten_aankoop'):
                    ctx['search_default_bus_check'] = 1
                elif user.has_group('activiteiten.group_activiteiten_vervangingen'):
                    ctx['search_default_replacement_pending'] = 1
                else:
                    ctx['search_default_my_requests'] = 1
                result['context'] = ctx
        return result
