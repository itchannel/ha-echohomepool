"""Constants for the Eco-Home integration."""

DOMAIN = "eco_home"
MANUFACTURER = "Eco-Home"
MODEL = "Pool Heat Pump"
PLATFORMS = ["climate", "sensor", "switch", "binary_sensor"]

CLOUD_BASE = "https://ehome.ne01.com"
CLOUD_API = f"{CLOUD_BASE}/cloudservice/api"
CRM_API = f"{CLOUD_BASE}/crmservice/api"

# Default polling interval in seconds
DEFAULT_SCAN_INTERVAL = 30

# Config entry keys
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_DEVICE_CODE = "device_code"
CONF_SCAN_INTERVAL = "scan_interval"

# Device modes from the app (制冷 = cooling, 制热 = heating)
MODE_COOLING = "cool"
MODE_HEATING = "heat"
MODE_AUTO = "auto"

# Map modeValue integers from API to HA HVAC modes
# The pool heat pump control pages show modeValue "1" for both cooling and heating
# in placeholder data; real values come from the device's modeList at runtime.
# We map by modeMeaning keywords.
MODE_MEANING_COOL_KEYWORDS = ("冷", "cool", "refriger", "制冷")
MODE_MEANING_HEAT_KEYWORDS = ("热", "heat", "制热")
MODE_MEANING_AUTO_KEYWORDS = ("auto", "自动", "smart", "intelligen")
MODE_MEANING_DRY_KEYWORDS = ("dry", "dehumid", "除湿", "干燥")
MODE_MEANING_FAN_KEYWORDS = ("fan only", "fan_only", "送风", "风扇")
