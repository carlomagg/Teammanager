# Raadaa
## 📄 Document Automation & Workflow Management System

A Django-based internal web application for Business Development teams to streamline the generation, approval, and distribution of business documents like Approval Letters and SLA Agreements.

---

## 🚀 Features

- 🔐 Role-based access (BDA, BDM, Sales Rep, Admin)
- 📝 Document generation from templates using dynamic inputs
- 📄 Word to PDF conversion
- 👀 In-browser PDF preview via modal
- ✅ Approval workflow with status tracking
- 📧 Email delivery (via Chosen mail provider) with CC to Sales Rep and BDM
- 📆 Date & user filters on document list
- 🔍 Column-specific filtering (company, type, status, created by, etc.)
- 🧹 Auto-cleanup of old files
- 📁 Local file storage with download & delete options

---

## 🛠 Tech Stack

- **Backend:** Django, Python
- **Frontend:** Bootstrap, HTML, JavaScript
- **PDF Conversion:** `python-docx`, `pdfkit`, `wkhtmltopdf`
- **Database:** SQLite / PostgreSQL
- **Email:** Chosen mail provider SMTP Integration

---

## 📸 Screenshots

| Document List with Filters | PDF Preview Modal |
|----------------------------|-------------------|
| ![document list](screenshots/doc_list.png) | ![pdf modal](screenshots/pdf_preview.png) |

---

## ⚙️ Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/ShayYhee/DocSystem.git
cd raadaa
```

### 2. Run these
- python manage.py specialized_tags
- python manage.py comprehensive_tags_list
- python manage.py comprehensive_skills_list
- python manage.py industry_specific_skills


### 3. Create
- Create a Fernet Key \
- Create credentials/client_secret.json \
```json
{
  "web": {
    "client_id": "000000000000-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.apps.googleusercontent.com",
    "project_id": "dummy-project",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "DUMMY_CLIENT_SECRET_1234567890",
    "redirect_uris": [
      "http://localhost:8000/oauth2callback",
      "http://127.0.0.1:8000/oauth2callback",
      "https://example.com/oauth2callback"
    ],
    "javascript_origins": [
      "http://localhost:8000",
      "http://127.0.0.1:8000",
      "https://example.com"
    ]
  }
}
```
- Create credentials/google_service_account.json\
```json
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "your-private-key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_HERE\n-----END PRIVATE KEY-----\n",
  "client_email": "your-service-account@your-project-id.iam.gserviceaccount.com",
  "client_id": "your-client-id",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project-id.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}
```
- Add .env in the root folder for dev env variables

### 4. Do NOTs
- Don't tamper with settings.py (do not delete or alter anything)

### 5. Roles
Create the following Roles in your ADMIN MANAGEMENT SYSTEM:
- Admin
- HR
- HOD
- Sales Rep
- Conference Organizer
- Receptionist

### 6. EMAIL SENDING
To send mails do the following, use the following syntax:
```python
from .mail_connection import get_email_smtp_connection
superuser = CustomUser.objects.filter(is_superuser=True, is_active=True).first()
connection, error_message = get_email_smtp_connection(superuser.email_provider, superuser.email_address, superuser.get_smtp_password())
    if connection:
        try:
            # Create and send HTML email
            email = EmailMessage(
                subject=subject,
                body=html_content,
                from_email=superuser.email_address,
                to=[user.email],
                connection=connection
            )
            # Specify that this is HTML email
            email.content_subtype = "html"
            email.send()
            print("Email sent successfully via superuser")
        except Exception as e:
            print(f"Failed to send approval email: {e}")
    else:
        print(f"SMTP Connection Failed for superuser: {error_message}")
```

### 6. MANDATORY DEVELOPMENT WORKFLOW

We follow a **feature-branch workflow** with `develop` as the integration branch.  
**Never** push directly to `develop` or `main` — all changes go through Merge Requests (MRs).

#### Core rules
- Always start from an up-to-date `develop` branch
- Work on your own **feature/bugfix/hotfix** branch
- Keep your branch up-to-date with `develop` before pushing (to reduce merge conflicts)
- Push **only** to your personal branch
- Open a Merge Request (MR) to `develop` for review
- Use clear MR titles & descriptions (link issues/tickets if available)

#### Step-by-step workflow

1. **Update your local develop branch** (do this frequently — especially before starting new work)
   ```bash
   git checkout develop
   git pull origin develop    # or: git pull office develop   (use your actual remote name)
2. Create your feature branch from the latest develop
```bash
git checkout -b feature/your-feature-name    # recommended prefix
# or: git checkout -b bugfix/fix-login-issue
# or: git checkout -b your-initials/short-description
```
Alternative one-liner (if you already updated develop):
```bash 
git checkout develop && git pull origin develop && git checkout -b feature/your-feature-name
```
3. Do your work
- Make changes, commit often with clear messages
```bash
git add .
git commit -m "Add user profile endpoint with validation"
```
4. Keep your branch up-to-date with develop (very important – do this before every push / before creating/updating MR)\
5. Push your branch & Inform Team Lead



#### RUN THIS TO MIGRATE TO TRIAL SO SUBSCRIPTION WOULD BE REQUIRED AFTER 7 DAYS TRIAL ON YOUR LOCAL
python manage.py migrate_users_to_trial --go-live-date=YYYY-MM-DD
