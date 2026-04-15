# Email Connection

from django.core.mail import get_connection
import smtplib, imaplib, ssl

def get_email_smtp_connection(sender_provider, sender_email, sender_password):
    smtp_settings = {
        "gmail": ("smtp.gmail.com", 587, True, False),
        "zoho": ("smtp.zoho.com", 587, True, False),
        "yahoo": ("smtp.mail.yahoo.com", 587, True, False),
        "outlook": ("smtp-mail.outlook.com", 587, True, False),
        "icloud": ("smtp.mail.me.com", 587, True, False),
        "zeptomail": ("smtp.zeptomail.com", 587, True, False),
    }
    
    if sender_provider:
        sender_provider = sender_provider.lower()
    if sender_provider not in smtp_settings:
        print(f"Unsupported email provider: {sender_provider}")
        return None, f"Unsupported email provider: {sender_provider}"
    
    host, port, use_tls, use_ssl = smtp_settings[sender_provider]
    try:
        print(f"Connecting to {host}:{port} for {sender_email}")
        # Establish SMTP connection
    #     context = ssl.create_default_context()
    #     server = smtplib.SMTP(host, port)
    #     server.starttls(context=context)
    #     server.login(sender_email, sender_password)
    #     return server, None
    # except smtplib.SMTPAuthenticationError as e:
    #     return None, str(e)
    # except Exception as e:
    #     return None, f"Failed to connect: {str(e)}"
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=host,
            port=port,
            username=sender_email,
            password=sender_password,
            use_tls=use_tls,
            use_ssl=False,
        )
        # Test the connection by opening it
        connection.open()
        # connection.close()
        print(f"SMTP connection successful for {sender_provider}")
        return connection, None  # Success: return connection and no error
    except smtplib.SMTPAuthenticationError as e:
        print(f"Authentication failed for {sender_provider}: {str(e)}")
        return None, str(e)  # Return error message for user feedback
    except Exception as e:
        print(f"SMTP connection failed for {sender_provider}: {str(e)}")
        return None, str(e)

    
def get_email_imap_connection(sender_provider, sender_email, sender_password):
    if sender_provider == "gmail":
        return imaplib.IMAP4_SSL("imap.gmail.com", 993)
    elif sender_provider == "yahoo":
        return imaplib.IMAP4_SSL("imap.mail.yahoo.com", 993)
    elif sender_provider == "outlook":
        return imaplib.IMAP4_SSL("outlook.office365.com", 993)
    elif sender_provider == "zoho":
        return imaplib.IMAP4_SSL("imap.zoho.com", 993)
    elif sender_provider == "icloud":
        return imaplib.IMAP4_SSL("imap.mail.me.com", 993)
    else:
        return None
