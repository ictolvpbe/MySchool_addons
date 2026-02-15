import json

from odoo import http
from odoo.http import request


class KnowledgeShareController(http.Controller):

    @http.route('/knowledge/share/<string:token>', type='http', auth='public', website=False)
    def share_knowledge(self, token, **kwargs):
        data = request.env['knowledge.object'].sudo().get_shared_data(token)
        if not data:
            return request.not_found()
        return request.render('knowledge_builder.share_page', {
            'data': data,
            'data_json': json.dumps(data),
        })
