from app.models.database import Database

db = Database()
users = db.fetch_all('SELECT id, name, email, is_active, role FROM users')
db.close()

print('\n=== ALL USERS ===')
for u in users:
    status = 'ACTIVE' if u['is_active'] else 'INACTIVE'
    print(f"ID {u['id']}: {u['name']} ({u['email']}) - {status} - Role: {u['role']}")

print(f'\nTotal: {len(users)} users')
print(f'Active: {sum(1 for u in users if u["is_active"])} users')
