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

# football-data.org token for live World Cup scores on the /live page.
# Get a free token at https://www.football-data.org/client/register — the free
# tier includes the FIFA World Cup (competition code "WC").
#
# The browser never sees this token: the Flask /api/live route calls
# football-data.org server-side and the page polls our own endpoint. That also
# sidesteps the CORS block football-data.org applies to direct browser calls.
#
# Leave blank to fall back to clearly-labelled sample fixtures. Prefer setting
# the FOOTBALL_DATA_TOKEN environment variable over committing the key.
import os
FOOTBALL_DATA_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "c665fce411204ba6b5cb96d7d73a96fd")

# Backwards-compatible alias for older code that read API_FOOTBALL_KEY.
API_FOOTBALL_KEY = FOOTBALL_DATA_TOKEN

