# -*- coding: utf-8 -*-
from odoo import models


class CalendarAttendee(models.Model):
    _inherit = "calendar.attendee"

    def _send_mail_to_attendees(self, mail_template, force_send=False):
        """Suppress Odoo's built-in calendar invitation email entirely.
        Google Calendar API handles attendee notifications via sendUpdates=all."""
        return False
