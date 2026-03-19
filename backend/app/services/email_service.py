import resend
from flask import current_app

class EmailService:
    @staticmethod
    def send_application_notification(user_email, job_details):
        """
        Sends an email notification via Resend when a job application is sent.
        """
        api_key = current_app.config.get('RESEND_API_KEY')
        if not api_key:
            print("[EmailService] Error: RESEND_API_KEY not configured.")
            return False

        resend.api_key = api_key

        job_title = job_details.get('title', 'Unknown Position')
        company_name = job_details.get('company', 'Unknown Company')
        location = job_details.get('location', 'Remote/Not specified')
        job_url = job_details.get('url', '#')

        try:
            params = {
                "from": "AutoJobAgent <onboarding@resend.dev>",
                "to": [user_email],
                "subject": f"Application Sent: {job_title} at {company_name}",
                "html": f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                    <h2 style="color: #333;">Application Successfully Sent!</h2>
                    <p>Hello,</p>
                    <p>Great news! Your application for the <strong>{job_title}</strong> position at <strong>{company_name}</strong> has been successfully submitted.</p>
                    
                    <div style="background-color: #f9f9f9; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #555;">Company Details</h3>
                        <p><strong>Company:</strong> {company_name}</p>
                        <p><strong>Location:</strong> {location}</p>
                        <p><strong>Job URL:</strong> <a href="{job_url}" style="color: #007bff;">View Job Posting</a></p>
                    </div>

                    <p>We'll keep you updated if there are any changes in your application status.</p>
                    <p>Best of luck,<br>The AutoJobAgent Team</p>
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                    <p style="font-size: 12px; color: #888;">This is an automated message from AutoJobAgent.</p>
                </div>
                """
            }

            email = resend.Emails.send(params)
            print(f"[EmailService] Email sent successfully to {user_email}. ID: {email['id']}")
            return True
        except Exception as e:
            print(f"[EmailService] Failed to send email: {e}")
            return False
