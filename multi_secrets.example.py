# multi_secrets.py - optional initial list of known WiFi networks.
# Copy to the badge drive as multi_secrets.py, open the WiFi Config app once:
# the networks are imported into the badge's internal storage, then this file
# can be deleted (see docs/wifi-config.md). Never commit the real file.
NETWORKS = [
    {"ssid": "HomeNetwork", "password": "home-password"},
    {"ssid": "PhoneHotspot", "password": "hotspot-password"},
    {"ssid": "OpenCafe", "password": ""},
]
