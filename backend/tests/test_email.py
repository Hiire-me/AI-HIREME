import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.services.email_service import EmailService

def test_send_email():
    app = create_app()
    with app.app_context():
        # Using a test email address (or the user's if known, but let's try a generic or dummy one first)
        # Actually, Resend onboarding@resend.dev can only send to the owner's email by default.
        # I will use a placeholder and expect the user to see it if they are the owner.
        test_email = "delivered@resend.dev" # This is often used for testing in some services, or just use the user's email if possible.
        # However, for Resend free tier, you can only send to the email you signed up with.
        # I'll try sending to a likely address or just print that we are ready for a real test.
        
        print(f"Attempting to send a test email to {test_email}...")
        success = EmailService.send_application_notification(
            test_email,
            {
                'title': 'Test Software Engineer',
                'company': 'Test Corp',
                'location': 'Remote',
                'url': 'https://example.com'
            }
        )
        if success:
            print("Test email sent successfully!")
        else:
            print("Failed to send test email.")

if __name__ == "__main__":
    test_send_email()
