"""Constants for the Thermowatt Smart (Thermann Smart Electric) integration."""

DOMAIN = "thermann"

CONF_APP_VERSION = "app_version"
DEFAULT_APP_VERSION = "3.14"

# Extracted from the MyThermowatt / Thermann Control app. Identifies requests
# as coming from "the app" - not a user secret, shared across all app users.
API_KEY = "YVjArWssxKH631jv1dnnWOTr6gijsSAGz7rQJ4hJoUNRffxYvbQaMbePBEZalena"
BASE_URL = "https://myapp-connectivity.com/api/v1"

# The app polls every 20 s, but only while it is open on screen. Home Assistant
# polls 24/7, so use a much gentler default. Configurable in the options flow.
CONF_POLL_INTERVAL = "poll_interval"
DEFAULT_POLL_INTERVAL = 60  # seconds
MIN_POLL_INTERVAL = 30
MAX_POLL_INTERVAL = 3600
# Upper bound for the backoff applied after errors / HTTP 429.
MAX_BACKOFF_INTERVAL = 900

# Keys under which tokens are persisted in the config entry, so a restart
# refreshes the session instead of sending a new password login.
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_DEVICE_UUID = "device_uuid"

# Cmd value (from the device status payload) -> HA operation mode string
CMD_TO_MODE = {
    9: "manual",
    3: "eco",
    17: "auto",
    65: "holiday",
    16: "off",
}
MODE_TO_CMD = {v: k for k, v in CMD_TO_MODE.items()}

OPERATION_MODES = ["off", "eco", "manual", "auto", "holiday"]

MIN_TEMP = 20
MAX_TEMP = 75
DEFAULT_TEMP = 60

CONF_ELEMENT_KW = "element_kw"
DEFAULT_ELEMENT_KW = 3.6  # typical AU electric HWS element size; user-configurable