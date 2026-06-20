import pymysql
import secrets
import smtplib  # Built-in Python Google SMTP tool
from email.mime.text import MIMEText  # Standard raw mail formatter
from datetime import datetime, timedelta
from flask import Flask, request, render_template

# --- 1. DATABASE CONFIGURATION ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'your_mysql_user',
    'password': 'your_mysql_password',
    'database': 'nicheforum_db',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

app = Flask(__name__)

# --- 1. DATABASE CONFIGURATION ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'your_mysql_user',
    'password': 'your_mysql_password',
    'database': 'nicheforum_db',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# --- 2. GOOGLE SMTP CONFIGURATION ---
GMAIL_SENDER = "suyogtuladhar04@gmail.com"      # <-- Your real Gmail address
GMAIL_APP_PASSWORD = "tecr fpns leas rzzr"   # <-- Your 16-digit Google App Password
SMTP_SERVER = "smtp.gmail.com"                # Official Google mail relay address
SMTP_PORT = 587                               # Standard secure TLS system port

def init_db():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    is_verified TINYINT DEFAULT 0,
                    verification_token VARCHAR(10),
                    token_expires_at DATETIME
                )
            """)
        conn.commit()
    finally:
        conn.close()

# --- 3. GOOGLE SMTP DELIVERY ENGINE ---
def send_otp_via_gmail(recipient_email, otp_code):
    subject = "Your NicheForum Verification Code"
    body = f"Hello,\n\nYour 6-digit security code is: {otp_code}\n\nThis code will automatically expire in 5 minutes."
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = GMAIL_SENDER
    msg['To'] = recipient_email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)  
            server.sendmail(GMAIL_SENDER, recipient_email, msg.as_string())  
        print(f"✅ Success! Google safely delivered the code to {recipient_email}")
        return True
    except Exception as error:
        print(f"❌ Google SMTP Connection Error: {error}")
        return False

def generate_and_store_otp(email):
    otp_code = str(secrets.randbelow(900000) + 100000)
    expiry = datetime.utcnow() + timedelta(minutes=5)
    
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            # Translated SQLite's "ON CONFLICT" syntax to native MySQL "ON DUPLICATE KEY UPDATE"
            query = """
                INSERT INTO users (email, is_verified, verification_token, token_expires_at)
                VALUES (%s, 0, %s, %s)
                ON DUPLICATE KEY UPDATE
                    verification_token = VALUES(verification_token),
                    token_expires_at = VALUES(token_expires_at),
                    is_verified = 0
            """
            cursor.execute(query, (email, otp_code, expiry))
        conn.commit()
    finally:
        conn.close()
    return otp_code

def verify_user_otp(email, submitted_otp):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            
            if not user:
                return "User account reference profile not found.", 404
            if not user["verification_token"] or user["verification_token"] != submitted_otp:
                return "Incorrect verification code.", 400
                
            # PyMySQL handles DATETIME fields natively as Python datetime objects
            expiry_dt = user["token_expires_at"]
            if datetime.utcnow() > expiry_dt:
                return "Code has expired.", 400
                
            cursor.execute("""
                UPDATE users 
                SET is_verified = 1, verification_token = NULL, token_expires_at = NULL 
                WHERE email = %s
            """, (email,))
        conn.commit()
        return "Success", 200
    finally:
        conn.close()

# --- ROUTES ---
@app.route('/')
def home():
    return render_template('register_trigger.html')

@app.route('/trigger-register', methods=['POST'])
def trigger_register():
    target_email = request.form.get('user_email') 
    
    if not target_email:
        return "<h3 style='color:red; text-align:center;'>Error: Email input was empty.</h3>", 400
        
    secret_otp = generate_and_store_otp(target_email)
    email_was_sent = send_otp_via_gmail(target_email, secret_otp)
    
    if not email_was_sent:
        return "<h3 style='color:red; text-align:center;'>Google Mail Delivery Blocked. Check your App Password configurations.</h3>", 500
        
    return render_template('enter_otp.html', email=target_email)

@app.route('/verify-otp', methods=['POST'])
def verify_otp():
    email = request.form.get('email')
    otp = request.form.get('otp')
    message, code = verify_user_otp(email, otp)
    if code == 200:
        return render_template('success.html')
    else:
        return render_template('failed.html', error_message=message), code

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5003)
