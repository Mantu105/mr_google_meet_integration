# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    google_meet_client_id = fields.Char(
        related="company_id.google_meet_client_id", readonly=False)
    google_meet_client_secret = fields.Char(
        related="company_id.google_meet_client_secret", readonly=False)
    google_meet_authorized = fields.Boolean(
        related="company_id.google_meet_authorized", readonly=True)

    def action_google_meet_authorize(self):
        """Save settings then redirect the admin to Google's consent screen."""
        self.ensure_one()
        # Persist the entered credentials before starting the OAuth dance.
        self.execute()
        company = self.company_id
        if not company.google_meet_client_id or \
                not company.google_meet_client_secret:
            raise UserError(_(
                "Please set both the Google Client ID and Client Secret "
                "before authorizing."))
        state = "company-%s" % company.id
        auth_url = company._get_google_meet_auth_url(state)
        return {
            "type": "ir.actions.act_url",
            "url": auth_url,
            "target": "self",
        }

    def action_google_meet_disconnect(self):
        self.ensure_one()
        self.company_id._google_meet_revoke()
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
