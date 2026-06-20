#!/usr/bin/env python
from app.models.database import Database
from werkzeug.security import generate_password_hash

db = Database()

# Create a test user
password = generate_password_hash('testpass123')
email = 'test@test.com'
name = 'Test User'

# Check if user exists and delete if it does
existing = db.fetch_one('SELECT id FROM users WHERE email = %s', (email,))
if existing:
    db.execute('DELETE FROM users WHERE id = %s', (existing['id'],))
    print(f'Deleted existing user: {email}')

# Create the user
db.execute(
    'INSERT INTO users (email, name, password, is_verified) VALUES (%s, %s, %s, 1)',
    (email, name, password)
)
print(f'Created user: {email}')

# Get the user ID
user = db.fetch_one('SELECT id FROM users WHERE email = %s', (email,))
print(f'User ID: {user["id"]}')
print(f'Password: testpass123 (hashed in database)')
    
db.close()
