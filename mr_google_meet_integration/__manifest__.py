# -*- coding: utf-8 -*-
{
    'name': 'Google Meet Integration',
    'version': '18.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Create Google Meet video meetings directly from Odoo Calendar events',
    'description': """
Google Meet Integration for Odoo 18
=====================================
Create, join, and manage Google Meet video meetings directly from Odoo Calendar events.

Key Features
------------
* One-click Google Meet creation from any calendar event.
* Company-level and User-level Google OAuth2 credentials.
* Personal credentials take priority over company credentials.
* Restrict company credential usage to specific allowed users.
* Wizard with meeting title, reminder, and email notification settings.
* Google-style invitation posted in the chatter with Join button.
* Google Calendar API sends native invitation emails to attendees.
* Join or Delete the meeting directly from the calendar event form.
* Chatter log updated on creation and deletion.
* Compatible with Odoo's native videocall_location field.
    """,
    'author': 'Mantu Raj',
    'website': 'https://www.linkedin.com/in/mantu105/',
    'support': 'workmantu105@gmail.com',
    'license': 'OPL-1',
    'price': 5.0,
    'currency': 'USD',
    'depends': [
        'mail',
        'calendar',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/ir.model.access.csv',
        'wizard/google_meet_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_company_views.xml',
        'views/res_users_views.xml',
        'views/calendar_event_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
