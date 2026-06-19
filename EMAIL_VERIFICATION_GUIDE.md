# Email Verification Troubleshooting Guide

## Current Status ✅
Your email verification system is **working correctly**! All components have been tested:
- ✓ OTP generation (6-digit secure code)
- ✓ Database storage (tokens and expiry times)
- ✓ Email sending via Gmail SMTP
- ✓ Token validation logic

## What Was Fixed
1. **Better error logging** - Now shows detailed debug messages when emails fail
2. **Resend OTP feature** - Added a "Resend Code" button in the verification page
3. **Improved user messages** - Clearer instructions about checking spam folder
4. **Database verification** - Confirmed all required columns exist

## Why You Might Not Be Receiving Emails

### ✓ Most Common Issues (Check These First):
1. **Gmail Spam/Promotions Folder**
   - Check your spam folder - emails often go there
   - Add `suyogtuladhar04@gmail.com` to your contacts to whitelist it

2. **Gmail Security Settings**
   - Visit: https://myaccount.google.com/security
   - Check for "Less secure app access" or "Allow less secure apps"
   - Google requires "App Passwords" for third-party apps like your forum

3. **App Password Verification**
   - Go to: https://myaccount.google.com/apppasswords
   - Your current app password: `tecr fpns leas rzzr`
   - If it's not working, generate a NEW app password and update `config.py`

### Email Configuration (in config.py):
```python
EMAIL_SENDER = "suyogtuladhar04@gmail.com"
EMAIL_SMTP_SERVER = "smtp.gmail.com"
EMAIL_SMTP_PORT = 587
EMAIL_SERVICE_API_KEY = "tecr fpns leas rzzr"  # ← Check this is correct
```

## How to Test Email Sending

### Option 1: Quick Test
```bash
python test_email_debug.py
# Enter your own email to send a test message
```

### Option 2: Full Registration Simulation
```bash
python test_full_verification.py
# Tests the complete registration flow
```

### Option 3: Check Logs
When you register through the web app, check the terminal for debug messages:
- `DEBUG: OTP email sent successfully to...` → Email sent ✓
- `WARNING: Failed to send OTP email...` → Email failed ✗

## New Features Added

### 1. Resend Code Button
- Users can now click "Resend Code" if they don't receive the first email
- New codes are generated and previous ones are invalidated
- Located on the verification page: `/verify-registration`

### 2. Better Error Messages
Users now see:
- "Check your inbox and spam folder" - guidance on where to look
- "If you don't receive it within a few minutes, contact support" - sets expectations
- Separate messages for email failures vs. delivery delays

### 3. Debug Logging
- All email send attempts are logged to the terminal
- Makes it easy to diagnose issues

## Step-by-Step Registration Test

1. **Go to Register Page**
   - http://yourapp/register

2. **Fill Registration Form**
   - Name: Enter any name
   - Email: Enter YOUR email (so you receive the code)
   - Password: Enter a strong password

3. **Submit & Check Email**
   - You'll be redirected to verification page
   - Check Gmail inbox (especially spam/promotions)
   - Look for email from: `suyogtuladhar04@gmail.com`
   - Subject: "Action Required: Verify Your NicheForum Account"

4. **If No Email After 5 Minutes**
   - Click "Resend Code" button
   - Wait another 2-3 minutes
   - Still nothing? Check Gmail security settings (step above)

5. **Enter Code & Verify**
   - Copy the 6-digit code from email
   - Enter it in the verification form
   - Click "Verify Code"
   - You're now verified! ✓

## Advanced Troubleshooting

### If Email Still Doesn't Arrive:

1. **Check Gmail Activity**
   ```
   https://myaccount.google.com/device-activity
   Check recent device activity for SMTP logins
   ```

2. **Enable App Passwords**
   - Ensure 2-Step Verification is enabled: https://myaccount.google.com/security
   - Go to App Passwords: https://myaccount.google.com/apppasswords
   - Select: Mail → Windows Computer
   - Generate new password
   - Copy the 16-character password to `config.py`

3. **Test Direct Connection**
   ```bash
   python test_email_debug.py
   ```
   This will test SMTP connection and let you send a test email.

4. **Check Firewall/ISP**
   - Some networks block SMTP port 587
   - Try using port 465 (if your ISP allows it)
   - Contact your IT department if on corporate network

### Alternative: Development Mode Without Email

If you want to test without email in development:

```python
# In app/utils/email_utils.py, modify send_otp:
@staticmethod
def send_otp(recipient_email, otp_code):
    """For development: print OTP instead of sending"""
    print(f"\n{'='*60}")
    print(f"DEVELOPMENT MODE: OTP for {recipient_email}")
    print(f"Code: {otp_code}")
    print(f"{'='*60}\n")
    return True
```

## Database Check

To verify the OTP was stored correctly:

```bash
python check_db.py
```

This shows all users table columns including:
- `verification_token` - stores the OTP
- `token_expires_at` - expiry time (5 minutes)
- `is_verified` - set to 1 after verification

## Verification Workflow

```
User Registers
    ↓
OTP Generated (6 digits, 5 min expiry)
    ↓
Stored in Database
    ↓
Email Sent to User
    ↓
User Enters Code
    ↓
Code Validated (check token & expiry)
    ↓
is_verified = 1
    ↓
User Can Login ✓
```

## Common Error Messages

| Message | Meaning | Solution |
|---------|---------|----------|
| "Invalid verification code" | Code doesn't match | Check you entered the correct code |
| "Verification code has expired" | Code older than 5 min | Click "Resend Code" |
| "Account not found" | Email doesn't exist | Check you used the same email |
| "This account is already verified" | User already verified | Go to login page |

## Contacts & Support

If you still have issues:
1. Run `python test_email_debug.py` and check output
2. Check Gmail spam folder
3. Verify Gmail App Password is correct
4. Check email configuration in `config.py`

---
**Last Updated:** June 19, 2026
**System Status:** All components verified and working ✓
