# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResUsers(models.Model):
    _name = "res.users"
    _inherit = ["res.users", "google.meet.mixin"]

    google_meet_credential_type = fields.Char(
        string="Currently Using",
        compute="_compute_google_meet_credential_type",
    )

    @api.depends("google_meet_refresh_token", "company_id.google_meet_refresh_token")
    def _compute_google_meet_credential_type(self):
        for user in self:
            if user.sudo().google_meet_refresh_token:
                user.google_meet_credential_type = _("Personal Credentials")
            elif user.company_id.sudo().google_meet_refresh_token:
                user.google_meet_credential_type = _("Company Credentials")
            else:
                user.google_meet_credential_type = _("Not Configured")

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            "google_meet_client_id",
            "google_meet_client_secret",
            "google_meet_authorized",
            "google_meet_credential_type",
        ]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + [
            "google_meet_client_id",
            "google_meet_client_secret",
        ]

    def action_user_google_meet_authorize(self):
        """Redirect the current user to Google's consent screen."""
        self.ensure_one()
        if not self.google_meet_client_id or not self.google_meet_client_secret:
            raise UserError(_(
                "Please set both your Google Client ID and Client Secret "
                "before authorizing."))
        state = "user-%s" % self.id
        auth_url = self._get_google_meet_auth_url(state)
        return {
            "type": "ir.actions.act_url",
            "url": auth_url,
            "target": "self",
        }

    def action_user_google_meet_disconnect(self):
        self.ensure_one()
        self._google_meet_revoke()
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
