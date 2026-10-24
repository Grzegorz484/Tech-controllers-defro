"""Constants for the DEFRO snapshot-specific, read-only integration."""

DOMAIN = "defro_emodul"
NAME = "DEFRO eModuł — odczyt"
VERSION = "1.0.0"
CONF_SITE = "site"
CONF_USER_ID = "user_id"
CONF_MODULE_UDID = "module_udid"
CONF_MENU_CODES = "menu_codes"
MENU_TYPES = ("MU", "MI", "MS")
CODE_FIELDS = {"MU": "user_code", "MI": "installer_code", "MS": "service_code"}
SITES = ("emodul.pl", "emodul.eu")
POLL_SECONDS = 60
MENU_POLL_SECONDS = 300
TRANSLATION_POLL_SECONDS = 43200

