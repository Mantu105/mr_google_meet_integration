# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class GoogleMeetController(http.Controller):

    @http.route("/google_meet/auth/callback", type="http", auth="user",
                website=False, csrf=False)
    def google_meet_callback(self, **kwargs):
        """Handle the redirect from Google after user consent.

        The ``state`` parameter tells us whether the credentials belong to a
        company (``company-<id>``) or a user (``user-<id>``).
        """
        code = kwargs.get("code")
        state = kwargs.get("state", "")
        error = kwargs.get("error")

        if error:
            return self._render_message(
                "Authorization failed",
                "Google returned an error: %s" % error)

        if not code or "-" not in state:
            return self._render_message(
                "Authorization failed",
                "Missing authorization code or invalid state.")

        kind, _sep, rec_id = state.partition("-")
        try:
            rec_id = int(rec_id)
        except (TypeError, ValueError):
            return self._render_message(
                "Authorization failed", "Invalid state value.")

        if kind == "company":
            record = request.env["res.company"].sudo().browse(rec_id)
            redirect_url = "/odoo/settings"
        elif kind == "user":
            record = request.env["res.users"].sudo().browse(rec_id)
            redirect_url = "/odoo/preferences"
        else:
            return self._render_message(
                "Authorization failed", "Unknown credential type.")

        if not record.exists():
            return self._render_message(
                "Authorization failed", "The target record no longer exists.")

        try:
            record._google_meet_exchange_code(code)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Google Meet token exchange failed")
            return self._render_message(
                "Authorization failed", str(exc))

        return self._render_message(
            "Google account connected",
            "You can close this tab and return to Odoo.",
            redirect_url=redirect_url, success=True)

    def _render_message(self, title, message, redirect_url=None,
                        success=False):
        color = "#28a745" if success else "#dc3545"
        redirect_html = ""
        if redirect_url:
            redirect_html = (
                "<p><a href=\"%s\" style=\"color:#714B67;\">"
                "Back to Odoo</a></p>"
                "<script>setTimeout(function(){window.location.href='%s';},"
                "2500);</script>" % (redirect_url, redirect_url)
            )
        html = """
            <html><head><meta charset="utf-8"/>
            <title>%(title)s</title></head>
            <body style="font-family:sans-serif;text-align:center;
            margin-top:80px;color:#333;">
            <h2 style="color:%(color)s;">%(title)s</h2>
            <p>%(message)s</p>
            %(redirect)s
            </body></html>
        """ % {
            "title": title,
            "message": message,
            "color": color,
            "redirect": redirect_html,
        }
        return request.make_response(html, headers=[
            ("Content-Type", "text/html")])
