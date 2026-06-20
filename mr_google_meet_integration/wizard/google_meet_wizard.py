# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class GoogleMeetWizard(models.TransientModel):
    _name = "google.meet.wizard"
    _description = "Google Meet Meeting Settings"

    event_id = fields.Many2one(
        "calendar.event", string="Calendar Event",
        required=True, ondelete="cascade")
    summary = fields.Char(string="Meeting Title", required=True)

    # Meeting details (read-only, taken from the event).
    start_time = fields.Datetime(
        related="event_id.start", string="Start Time", readonly=True)
    end_time = fields.Datetime(
        related="event_id.stop", string="End Time", readonly=True)

    # Settings.
    send_email = fields.Boolean(
        string="Send Email Notifications to Attendees", default=True,
        help="Let Google email a calendar invitation to the attendees.")
    reminder = fields.Selection(
        selection=[
            ("none", "No reminder"),
            ("5", "5 minutes before"),
            ("10", "10 minutes before"),
            ("15", "15 minutes before"),
            ("30", "30 minutes before"),
            ("60", "1 hour before"),
            ("1440", "1 day before"),
        ],
        string="Reminder", default="10", required=True)

    # Credentials.
    credential_source = fields.Selection(
        selection=[
            ("personal", "My Personal Account"),
            ("company", "Company Account"),
        ],
        string="Use Credentials", required=True,
        default=lambda self: self._default_credential_source())
    credential_info = fields.Char(
        string="Meeting will be created from",
        compute="_compute_credential_info")

    def _default_credential_source(self):
        user = self.env.user
        if user.sudo().google_meet_refresh_token:
            return "personal"
        return "company"

    @api.depends("credential_source", "event_id")
    def _compute_credential_info(self):
        for wiz in self:
            if wiz.credential_source == "personal":
                wiz.credential_info = _("Personal: %s") % wiz.env.user.name
            elif wiz.credential_source == "company":
                company = wiz.env.company
                if wiz.event_id:
                    company = wiz.event_id._get_google_meet_company()
                wiz.credential_info = _("Company: %s") % (
                    company.name if company else wiz.env.company.name)
            else:
                wiz.credential_info = ""

    def action_create_meet(self):
        self.ensure_one()
        self.event_id._create_google_meet(
            summary=self.summary,
            reminder_minutes=None if self.reminder == "none" else self.reminder,
            send_email=self.send_email,
            source=self.credential_source,
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Google Meet Created"),
                "message": _(
                    "Google Meet has been created successfully. "
                    "The join link is available on the event."),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
