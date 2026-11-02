# secrets.py - copy this file to secrets.py and fill in your values.
# secrets.py is ignored by git: never commit your real WiFi password.
# On the badge it lives in /system/secrets.py (drive visible in Disk Mode);
# apps/wifi_config keeps WIFI_SSID/WIFI_PASSWORD up to date for you.

WIFI_SSID = "MyHomeNetwork"
WIFI_PASSWORD = "my-wifi-password"
REGION = "eu"  # Options are us, cuba, eu, moldova, lebanon, egypt, chile, australia, nz
TIMEZONE = 1  # Offset from GMT as number of hours, i.e. 0, 1, -7 etc.

# Optional: label shown bottom-right on the Claude Monitor dashboard,
# e.g. the email of your Claude account. "" = nothing shown.
CLAUDE_ACCOUNT_LABEL = ""
