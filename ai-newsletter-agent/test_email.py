import smtplib
import os
import markdown
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp-mail.outlook.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))

# AUTHENTICATION
# Default to EMAIL_SENDER if SMTP_USERNAME is not set
SMTP_USERNAME = os.environ.get("SMTP_USERNAME") or os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

# HEADERS
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT")


def test_send_email():
    print("🧪 STARTING EMAIL TEST (Split Auth Mode)...")
    print(f"   Server:    {SMTP_SERVER}:{SMTP_PORT}")
    print(f"   Auth User: {SMTP_USERNAME}")
    print(f"   Sender:    {EMAIL_SENDER}")
    print(f"   Recipient: {EMAIL_RECIPIENT}")

    if not SMTP_USERNAME or not EMAIL_PASSWORD or not EMAIL_SENDER:
        print("\n❌ ERROR: Missing environment variables.")
        return

    # Basic HTML Content
    html_content = f"""
    <html>
        <body>
            <h2>Test Successful</h2>
            <p>This email was sent using <b>Split Authentication</b>.</p>
            <ul>
                <li><b>Logged in as:</b> {SMTP_USERNAME}</li>
                <li><b>Sent as:</b> {EMAIL_SENDER}</li>
            </ul>
        </body>
    </html>
    """

    msg = MIMEMultipart()
    # The 'From' header is what the recipient sees. It must be your verified email.
    msg["From"] = f"AI Test Bot <{EMAIL_SENDER}>"
    msg["To"] = EMAIL_RECIPIENT
    msg["Subject"] = (
        f"🧪 Split Auth Test - {datetime.datetime.now().strftime('%H:%M:%S')}"
    )
    msg.attach(MIMEText(html_content, "html"))

    try:
        print("\n🔌 Connecting to SMTP server...")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.set_debuglevel(1)
            server.starttls()
            server.ehlo()

            print(f"🔑 Logging in as {SMTP_USERNAME}...")
            # We log in with the ID...
            server.login(SMTP_USERNAME, EMAIL_PASSWORD)

            print(f"📨 Sending as {EMAIL_SENDER}...")
            # ...but we send as the Verified Email
            server.send_message(msg)

        print("\n✅ SUCCESS: Email sent successfully!")

    except Exception as e:
        print(f"\n❌ FAILED: {e}")


if __name__ == "__main__":
    test_send_email()
