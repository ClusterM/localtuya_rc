"""Constants for the LocalTuyaIR Remote Control integration."""

DOMAIN = "localtuya_rc"
DEFAULT_FRIENDLY_NAME = "Tuya IR Remote Control"
NOTIFICATION_TITLE = "Tuya IR Remote Control"

CONF_LOCAL_KEY = "local_key"
CONF_PROTOCOL_VERSION = "protocol_version"
CONF_CLOUD_INFO = "cloud_info"

CONF_SERIAL_NUMBER = "serial_number"
CONF_PRODUCT_CATEGORY = "product_category"
CONF_PRODUCT_NAME = "product_name"
CONF_PRODUCT_ID = "product_id"
CONF_PERSISTENT_CONNECTION = "persistent_connection"

DEFAULT_PERSISTENT_CONNECTION = False

CODE_STORAGE_VERSION = 1
CODE_STORAGE_CODES = f"{DOMAIN}_codes"

# Tuya protocol versions in order of preference
TUYA_VERSIONS = [3.3, 3.4, 3.5, 3.2, 3.1]