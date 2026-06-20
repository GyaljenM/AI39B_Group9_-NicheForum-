#!/usr/bin/env python3
"""
Test script to debug email sending issues
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config

def test_email_connection():
    """Test if we can connect to Gmail SMTP server"""
    print("=" * 60)
    print("TESTING EMAIL CONFIGURATION")
    print("=" * 60)
    
    # Display config (without exposing full password)
    print(f"\n1. Configuration Check:")
    print(f"   EMAIL_SENDER: {config.EMAIL_SENDER}")
    print(f"   SMTP_SERVER: {config.EMAIL_SMTP_SERVER}")
    print(f"   SMTP_PORT: {config.EMAIL_SMTP_PORT}")
    print(f"   API_KEY: {config.EMAIL_SERVICE_API_KEY[:10]}...{config.EMAIL_SERVICE_API_KEY[-4:]}")
    
    # Test SMTP connection
    print(f"\n2. Testing SMTP Connection...")
    try:
        with smtplib.SMTP(config.EMAIL_SMTP_SERVER, config.EMAIL_SMTP_PORT) as server:
            print("   ✓ Connected to SMTP server")
            
            # Start TLS
            server.starttls()
            print("   ✓ TLS started successfully")
            
            # Try to login
            server.login(config.EMAIL_SENDER, config.EMAIL_SERVICE_API_KEY)
            print("   ✓ Authentication successful")
            
            return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"   ✗ AUTHENTICATION FAILED: {e}")
        print("\n   SOLUTION:")
        print("   - Verify the Gmail App Password is correct")
        print("   - Ensure 2-Step Verification is enabled on your Google Account")
        print("   - Go to: https://myaccount.google.com/apppasswords")
        print("   - Generate a new App Password for 'Mail' and 'Windows Computer'")
        print("   - Update EMAIL_SERVICE_API_KEY in config.py")
        return False
    except smtplib.SMTPException as e:
        print(f"   ✗ SMTP ERROR: {e}")
        print("\n   SOLUTION:")
        print("   - Check your internet connection")
        print("   - Verify SMTP_SERVER and SMTP_PORT are correct")
        print("   - Try: SMTP_SERVER = 'smtp.gmail.com', SMTP_PORT = 587")
        return False
    except Exception as e:
        print(f"   ✗ UNEXPECTED ERROR: {e}")
        return False

def test_send_email(test_recipient):
    """Test sending an actual email"""
    print(f"\n3. Testing Email Send to: {test_recipient}")
    try:
        otp_code = "123456"
        subject = "Test - NicheForum Verification Code"
        
        html_content = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e1e1e1; border-radius: 10px;">
                    <h2 style="color: #4648d4;">Test Email - NicheForum</h2>
                    <p>Your test verification code is:</p>
                    <div style="background-color: #f4f4f9; padding: 20px; text-align: center; border-radius: 8px;">
                        <span style="font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #4648d4;">{otp_code}</span>
                    </div>
                    <p>If you didn't request this, ignore the email.</p>
                </div>
            </body>
        </html>
        """
        
        msg = MIMEMultipart("alternative")
        msg['Subject'] = subject
        msg['From'] = config.EMAIL_SENDER
        msg['To'] = test_recipient
        
        text_content = f"Test code: {otp_code}"
        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))
        
        with smtplib.SMTP(config.EMAIL_SMTP_SERVER, config.EMAIL_SMTP_PORT) as server:
            server.starttls()
            server.login(config.EMAIL_SENDER, config.EMAIL_SERVICE_API_KEY)
            server.sendmail(config.EMAIL_SENDER, test_recipient, msg.as_string())
        
        print(f"   ✓ Test email sent successfully to {test_recipient}")
        print("\n   NEXT STEPS:")
        print("   - Check your email inbox (and spam folder)")
        print("   - If email arrives, the configuration is working!")
        print("   - If not, check Gmail security settings")
        return True
    except Exception as e:
        print(f"   ✗ Failed to send email: {e}")
        return False

if __name__ == "__main__":
    # Test connection
    if test_email_connection():
        # Ask for test recipient
        test_email = input("\n4. Enter an email address to send a test message (or press Enter to skip): ").strip()
        if test_email:
            test_send_email(test_email)
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)
