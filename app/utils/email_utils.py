import smtplib
import secrets
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config

class EmailService:
    @staticmethod
    def send_otp(recipient_email, otp_code):
        """Sends a 6-digit OTP code to the recipient's email."""
        subject = "Action Required: Verify Your NicheForum Account"
        
        # HTML Content for a more professional look
        html_content = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e1e1e1; border-radius: 10px;">
                    <h2 style="color: #4648d4; text-align: center;">NicheForum Verification</h2>
                    <p>Hello,</p>
                    <p>Thank you for joining NicheForum! To complete your registration or sign-in, please use the following security code:</p>
                    <div style="background-color: #f4f4f9; padding: 20px; text-align: center; border-radius: 8px; margin: 20px 0;">
                        <span style="font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #4648d4;">{otp_code}</span>
                    </div>
                    <p style="font-size: 14px; color: #666;">This code will expire in 5 minutes. If you did not request this, please ignore this email.</p>
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                    <p style="font-size: 12px; color: #999; text-align: center;">&copy; 2026 NicheForum Team</p>
                </div>
            </body>
        </html>
        """
        
        msg = MIMEMultipart("alternative")
        msg['Subject'] = subject
        msg['From'] = config.EMAIL_SENDER
        msg['To'] = recipient_email
        
        # Plain text version for fallback
        text_content = f"Your NicheForum verification code is: {otp_code}. It expires in 5 minutes."
        
        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        try:
            with smtplib.SMTP(config.EMAIL_SMTP_SERVER, config.EMAIL_SMTP_PORT) as server:
                server.starttls()
                server.login(config.EMAIL_SENDER, config.EMAIL_SERVICE_API_KEY)
                server.sendmail(config.EMAIL_SENDER, recipient_email, msg.as_string())
            return True
        except Exception as e:
            print(f"DEBUG: Email delivery failed: {str(e)}")
            return False

    @staticmethod
    def generate_secure_otp(length=6):
        """Generates a cryptographically secure numeric OTP."""
        return ''.join(secrets.choice(string.digits) for _ in range(length))
  