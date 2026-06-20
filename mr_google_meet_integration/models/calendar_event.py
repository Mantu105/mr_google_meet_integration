# -*- coding: utf-8 -*-
import logging

from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_datetime

_logger = logging.getLogger(__name__)


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    google_meet_url = fields.Char(
        string="Google Meet URL", copy=False, readonly=True)
    google_meet_event_id = fields.Char(
        string="Google Event ID", copy=False, readonly=True)
    google_meet_code = fields.Char(
        string="Google Meet Code", copy=False, readonly=True)
    google_meet_credential_source = fields.Char(
        string="Google Meet Credential Source", copy=False, readonly=True)
    google_meet_has_meeting = fields.Boolean(
        string="Has Google Meet", compute="_compute_google_meet_has_meeting",
        store=True)

    @api.depends("google_meet_url")
    def _compute_google_meet_has_meeting(self):
        for event in self:
            event.google_meet_has_meeting = bool(event.google_meet_url)

    # ------------------------------------------------------------------
    # Credential resolution
    # ------------------------------------------------------------------
    def _get_google_meet_company(self):
        """Return the first allowed company that has Google credentials.

        Falls back to the active company even without credentials so callers
        can decide what to do.
        """
        self.ensure_one()
        user = self.env.user
        seen = set()
        for company in (self.env.company | user.company_id |
                        user.company_ids):
            if company.id in seen:
                continue
            seen.add(company.id)
            if company.sudo().google_meet_refresh_token:
                return company
        return self.env.company

    def _get_google_meet_credentials(self, source=None):
        """Return the credential holder (user or company) to use.

        :param source: 'personal', 'company' or None (auto: personal first).
        """
        self.ensure_one()
        user = self.env.user
        user_has = bool(user.sudo().google_meet_refresh_token)
        company = self._get_google_meet_company()
        company_has = bool(company) and bool(
            company.sudo().google_meet_refresh_token)

        def _user_allowed_for_company():
            allowed = company.sudo().google_meet_allowed_user_ids
            return not allowed or user in allowed

        if source == "personal":
            if user_has:
                return user
            raise UserError(_(
                "Your personal Google account is not connected.\n"
                "Connect it in your user preferences (Google Meet tab)."))
        if source == "company":
            if company_has:
                if not _user_allowed_for_company():
                    raise UserError(_(
                        "You are not authorised to use the company Google "
                        "account. Ask an administrator to add you to the "
                        "allowed users list on the company form."))
                return company
            raise UserError(_(
                "The company Google account is not connected.\n"
                "Ask an administrator to connect it in Settings."))

        # Auto: personal takes priority, then company.
        if user_has:
            return user
        if company_has and _user_allowed_for_company():
            return company
        raise UserError(_(
            "No Google account is connected.\n\n"
            "Connect your personal account in your user preferences, or ask "
            "an administrator to connect the company account in Settings."))

    # ------------------------------------------------------------------
    # Payload
    # ------------------------------------------------------------------
    def _prepare_google_meet_payload(self, summary=None, description=None,
                                     extra_attendees=None,
                                     reminder_minutes=None):
        """Build the Google Calendar event body for this Odoo event."""
        self.ensure_one()
        tz = self.env.user.tz or "UTC"
        organizer_email = (self.user_id or self.env.user).email or ""
        attendees = []
        for partner in self.partner_ids:
            if partner.email and partner.email.lower() != organizer_email.lower():
                attendees.append({"email": partner.email})
        for email in (extra_attendees or []):
            if email and email.lower() != organizer_email.lower():
                attendees.append({"email": email})

        if self.allday:
            # Google treats the all-day end date as exclusive.
            end_date = self.stop_date + timedelta(days=1)
            body = {
                "summary": summary or self.name,
                "description": description or (self.description or ""),
                "start": {"date": fields.Date.to_string(self.start_date)},
                "end": {"date": fields.Date.to_string(end_date)},
            }
        else:
            body = {
                "summary": summary or self.name,
                "description": description or (self.description or ""),
                "start": {
                    "dateTime": self.start.isoformat() + "Z",
                    "timeZone": tz,
                },
                "end": {
                    "dateTime": self.stop.isoformat() + "Z",
                    "timeZone": tz,
                },
            }
        if attendees:
            body["attendees"] = attendees
        if self.location:
            body["location"] = self.location

        # Reminders.
        if reminder_minutes not in (None, False, "none", ""):
            minutes = int(reminder_minutes)
            body["reminders"] = {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": minutes},
                    {"method": "email", "minutes": minutes},
                ],
            }
        else:
            body["reminders"] = {"useDefault": True}
        return body

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_open_google_meet_wizard(self):
        """Open the meeting-settings wizard."""
        self.ensure_one()
        if self.google_meet_url:
            raise UserError(_(
                "This event already has a Google Meet meeting. Delete it "
                "first if you want to create a new one."))
        # Validate at least one credential exists before opening the wizard.
        self._get_google_meet_credentials()
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Google Meet"),
            "res_model": "google.meet.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_event_id": self.id,
                "default_summary": self.name,
            },
        }

    def _create_google_meet(self, summary=None, description=None,
                            extra_attendees=None, reminder_minutes=None,
                            send_email=True, source=None):
        """Create the meeting on Google and store the result on the event."""
        self.ensure_one()
        credentials = self._get_google_meet_credentials(source=source)
        send_updates = "all" if send_email else "none"
        payload = self._prepare_google_meet_payload(
            summary=summary, description=description,
            extra_attendees=extra_attendees, reminder_minutes=reminder_minutes)
        result = credentials.google_meet_create_event(
            payload, send_updates=send_updates)

        meet_url = result.get("hangoutLink")
        if not meet_url:
            for entry in result.get("conferenceData", {}).get(
                    "entryPoints", []):
                if entry.get("entryPointType") == "video":
                    meet_url = entry.get("uri")
                    break
        meet_code = ""
        if meet_url:
            meet_code = meet_url.rstrip("/").split("/")[-1]

        used_source = "personal" if credentials._name == "res.users" \
            else "company"
        vals = {
            "google_meet_url": meet_url,
            "google_meet_event_id": result.get("id"),
            "google_meet_code": meet_code,
            "google_meet_credential_source": used_source,
        }
        # Mirror the link into Odoo's native videocall field so the standard
        # "Join video call" link works too.
        if meet_url and "videocall_location" in self._fields:
            vals["videocall_location"] = meet_url
        self.write(vals)

        self._post_google_meet_invitation()
        return meet_url

    def action_join_google_meet(self):
        """Open the Google Meet link in a new browser tab."""
        self.ensure_one()
        if not self.google_meet_url:
            raise UserError(_("There is no Google Meet link for this event."))
        return {
            "type": "ir.actions.act_url",
            "url": self.google_meet_url,
            "target": "new",
        }

    def action_delete_google_meet(self):
        """Remove the Google Meet meeting and clear the stored values."""
        self.ensure_one()
        if not self.google_meet_event_id:
            raise UserError(_("There is no Google Meet meeting to delete."))
        credentials = self._get_google_meet_credentials(
            source=self.google_meet_credential_source or None)
        credentials.google_meet_delete_event(self.google_meet_event_id)
        self._post_google_meet_deletion()

        vals = {
            "google_meet_url": False,
            "google_meet_event_id": False,
            "google_meet_code": False,
            "google_meet_credential_source": False,
        }
        if "videocall_location" in self._fields and \
                self.videocall_location == self.google_meet_url:
            vals["videocall_location"] = False
        self.write(vals)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Google Meet deleted"),
                "message": _("The Google Meet meeting has been deleted."),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window",
                    "res_model": "calendar.event",
                    "res_id": self.id,
                    "view_mode": "form",
                    "views": [(False, "form")],
                    "target": "current",
                },
            },
        }

    # ------------------------------------------------------------------
    # Chatter
    # ------------------------------------------------------------------
    def _google_meet_time_display(self):
        self.ensure_one()
        tz = self.env.user.tz or "UTC"
        return format_datetime(
            self.env, self.start, tz=tz, dt_format="medium")

    def _post_google_meet_invitation(self):
        """Post a Google Calendar-style invitation in the chatter and email attendees."""
        self.ensure_one()
        organizer_user = self.user_id or self.env.user
        organizer_email = (organizer_user.email or "").lower()

        # Build guests list HTML
        guest_parts = []
        for partner in self.partner_ids:
            is_org = (partner.email or "").lower() == organizer_email
            name_html = Markup(
                "<span style='color:#202124;font-size:14px;font-weight:500;'>%s</span>"
            ) % (partner.name or "")
            if is_org:
                name_html += Markup(
                    " <span style='color:#5f6368;font-size:13px;'>- organizer</span>"
                )
            if partner.email:
                name_html += Markup(
                    "<br/><span style='color:#5f6368;font-size:13px;'>%s</span>"
                ) % partner.email
            guest_parts.append(name_html)
        guests_html = Markup("<br/><br/>").join(guest_parts)

        body = Markup(
            "<div style='font-family:Arial,sans-serif;max-width:600px;"
            "background:#fff;border:1px solid #e0e0e0;border-radius:8px;'>"
            "<div style='padding:24px;'>"
            "<table width='100%%' style='border-collapse:collapse;'><tr>"
            "<td style='vertical-align:top;padding-right:16px;'>"
            "<h2 style='font-size:22px;color:#202124;margin:0 0 6px;'>%(topic)s</h2>"
            "<p style='color:#5f6368;font-size:14px;margin:0;'>%(time)s</p>"
            "</td>"
            "<td style='vertical-align:top;text-align:right;white-space:nowrap;'>"
            "<a href='%(url)s' target='_blank'"
            " style='display:inline-block;background-color:#1a73e8;color:#ffffff;"
            "padding:10px 20px;border-radius:4px;text-decoration:none;"
            "font-size:14px;font-weight:500;'>Join with Google Meet</a>"
            "</td></tr></table>"
            "<div style='margin-top:20px;border-top:1px solid #e0e0e0;padding-top:16px;'>"
            "<p style='color:#5f6368;font-size:12px;font-weight:500;margin:0 0 4px;'>"
            "Meeting link</p>"
            "<a href='%(url)s' target='_blank'"
            " style='color:#1a73e8;font-size:14px;text-decoration:none;'>"
            "%(url)s</a>"
            "</div>"
            "<div style='margin-top:16px;'>"
            "<p style='color:#5f6368;font-size:12px;font-weight:500;margin:0 0 10px;'>"
            "Guests</p>"
            "%(guests)s"
            "</div>"
            "</div>"
            "</div>"
        ) % {
            "topic": self.name or "",
            "time": self._google_meet_time_display(),
            "url": self.google_meet_url or "",
            "guests": guests_html,
        }

        self.message_post(body=body, subtype_xmlid="mail.mt_note")

    def _post_google_meet_deletion(self):
        self.ensure_one()
        self.message_post(
            body=Markup(_("<p>Google Meet deleted successfully.</p>")),
            subtype_xmlid="mail.mt_note")
