SECRET_KEY = "random-secret-key"

MYSQL_HOST = "localhost"
MYSQL_USER = "root"
MYSQL_PASSWORD = "4425148$uyoG"
MYSQL_DB = "class_db"

# Backwards-compatible alias: some modules use MYSQL_DATABASE
MYSQL_DATABASE = MYSQL_DB

# Email Configuration for OTP verification
EMAIL_SENDER = "suyogtuladhar04@gmail.com"
EMAIL_SMTP_SERVER = "smtp.gmail.com"
EMAIL_SMTP_PORT = 587
EMAIL_SERVICE_API_KEY = "tecr fpns leas rzzr"

# API-Football key for live World Cup 2026 scores on the home page.
# Get a free key at https://www.api-football.com/ (or dashboard.api-football.com).
# Leave blank to fall back to clearly-labelled sample fixtures. Prefer setting
# the API_FOOTBALL_KEY environment variable over hard-coding it here.
import os
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "")

