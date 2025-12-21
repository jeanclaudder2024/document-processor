"""
Email Service - SMTP/IMAP Integration with Auto-Reply
Handles email sending, receiving, and AI-powered auto-replies
"""

import os
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
from supabase import create_client, Client
import openai

logger = logging.getLogger(__name__)

# Initialize Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# OpenAI for AI replies
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


class EmailService:
    """Email service for SMTP sending and IMAP receiving"""
    
    @staticmethod
    def get_smtp_config() -> Optional[Dict]:
        """Get SMTP configuration from database"""
        try:
            if not supabase:
                return None
            result = supabase.table('email_configurations').select('*').eq('type', 'smtp').eq('active', True).execute()
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error fetching SMTP config: {e}")
            return None
    
    @staticmethod
    def get_imap_config() -> Optional[Dict]:
        """Get IMAP configuration from database"""
        try:
            if not supabase:
                return None
            result = supabase.table('email_configurations').select('*').eq('type', 'imap').eq('active', True).execute()
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error fetching IMAP config: {e}")
            return None
    
    @staticmethod
    def test_smtp_connection(config: Dict) -> Dict[str, Any]:
        """Test SMTP connection - handles SSL (port 465) and TLS (port 587)"""
        try:
            port = config.get('port', 587)
            enable_tls = config.get('enable_tls', True)
            
            # Port 465 typically uses SSL (SMTP_SSL)
            if port == 465:
                server = smtplib.SMTP_SSL(config['host'], port, timeout=10)
            # Port 587 and others use TLS with STARTTLS when enabled
            elif enable_tls:
                server = smtplib.SMTP(config['host'], port, timeout=10)
                server.starttls()
            else:
                server = smtplib.SMTP(config['host'], port, timeout=10)
            
            server.login(config['username'], config['password'])
            server.quit()
            
            return {'success': True, 'message': 'SMTP connection successful'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def test_imap_connection(config: Dict) -> Dict[str, Any]:
        """Test IMAP connection"""
        try:
            if config.get('enable_tls'):
                mail = imaplib.IMAP4_SSL(config['host'], config['port'])
            else:
                mail = imaplib.IMAP4(config['host'], config['port'])
            
            mail.login(config['username'], config['password'])
            mail.logout()
            
            return {'success': True, 'message': 'IMAP connection successful'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def replace_placeholders(text: str, data: Dict[str, Any]) -> str:
        """Replace placeholders in email template"""
        result = text
        
        # System placeholders
        system_data = {
            'current_date': datetime.now().strftime('%B %d, %Y'),
            'current_year': str(datetime.now().year),
            'platform_name': data.get('platform_name', 'PetroDealHub'),
            'platform_url': data.get('platform_url', 'https://petrodealhub.com'),
        }
        
        # Merge with provided data
        all_data = {**system_data, **data}
        
        # Replace placeholders
        for key, value in all_data.items():
            if value is not None:
                placeholder = f'{{{{{key}}}}}'
                result = result.replace(placeholder, str(value))
        
        return result
    
    @staticmethod
    def send_email(
        to: str | List[str],
        subject: str,
        body: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        template_id: Optional[str] = None,
        placeholders: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Send email via SMTP"""
        try:
            config = EmailService.get_smtp_config()
            if not config:
                return {'success': False, 'error': 'SMTP not configured'}
            
            # Use template if provided
            if template_id:
                template = supabase.table('email_templates').select('*').eq('id', template_id).execute()
                if template.data:
                    template_data = template.data[0]
                    subject = EmailService.replace_placeholders(template_data['subject'], placeholders or {})
                    body = EmailService.replace_placeholders(template_data['body'], placeholders or {})
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{from_name or config.get('from_name', 'PetroDealHub')} <{from_email or config.get('from_email', config['username'])}>"
            
            if isinstance(to, list):
                msg['To'] = ', '.join(to)
                recipients = to
            else:
                msg['To'] = to
                recipients = [to]
            
            # Add body
            msg.attach(MIMEText(body, 'html'))
            
            # Send email - handle SSL (port 465) and TLS (port 587) properly
            port = config.get('port', 587)
            enable_tls = config.get('enable_tls', True)
            
            # Port 465 typically uses SSL (SMTP_SSL)
            if port == 465:
                server = smtplib.SMTP_SSL(config['host'], port, timeout=10)
            # Port 587 and others use TLS with STARTTLS when enabled
            elif enable_tls:
                server = smtplib.SMTP(config['host'], port, timeout=10)
                server.starttls()
            else:
                server = smtplib.SMTP(config['host'], port, timeout=10)
            
            server.login(config['username'], config['password'])
            server.send_message(msg, from_addr=config['username'], to_addrs=recipients)
            server.quit()
            
            # Log email sent
            if supabase:
                supabase.table('email_logs').insert({
                    'to_email': ','.join(recipients) if isinstance(recipients, list) else recipients,
                    'subject': subject,
                    'template_id': template_id,
                    'status': 'sent',
                    'sent_at': datetime.now().isoformat()
                }).execute()
            
            return {'success': True, 'message': 'Email sent successfully'}
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def sync_imap_emails() -> Dict[str, Any]:
        """Sync emails from IMAP server"""
        try:
            config = EmailService.get_imap_config()
            if not config:
                return {'success': False, 'error': 'IMAP not configured'}
            
            # Connect to IMAP
            if config.get('enable_tls'):
                mail = imaplib.IMAP4_SSL(config['host'], config['port'])
            else:
                mail = imaplib.IMAP4(config['host'], config['port'])
            
            mail.login(config['username'], config['password'])
            mail.select('INBOX')
            
            # Search for unread emails
            status, messages = mail.search(None, 'UNSEEN')
            email_ids = messages[0].split()
            
            new_emails = []
            for email_id in email_ids:
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                email_body = msg_data[0][1]
                email_message = email.message_from_bytes(email_body)
                
                # Extract email data
                from_email = email_message['From']
                subject = decode_header(email_message['Subject'])[0][0]
                if isinstance(subject, bytes):
                    subject = subject.decode()
                
                # Get body
                body = ""
                if email_message.is_multipart():
                    for part in email_message.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode()
                            break
                else:
                    body = email_message.get_payload(decode=True).decode()
                
                # Store in database
                if supabase:
                    result = supabase.table('incoming_emails').insert({
                        'from_email': from_email,
                        'subject': subject,
                        'body': body,
                        'received_at': datetime.now().isoformat(),
                        'processed': False,
                        'auto_replied': False
                    }).execute()
                    
                    if result.data:
                        new_emails.append(result.data[0])
            
            mail.logout()
            
            return {'success': True, 'count': len(new_emails), 'emails': new_emails}
        except Exception as e:
            logger.error(f"Error syncing IMAP emails: {e}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def generate_ai_reply(email_data: Dict) -> Dict[str, Any]:
        """Generate AI-powered auto-reply"""
        try:
            if not openai_client:
                return {'success': False, 'error': 'OpenAI not configured'}
            
            # Get platform context from database
            platform_name = "PetroDealHub"
            platform_url = "https://petrodealhub.com"
            
            # Create AI prompt
            prompt = f"""You are an AI assistant for {platform_name}, an oil trading platform.

You received an email:
From: {email_data.get('from')}
Subject: {email_data.get('subject')}
Body: {email_data.get('body')}

Generate a professional, helpful, and concise auto-reply email. The reply should:
1. Acknowledge receipt of the email
2. Provide relevant information if the question is clear
3. Direct them to support if needed
4. Be friendly and professional
5. Include the platform name: {platform_name}
6. Keep it under 150 words

Generate only the email body (no subject line needed):"""
            
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"You are a professional email assistant for {platform_name}."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.7
            )
            
            ai_reply = response.choices[0].message.content.strip()
            
            # Send auto-reply
            reply_subject = f"Re: {email_data.get('subject', 'Your Inquiry')}"
            send_result = EmailService.send_email(
                to=email_data.get('from'),
                subject=reply_subject,
                body=ai_reply
            )
            
            if send_result['success']:
                # Mark as replied
                if supabase:
                    supabase.table('incoming_emails').update({
                        'auto_replied': True,
                        'processed': True,
                        'reply_body': ai_reply,
                        'replied_at': datetime.now().isoformat()
                    }).eq('id', email_data.get('email_id')).execute()
                
                return {'success': True, 'reply': ai_reply, 'message': 'Auto-reply sent successfully'}
            else:
                return {'success': False, 'error': 'Failed to send auto-reply'}
                
        except Exception as e:
            logger.error(f"Error generating AI reply: {e}")
            return {'success': False, 'error': str(e)}

