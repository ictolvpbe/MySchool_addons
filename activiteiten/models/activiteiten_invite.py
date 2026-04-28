from odoo import models, fields, api

LATE_STATES = ('approved', 's_code', 'vervanging', 'done')


class ActiviteitenInvite(models.Model):
    _name = 'activiteiten.invite'
    _description = 'Activiteiten Uitnodiging'
    _inherit = ['mail.thread']
    _rec_name = 'person_id'

    activiteit_id = fields.Many2one(
        'activiteiten.record', required=True, ondelete='cascade',
    )
    activiteit_titel = fields.Char(
        related='activiteit_id.titel', string='Activiteit',
    )
    activiteit_state = fields.Selection(
        related='activiteit_id.state', string='Status aanvraag',
    )
    invited_by = fields.Many2one(
        related='activiteit_id.create_uid', string='Uitgenodigd door',
    )
    person_id = fields.Many2one(
        'myschool.person', string='Leerkracht', required=True,
    )

    def _notify_invited_person(self):
        for invite in self:
            user = invite.person_id.odoo_user_id
            if not user:
                continue
            act = invite.activiteit_id
            act.message_post(
                body=(
                    '<p>Beste %s,</p>'
                    '<p>U bent door <strong>%s</strong> opgegeven als begeleider voor de activiteit '
                    '<strong>%s</strong>, en de directie heeft dit goedgekeurd.</p>'
                ) % (invite.person_id.name, act.create_uid.name, act.titel),
                partner_ids=user.partner_id.ids,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

    def unlink(self):
        for invite in self:
            act = invite.activiteit_id
            if act.state in LATE_STATES and invite.person_id in act.leerkracht_ids:
                act.write({'leerkracht_ids': [(3, invite.person_id.id)]})
                invite._notify_vervangingen('verwijderd')
        return super().unlink()

    def _notify_vervangingen(self, result):
        """Notify vervangingen team when a teacher accepts/rejects after activity is past approval."""
        vervangingen_group = self.env.ref(
            'activiteiten.group_activiteiten_vervangingen', raise_if_not_found=False)
        if not vervangingen_group:
            return
        vervangingen_users = vervangingen_group.user_ids
        if not vervangingen_users:
            return
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for invite in self:
            act = invite.activiteit_id
            partner_ids = vervangingen_users.mapped('partner_id').ids
            act.message_post(
                body=(
                    '<p><strong>Vervanging update:</strong> %s heeft de uitnodiging '
                    '<strong>%s</strong> voor activiteit <strong>%s</strong>. '
                    'De vervanging moet mogelijk aangepast worden.</p>'
                ) % (invite.person_id.name, result, act.titel),
                partner_ids=partner_ids,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
            for user in vervangingen_users:
                act.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary='Vervanging aanpassen: %s' % act.titel,
                    note='%s heeft de uitnodiging %s. Controleer de vervanging.' % (
                        invite.person_id.name, result),
                    user_id=user.id,
                )
