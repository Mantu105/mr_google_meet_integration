# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _name = "res.company"
    _inherit = ["res.company", "google.meet.mixin"]

    google_meet_allowed_user_ids = fields.Many2many(
        "res.users",
        "res_company_google_meet_user_rel",
        "company_id",
        "user_id",
        string="Allowed Users (to use company credentials)",
        help="Users who may create Google Meet meetings using this company's "
             "credentials. Leave empty to allow all users.",
    )

    def action_google_meet_authorize(self):
        """Redirect to Google consent screen for company-level authorization."""
        self.ensure_one()
        if not self.google_meet_client_id or not self.google_meet_client_secret:
            raise UserError(_(
                "Please set both the Google Client ID and Client Secret "
                "before authorizing."))
        state = "company-%s" % self.id
        auth_url = self._get_google_meet_auth_url(state)
        return {
            "type": "ir.actions.act_url",
            "url": auth_url,
            "target": "self",
        }

    def action_google_meet_revoke(self):
        """Revoke the company Google Meet authorization."""
        self.ensure_one()
        self._google_meet_revoke()
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
