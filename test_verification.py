import sqlite3
import secrets
import smtplib  # Built-in Python Google SMTP tool
from email.mime.text import MIMEText  # Standard raw mail formatter
from datetime import datetime, timedelta
from flask import Flask, request, render_template

app = Flask(__name__)
DB_FILE = "users.db"

# --- 1. GOOGLE SMTP CONFIGURATION ---
GMAIL_SENDER = "suyogtuladhar04@gmail.com"      # <-- Your real Gmail address
GMAIL_APP_PASSWORD = "tecr fpns leas rzzr"   # <-- Your 16-digit Google App Password
SMTP_SERVER = "smtp.gmail.com"                # Official Google mail relay address
SMTP_PORT = 587                               # Standard secure TLS system port

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                is_verified INTEGER DEFAULT 0,
                verification_token TEXT,
                token_expires_at TEXT
            )
        """)
        conn.commit()

# --- 2. GOOGLE SMTP DELIVERY ENGINE ---
def send_otp_via_gmail(recipient_email, otp_code):
    subject = "Your NicheForum Verification Code"
    body = f"Hello,\n\nYour 6-digit security code is: {otp_code}\n\nThis code will automatically expire in 5 minutes."
    
    # Format the message packet using pure standard text rules
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = GMAIL_SENDER
    msg['To'] = recipient_email

    try:
        # Establish connection with the Google web data grid
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # Encrypt the network connection safely via TLS
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)  # Authenticate script passcodes
            server.sendmail(GMAIL_SENDER, recipient_email, msg.as_string())  # Dispatch packet
        print(f"✅ Success! Google safely delivered the code to {recipient_email}")
        return True
    except Exception as error:
        print(f"❌ Google SMTP Connection Error: {error}")
        return False

def generate_and_store_otp(email):
    otp_code = str(secrets.randbelow(900000) + 100000)
    expiry = (datetime.utcnow() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (email, is_verified, verification_token, token_expires_at)
            VALUES (?, 0, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                verification_token=excluded.verification_token,
                token_expires_at=excluded.token_expires_at,
                is_verified=0
        """, (email, otp_code, expiry))
        conn.commit()
    return otp_code

def verify_user_otp(email, submitted_otp):
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        if not user:
            return "User account reference profile not found.", 404
        if not user["verification_token"] or user["verification_token"] != submitted_otp:
            return "Incorrect verification code.", 400
        expiry_dt = datetime.strptime(user["token_expires_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.utcnow() > expiry_dt:
            return "Code has expired.", 400
        cursor.execute("UPDATE users SET is_verified = 1, verification_token = NULL, token_expires_at = NULL WHERE email = ?", (email,))
        conn.commit()
        return "Success", 200

# --- ROUTES ---
@app.route('/')
def home():
    return render_template('register_trigger.html')

@app.route('/trigger-register', methods=['POST'])
def trigger_register():
    # Capture whichever real email address is typed into the browser form
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
    app.run(debug=True, host='0.0.0.0', port=5001)
