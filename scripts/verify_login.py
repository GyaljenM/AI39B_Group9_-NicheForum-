import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models.database import Database
from werkzeug.security import check_password_hash

EMAIL = 'adimn@admin.com'
PASSWORD = 'admin'

print('Using credentials:', EMAIL, PASSWORD)

# Verify DB row and hash
try:
    db = Database()
    user = db.fetch_one('SELECT * FROM users WHERE email = %s', (EMAIL,))
    db.close()
    if not user:
        print('User not found in database')
    else:
        print('User found:', user['email'], 'role=', user['role'], 'active=', user['is_active'])
        print('Password hash check:', check_password_hash(user['password'], PASSWORD))
except Exception as e:
    print('DB error:', e)
    raise

app = create_app()
with app.test_client() as client:
    response = client.post('/login', data={'email': EMAIL, 'password': PASSWORD}, follow_redirects=True)
    print('POST /login status:', response.status_code)
    print('Final path:', response.request.path)
    data = response.data.decode('utf-8', errors='replace')
    print('Contains incorrect flash:', 'Incorrect email or password' in data)
    print('Contains welcome flash:', 'Welcome back' in data)
    print('Response length:', len(data))
    print('Response snippet:')
    print(data[:1200])
