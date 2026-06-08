import pymysql
import config

# Check table schema
db = pymysql.connect(
    host=config.MYSQL_HOST,
    user=config.MYSQL_USER,
    password=config.MYSQL_PASSWORD,
    database=config.MYSQL_DB,
    cursorclass=pymysql.cursors.DictCursor,
)

cursor = db.cursor()

# Check users table columns
cursor.execute("DESCRIBE users")
columns = cursor.fetchall()
print("\n=== USERS TABLE SCHEMA ===")
for col in columns:
    print(f"  {col['Field']}: {col['Type']} (Null: {col['Null']}, Default: {col['Default']})")

# Check if test user exists
cursor.execute("SELECT * FROM users WHERE email = %s", ("johntest@example.com",))
existing = cursor.fetchone()
print(f"\n=== TEST USER LOOKUP ===")
if existing:
    print(f"  Email: {existing['email']}")
    print(f"  Is Verified: {existing['is_verified']} (should be 1 after verification)")
    print(f"  Token: {existing['verification_token']} (should be None after verification)")
else:
    print("  User not found")

db.close()
print("\nDone!")
