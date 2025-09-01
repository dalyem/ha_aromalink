"""Constants for the Aroma-Link integration."""

DOMAIN = "aroma_link_new"

# Configuration
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_DEVICE_ID = "device_id"
CONF_DIFFUSE_TIME = "diffuse_time"
CONF_WORK_DURATION = "work_duration"

# Default values
DEFAULT_DIFFUSE_TIME = 60  # seconds
DEFAULT_WORK_DURATION = 10  # seconds
DEFAULT_PAUSE_DURATION = 900  # seconds (15 minutes)

# Services
SERVICE_SET_SCHEDULER = "set_scheduler"
SERVICE_RUN_DIFFUSER = "run_diffuser"

# Attributes
ATTR_DURATION = "duration"
ATTR_DIFFUSE_TIME = "diffuse_time"
ATTR_WORK_DURATION = "work_duration"
ATTR_PAUSE_DURATION = "pause_duration"
ATTR_WEEK_DAYS = "week_days"
