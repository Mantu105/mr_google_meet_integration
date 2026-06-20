# -*- coding: utf-8 -*-
import json
import logging
import uuid
from datetime import datetime, timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Google OAuth2 / Calendar API endpoints
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
# Scope required to create events that carry a Google Meet conference link.
GOOGLE_SCOPE = "https://www.googleapis.com/auth/calendar"
REQUEST_TIMEOUT = 20


class GoogleMeetMixin(models.AbstractModel):
    """Shared OAuth2 + Google Calendar helpers.

    Both ``res.company`` and ``res.users`` inherit this mixin so that the same
    credential-handling and API code is reused for company-level and
    user-level Google accounts.
    """
    _name = "google.meet.mixin"
    _description = "Google Meet Credentials Mixin"

    google_meet_client_id = fields.Char(
        string="Google Client ID", copy=False)
    google_meet_client_secret = fields.Char(
        string="Google Client Secret", copy=False)
    google_meet_refresh_token = fields.Char(
        string="Google Refresh Token", copy=False, groups="base.group_system")
    google_meet_access_token = fields.Char(
        string="Google Access Token", copy=False, groups="base.group_system")
    google_meet_token_expiry = fields.Datetime(
        string="Token Expiry", copy=False, groups="base.group_system")
    google_meet_authorized = fields.Boolean(
        string="Google Authorized", compute="_compute_google_meet_authorized",
        store=False)

    @api.depends("google_meet_refresh_token")
    def _compute_google_meet_authorized(self):
        for record in self:
            record.google_meet_authorized = bool(
                record.sudo().google_meet_refresh_token)

    # ------------------------------------------------------------------
    # OAuth helpers
    # ------------------------------------------------------------------
    def _google_meet_redirect_uri(self):
        """Return the OAuth2 redirect URI registered in the Google console."""
        base_url = self.env["ir.config_parameter"].sudo().get_param(
            "web.base.url")
        return "%s/google_meet/auth/callback" % base_url.rstrip("/")

    def _get_google_meet_auth_url(self, state):
        """Build the Google consent screen URL for this credential holder."""
        self.ensure_one()
        if not self.google_meet_client_id:
            raise UserError(_("Please set the Google Client ID first."))
        params = {
            "client_id": self.google_meet_client_id,
            "redirect_uri": self._google_meet_redirect_uri(),
            "response_type": "code",
            "scope": GOOGLE_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        query = "&".join(
            "%s=%s" % (key, requests.utils.quote(str(value), safe=""))
            for key, value in params.items()
        )
        return "%s?%s" % (GOOGLE_AUTH_ENDPOINT, query)

    def _google_meet_exchange_code(self, code):
        """Exchange an authorization code for refresh/access tokens."""
        self.ensure_one()
        data = {
            "code": code,
            "client_id": self.google_meet_client_id,
            "client_secret": self.google_meet_client_secret,
            "redirect_uri": self._google_meet_redirect_uri(),
            "grant_type": "authorization_code",
        }
        try:
            response = requests.post(
                GOOGLE_TOKEN_ENDPOINT, data=data, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as error:
            _logger.exception("Google token exchange failed")
            raise UserError(
                _("Could not retrieve tokens from Google: %s") % error)
        payload = response.json()
        expiry = fields.Datetime.now() + timedelta(
            seconds=payload.get("expires_in", 3600))
        vals = {
            "google_meet_access_token": payload.get("access_token"),
            "google_meet_token_expiry": expiry,
        }
        # Google only returns the refresh token on the first consent.
        if payload.get("refresh_token"):
            vals["google_meet_refresh_token"] = payload["refresh_token"]
        self.sudo().write(vals)
        return True

    def _google_meet_get_access_token(self):
        """Return a valid access token, refreshing it when needed."""
        self.ensure_one()
        record = self.sudo()
        if not record.google_meet_refresh_token:
            raise UserError(_(
                "This account is not connected to Google yet. "
                "Please authorize it in the settings."))
        expiry = record.google_meet_token_expiry
        if record.google_meet_access_token and expiry and \
                expiry > fields.Datetime.now() + timedelta(seconds=60):
            return record.google_meet_access_token
        # Refresh the access token.
        data = {
            "client_id": record.google_meet_client_id,
            "client_secret": record.google_meet_client_secret,
            "refresh_token": record.google_meet_refresh_token,
            "grant_type": "refresh_token",
        }
        try:
            response = requests.post(
                GOOGLE_TOKEN_ENDPOINT, data=data, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as error:
            _logger.exception("Google token refresh failed")
            raise UserError(
                _("Could not refresh the Google access token: %s") % error)
        payload = response.json()
        new_expiry = fields.Datetime.now() + timedelta(
            seconds=payload.get("expires_in", 3600))
        record.write({
            "google_meet_access_token": payload.get("access_token"),
            "google_meet_token_expiry": new_expiry,
        })
        return payload.get("access_token")

    def _google_meet_revoke(self):
        """Clear stored Google credentials (local disconnect)."""
        self.sudo().write({
            "google_meet_refresh_token": False,
            "google_meet_access_token": False,
            "google_meet_token_expiry": False,
        })
        return True

    # ------------------------------------------------------------------
    # Google Calendar API calls
    # ------------------------------------------------------------------
    def _google_meet_headers(self):
        return {
            "Authorization": "Bearer %s" % self._google_meet_get_access_token(),
            "Content-Type": "application/json",
        }

    def google_meet_create_event(self, payload, send_updates="all"):
        """Insert a Calendar event with a Google Meet conference link.

        :param dict payload: event body (summary, start, end, attendees...)
        :return: the parsed Google event response
        """
        self.ensure_one()
        payload.setdefault("conferenceData", {
            "createRequest": {
                "requestId": uuid.uuid4().hex,
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        })
        url = "%s/calendars/primary/events" % GOOGLE_CALENDAR_API
        params = {"conferenceDataVersion": 1, "sendUpdates": send_updates}
        try:
            response = requests.post(
                url, headers=self._google_meet_headers(),
                params=params, data=json.dumps(payload),
                timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as error:
            _logger.exception("Google Meet creation failed")
            detail = getattr(error.response, "text", "") if \
                getattr(error, "response", None) is not None else ""
            raise UserError(_(
                "Failed to create the Google Meet meeting.\n%s") % (
                    detail or error))
        return response.json()

    def google_meet_delete_event(self, google_event_id, send_updates="all"):
        """Delete a previously created Calendar/Meet event on Google's side."""
        self.ensure_one()
        url = "%s/calendars/primary/events/%s" % (
            GOOGLE_CALENDAR_API, google_event_id)
        params = {"sendUpdates": send_updates}
        try:
            response = requests.delete(
                url, headers=self._google_meet_headers(),
                params=params, timeout=REQUEST_TIMEOUT)
            # 410 == already gone, treat as success.
            if response.status_code not in (200, 204, 404, 410):
                response.raise_for_status()
        except requests.RequestException as error:
            _logger.exception("Google Meet deletion failed")
            raise UserError(_(
                "Failed to delete the Google Meet meeting: %s") % error)
        return True
