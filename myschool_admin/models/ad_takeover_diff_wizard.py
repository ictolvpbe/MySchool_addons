# -*- coding: utf-8 -*-
"""AD-Takeover Diff Wizard — slide-over preview voor één finding.

Toont een 3-koloms diff (BRON / DB / ACTIE) voordat de admin het
voorstel approveert, piloott of negeert. Het wizardmodel is
``TransientModel`` zodat records vanzelf worden opgekuist.
"""
import json
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AdTakeoverDiffWizard(models.TransientModel):
    _name = 'myschool.ad.takeover.diff.wizard'
    _description = 'AD-Takeover Diff Preview'

    finding_id = fields.Many2one(
        'myschool.ad.takeover.finding', required=True, ondelete='cascade')

    # Geprefetched velden zodat de form-view ze direct kan tonen
    # zonder een aparte related-roundtrip per cell.
    source         = fields.Selection(related='finding_id.source', readonly=True)
    kind           = fields.Selection(related='finding_id.kind', readonly=True)
    ad_dn          = fields.Char(related='finding_id.ad_dn', readonly=True,
                                 string='Bron-DN / pad')
    ad_cn          = fields.Char(related='finding_id.ad_cn', readonly=True,
                                 string='Naam in bron')
    ad_mail        = fields.Char(related='finding_id.ad_mail', readonly=True)
    sap_ref        = fields.Char(related='finding_id.sap_ref', readonly=True)
    state          = fields.Selection(related='finding_id.state', readonly=True)
    proposal_kind  = fields.Selection(related='finding_id.proposal_kind',
                                      readonly=True)
    risk_level     = fields.Selection(related='finding_id.risk_level',
                                      readonly=True)
    matched_person_id = fields.Many2one(
        related='finding_id.matched_person_id', readonly=True)
    sibling_ids    = fields.Many2many(
        related='finding_id.sibling_ids', readonly=True)

    # Berekende rich-text kolommen — een per axis van de diff.
    bron_text    = fields.Text(compute='_compute_diff_texts', readonly=True,
                               string='BRON (huidige staat)')
    db_text      = fields.Text(compute='_compute_diff_texts', readonly=True,
                               string='DB (myschool)')
    actie_text   = fields.Text(compute='_compute_diff_texts', readonly=True,
                               string='ACTIE (wat wordt gewijzigd)')
    risk_note    = fields.Text(compute='_compute_diff_texts', readonly=True,
                               string='Veiligheidsnotities')
    snapshot_preview = fields.Text(compute='_compute_snapshot_preview',
                                   readonly=True,
                                   string='Snapshot (voor rollback)')

    @api.depends('finding_id', 'finding_id.proposal_kind',
                 'finding_id.proposal_payload_json',
                 'finding_id.matched_person_id', 'finding_id.ad_dn',
                 'finding_id.ad_cn', 'finding_id.ad_mail',
                 'finding_id.sap_ref', 'finding_id.source')
    def _compute_diff_texts(self):
        for wiz in self:
            f = wiz.finding_id
            if not f:
                wiz.bron_text = wiz.db_text = wiz.actie_text = ''
                wiz.risk_note = ''
                continue
            try:
                payload = json.loads(f.proposal_payload_json or '{}')
            except (ValueError, TypeError):
                payload = {}

            bron = [
                f'Bron:        {f.source.upper()}',
                f'Kind:        {f.kind}',
                f'DN / pad:    {f.ad_dn or "—"}',
                f'CN / naam:   {f.ad_cn or "—"}',
                f'Mail:        {f.ad_mail or "—"}',
                f'sap_ref:     {f.sap_ref or "(niet gezet)"}',
            ]
            person = f.matched_person_id
            db = [
                f'Gematcht:    {person.display_name if person else "(geen)"}',
                f'sap_ref DB:  {person.sap_ref if person else "—"}',
                f'email_cloud: {person.email_cloud if person else "—"}',
                f'person_fqdn: {person.person_fqdn_internal if person else "—"}',
            ]
            actie, risk = wiz._describe_action(f, payload, person)

            wiz.bron_text = '\n'.join(bron)
            wiz.db_text = '\n'.join(db)
            wiz.actie_text = actie
            wiz.risk_note = risk

    @staticmethod
    def _describe_action(f, payload, person):
        """Per proposal_kind: tekst voor 'ACTIE' + bijbehorende risico-
        notitie. Pure presentatie, geen state-change."""
        pk = f.proposal_kind
        if not pk:
            return (_('Geen voorstel gedaan; admin moet nog kiezen.'),
                    _('Niets staat op het spel zolang er geen voorstel is.'))

        if pk == 'link_only':
            return (
                _('LINK_ONLY — DB-record aanmaken voor "%s"; bron blijft '
                  'volledig ongewijzigd.') % f.ad_cn,
                _('Geen risico aan kant van AD/Cloud. Wel: '
                  'controleer of dit echt een nieuwe persoon/org is en '
                  'geen duplicate van bestaande DB-data.'))

        if pk == 'stamp_id':
            attr = ('employeeID' if f.source == 'ad' else 'externalIds')
            value = payload.get('value', '?')
            return (
                _('STAMP_ID — schrijf %(attr)s=%(value)s naar de bron. '
                  'Geen wijziging in DN, sAMAccountName, primaryEmail, '
                  'naam of wachtwoord.') % {'attr': attr, 'value': value},
                _('De allerveiligste mutatie: alleen het identity-attribuut '
                  'wordt gevuld. Login-flows en groep-memberships '
                  'ongewijzigd.'))

        if pk == 'rename':
            new_name = payload.get('new_name', '?')
            return (
                _('RENAME — hernoem in %(src)s naar "%(new)s". '
                  '%(method)s')
                % {
                    'src': f.source.upper(),
                    'new': new_name,
                    'method': (
                        'LDAP MODIFY DN bewaart SID, GUID, group-'
                        'memberships en GPO-links.' if f.source == 'ad'
                        else 'Google patch bewaart group-email/orgUnit-pad '
                        'en members.')
                },
                _('Cloud-users kunnen NIET hernoemd worden — primaryEmail '
                  'is identity. Voor groups blijft email gelijk, alleen '
                  'displayName wijzigt.'))

        if pk == 'move':
            new_parent = payload.get('new_parent', '?')
            return (
                _('MOVE — verplaats naar "%(parent)s" in %(src)s. RDN '
                  'blijft gelijk.') % {'parent': new_parent,
                                       'src': f.source.upper()},
                _('AD: LDAP MODIFY DN met new_superior bewaart alle '
                  'identity en memberships. Cloud: voor OUs verandert '
                  'het pad — kinderen verhuizen mee.'))

        if pk == 'membership_add':
            tg = payload.get('target_group_dn') or payload.get(
                'target_group_email') or '?'
            return (
                _('MEMBERSHIP_ADD — voeg deze user toe aan groep "%s".') % tg,
                _('Geen wijziging op de user zelf. Wel: vereist dat de '
                  'doelgroep bestaat en deze user nog geen lid is.'))

        if pk == 'delete_after':
            return (
                _('DELETE_AFTER — verwijder uit %s in de cleanup-fase.')
                % f.source.upper(),
                _('Onomkeerbaar! Geen rollback mogelijk. Alleen uitvoeren '
                  'nadat alle takeovers afgerond en gecontroleerd zijn.'))

        if pk == 'ignore':
            return (_('IGNORE — sluit deze rij zonder iets te doen.'),
                    _('Volledig veilig.'))

        return (f'Onbekend voorstel-type: {pk}', '')

    @api.depends('finding_id.rollback_snapshot_json',
                 'finding_id.rollback_snapshot_at')
    def _compute_snapshot_preview(self):
        for wiz in self:
            raw = wiz.finding_id.rollback_snapshot_json or ''
            if not raw:
                wiz.snapshot_preview = ''
                continue
            try:
                data = json.loads(raw)
                pretty = json.dumps(data, indent=2, ensure_ascii=False)
            except Exception:
                pretty = raw
            ts = wiz.finding_id.rollback_snapshot_at
            wiz.snapshot_preview = (
                f'Snapshot gemaakt op {ts}\n\n{pretty}')

    # ------------------------------------------------------------------
    # Pass-through actions naar de onderliggende finding.
    # ------------------------------------------------------------------

    def action_approve(self):
        self.finding_id.action_approve()
        return {'type': 'ir.actions.act_window_close'}

    def action_pilot(self):
        self.finding_id.action_pilot()
        return {'type': 'ir.actions.act_window_close'}

    def action_verify(self):
        self.finding_id.action_verify()
        return {'type': 'ir.actions.act_window_close'}

    def action_rollback(self):
        self.finding_id.action_rollback()
        return {'type': 'ir.actions.act_window_close'}

    def action_takeover(self):
        self.finding_id.action_takeover()
        return {'type': 'ir.actions.act_window_close'}

    def action_ignore(self):
        self.finding_id.action_mark_ignore()
        return {'type': 'ir.actions.act_window_close'}

    def action_resolve_conflict(self):
        self.finding_id.action_resolve_conflict()
        return {'type': 'ir.actions.act_window_close'}
