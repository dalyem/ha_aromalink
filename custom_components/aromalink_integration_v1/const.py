"""Constants for the Aroma-Link integration."""

DOMAIN = "aromalink_integration_v1"
AROMA_LINK_SSL = False  # Temporary workaround for Aroma-Link's expired certificate.
AROMA_LINK_TRACE_REQUESTS = True  # Temporary request logging while debugging API behavior.

# Configuration
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_DEVICE_ID = "device_id"
CONF_DIFFUSE_TIME = "diffuse_time"
CONF_WORK_DURATION = "work_duration"
CONF_POLL_INTERVAL_SECONDS = "poll_interval_seconds"

# Default values
DEFAULT_DIFFUSE_TIME = 60  # seconds
DEFAULT_WORK_DURATION = 10  # seconds
DEFAULT_PAUSE_DURATION = 90  # seconds
DEFAULT_POLL_INTERVAL_SECONDS = 60

# Services
SERVICE_SET_SCHEDULER = "set_scheduler"
SERVICE_RUN_DIFFUSER = "run_diffuser"

# Attributes
ATTR_DURATION = "duration"
ATTR_DIFFUSE_TIME = "diffuse_time"
ATTR_WORK_DURATION = "work_duration"
ATTR_PAUSE_DURATION = "pause_duration"
ATTR_WEEK_DAYS = "week_days"
