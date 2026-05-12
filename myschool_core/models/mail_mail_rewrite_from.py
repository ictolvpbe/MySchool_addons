"""Herschrijf de From-header van uitgaande mails naar het kanonieke
SMTP-adres, met de originele afzender in Reply-To.

Reden: bepaalde SMTP-providers (zoals mail.one.com) staan enkel toe dat de
SMTP-account zelf als afzender gebruikt wordt. Plus-aliassen of andere
gebruikers van hetzelfde domein worden geweigerd met fout
``550 5.7.1 User not authorized to send on behalf of <other@example.com>``.

Deze hook leest het kanonieke adres uit de systeemparameter
``mail.default.from`` en herschrijft de ``email_from`` van elke
``mail.mail`` net voor verzending. De originele afzender komt in
``reply_to`` zodat antwoorden bij de juiste persoon belanden.

Het herschrijven gebeurt enkel wanneer:
- ``mail.default.from`` is gezet (sleutel + waarde aanwezig)
- de huidige ``email_from`` is leeg, OF zit op hetzelfde domein als de
  kanonieke from, OF heeft een plus-alias op dat domein

Mailtjes naar/van externe domeinen blijven dus onaangeroerd.
"""

from email.utils import formataddr, parseaddr

from odoo import models
from odoo.tools import email_normalize, email_split


class MailMail(models.Model):
    _inherit = 'mail.mail'

    def send(self, auto_commit=False, raise_exception=False, post_send_callback=None):
        canonical = self.env['ir.config_parameter'].sudo().get_param(
            'mail.default.from')
        if canonical and '@' in canonical:
            canonical_norm = email_normalize(canonical) or canonical
            canonical_domain = canonical_norm.split('@', 1)[1].lower()
            for mail in self:
                self._rewrite_email_from(mail, canonical_norm, canonical_domain)
        return super().send(
            auto_commit=auto_commit,
            raise_exception=raise_exception,
            post_send_callback=post_send_callback,
        )

    @staticmethod
    def _rewrite_email_from(mail, canonical_from, canonical_domain):
        """Pas mail.email_from aan naar canonical_from indien nodig.
        Behoud de display-naam van de originele afzender zodat de ontvanger
        nog ziet wie het effectief verzond, ondanks de SMTP-rewriting.

        Voorbeeld:
            origineel  : "Test Directie" <itinfo+directie@olvp.be>
            canonical  : itinfo@olvp.be
            resultaat  : "Test Directie (via OLVP)" <itinfo@olvp.be>
            reply_to   : "Test Directie" <itinfo+directie@olvp.be>
        """
        original = (mail.email_from or '').strip()
        if not original:
            mail.email_from = canonical_from
            return
        # Parse "Naam <adres>" naar (naam, adres)
        original_name, original_addr = parseaddr(original)
        if not original_addr:
            return
        addr_lower = (email_normalize(original_addr) or original_addr).lower()
        # Behoud externe afzenders (ander domein) ongewijzigd.
        if not addr_lower.endswith('@' + canonical_domain):
            return
        # Zelfde adres als de kanonieke (en geen extra naam te bewaren) → klaar.
        if addr_lower == canonical_from.lower():
            return
        # Bouw nieuwe From: behoud de naam, vervang het adres.
        if original_name:
            new_from = formataddr((f'{original_name} (via OLVP)', canonical_from))
        else:
            new_from = canonical_from
        # Originele afzender (mét naam) als Reply-To zodat antwoorden alsnog
        # bij de juiste persoon belanden.
        if not (mail.reply_to or '').strip():
            mail.reply_to = original
        mail.email_from = new_from
