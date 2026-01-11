import smtplib
import markdown
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import (
    SMTP_SERVER,
    SMTP_PORT,
    SMTP_USERNAME,
    EMAIL_PASSWORD,
    EMAIL_SENDER,
    EMAIL_RECIPIENT,
)


def send_email(report_md: str):
    """
    Sends the Markdown report as an HTML email using SMTP.
    """
    if not SMTP_USERNAME or not EMAIL_PASSWORD or not EMAIL_RECIPIENT:
        print("Email credentials missing. Skipping email send.")
        return

    print(f"\n Sending email to {EMAIL_RECIPIENT} via {SMTP_SERVER}...")

    try:
        html_content = markdown.markdown(report_md)
        styled_html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #f4f4f4; padding: 10px; text-align: center; border-radius: 5px;">
                    <h2 style="color: #2c3e50; margin: 0;">The Daily AI Report</h2>
                    <p style="font-size: 12px; color: #7f8c8d;">{datetime.datetime.now().strftime('%B %d, %Y')}</p>
                </div>
                <div style="margin-top: 20px;">
                    {html_content}
                </div>
                <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="font-size: 11px; color: #999; text-align: center;">
                    Generated automatically by our AI Agent.
                </p>
            </body>
        </html>
        """

        msg = MIMEMultipart()
        msg["From"] = f"AI Newsletter <{EMAIL_SENDER}>"
        msg["To"] = EMAIL_RECIPIENT
        msg["Subject"] = (
            f"AI Market Report: {datetime.datetime.now().strftime('%Y-%m-%d')}"
        )
        msg.attach(MIMEText(styled_html, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, EMAIL_PASSWORD)
            server.send_message(msg)

        print("Email sent successfully!")

    except Exception as e:
        print(f"Failed to send email: {e}")
