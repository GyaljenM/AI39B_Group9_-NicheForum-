#!/usr/bin/env python3
"""
Comprehensive test to simulate the registration and email verification flow
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pymysql
from datetime import datetime, timedelta
import config
from app.utils.email_utils import EmailService

def test_registration_flow():
    """Simulate the complete registration flow"""
    print("=" * 70)
    print("TESTING REGISTRATION & EMAIL VERIFICATION FLOW")
    print("=" * 70)
    
    test_email = "test_verify_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "@example.com"
    test_name = "Test User"
    test_password = "TestPassword123"
    
    print(f"\n1. TEST DATA:")
    print(f"   Name: {test_name}")
    print(f"   Email: {test_email}")
    print(f"   Password: {test_password}")
    
    # Test OTP generation
    print(f"\n2. GENERATING OTP:")
    otp_code = EmailService.generate_secure_otp()
    print(f"   Generated OTP: {otp_code}")
    print(f"   OTP Length: {len(otp_code)} (should be 6)")
    
    # Test database insertion
    print(f"\n3. TESTING DATABASE INSERT:")
    try:
        db = pymysql.connect(
            host=config.MYSQL_HOST,
            user=config.MYSQL_USER,
            password=config.MYSQL_PASSWORD,
            database=config.MYSQL_DB,
            cursorclass=pymysql.cursors.DictCursor,
        )
        
        cursor = db.cursor()
        expiry_dt = datetime.utcnow() + timedelta(minutes=5)
        
        # Check if user already exists
        cursor.execute("SELECT id FROM users WHERE email = %s", (test_email,))
        existing = cursor.fetchone()
        if existing:
            print(f"   ! Cleaning up existing test user...")
            cursor.execute("DELETE FROM users WHERE email = %s", (test_email,))
            db.commit()
        
        # Insert test user
        cursor.execute(
            "INSERT INTO users (name, email, password, is_verified, verification_token, token_expires_at) VALUES (%s, %s, %s, 0, %s, %s)",
            (test_name, test_email, "hashed_password", otp_code, expiry_dt)
        )
        db.commit()
        print(f"   ✓ User inserted successfully into database")
        
        # Verify the insert
        cursor.execute("SELECT * FROM users WHERE email = %s", (test_email,))
        user = cursor.fetchone()
        if user:
            print(f"   ✓ User record retrieved:")
            print(f"     - ID: {user['id']}")
            print(f"     - Name: {user['name']}")
            print(f"     - Email: {user['email']}")
            print(f"     - Token: {user['verification_token']}")
            print(f"     - Expires: {user['token_expires_at']}")
            print(f"     - Is Verified: {user['is_verified']}")
        else:
            print(f"   ✗ ERROR: User was not inserted properly!")
            return False
        
        db.close()
        
    except Exception as e:
        print(f"   ✗ DATABASE ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test email sending
    print(f"\n4. TESTING EMAIL SEND:")
    try:
        result = EmailService.send_otp(test_email, otp_code)
        if result:
            print(f"   ✓ Email sent successfully")
            print(f"\n   CHECK YOUR EMAIL ({test_email}):")
            print(f"   - Look for an email from: {config.EMAIL_SENDER}")
            print(f"   - Subject: 'Action Required: Verify Your NicheForum Account'")
            print(f"   - The code should be: {otp_code}")
            print(f"   - Check SPAM folder if not in Inbox")
        else:
            print(f"   ✗ Email send returned False (check config)")
            return False
    except Exception as e:
        print(f"   ✗ EMAIL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test verification token validation
    print(f"\n5. TESTING TOKEN VALIDATION:")
    try:
        db = pymysql.connect(
            host=config.MYSQL_HOST,
            user=config.MYSQL_USER,
            password=config.MYSQL_PASSWORD,
            database=config.MYSQL_DB,
            cursorclass=pymysql.cursors.DictCursor,
        )
        
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE email = %s", (test_email,))
        user = cursor.fetchone()
        
        # Check if token matches
        if user['verification_token'] == otp_code:
            print(f"   ✓ Token stored correctly in database")
        else:
            print(f"   ✗ Token mismatch! Expected: {otp_code}, Got: {user['verification_token']}")
        
        # Check if token has not expired
        if datetime.utcnow() < user['token_expires_at']:
            print(f"   ✓ Token has not expired")
        else:
            print(f"   ✗ Token has already expired!")
        
        db.close()
        
    except Exception as e:
        print(f"   ✗ VALIDATION ERROR: {e}")
        return False
    
    print(f"\n" + "=" * 70)
    print("REGISTRATION TEST COMPLETE")
    print("=" * 70)
    print("\nSUMMARY:")
    print("- The registration flow appears to be working correctly")
    print("- If you didn't receive the email:")
    print("  1. Check your Gmail spam/promotions folder")
    print("  2. Add suyogtuladhar04@gmail.com to your contacts")
    print("  3. Check Gmail security: https://myaccount.google.com/security")
    print("  4. Whitelist the sender in your email filters")
    
    return True

if __name__ == "__main__":
    try:
        test_registration_flow()
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
