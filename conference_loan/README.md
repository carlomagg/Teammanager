# Conference Loan Module

## Overview
This module provides financing/loan functionality for conference organizers in partnership with Transave. It allows conference organizers to request loans for their conferences with proper KYC/KYB verification.

## Features

### 1. Loan Application
- Link to existing conferences
- Provide conference details and financial projections
- Enter guarantor information
- Upload supporting documents (optional, can add more later)
- Save as draft or submit for review

### 2. KYC/KYB Verification
- Only users with complete and verified KYC/KYB can request loans
- Automatic eligibility checking
- Supports both UserKYC and CompanyKYB verification

### 3. Loan Management
- Draft, submit, and track loan applications
- View loan status and history
- Upload supporting documents
- Add comments and notes

### 4. Review & Approval (Staff Only)
- Review loan applications
- Approve or reject with reasons
- Set approved amount, interest rate, and repayment terms
- Track disbursement and repayments

### 5. Transave Integration (Ready)
- Models include fields for Transave API integration
- `transave_loan_id` and `transave_response` fields
- Methods `submit_to_transave()` ready for API implementation

## Models

### ConferenceLoan
Main loan application model with:
- Conference linkage
- Loan details (amount, currency, reason, expected date)
- Conference description and financial projections
- Guarantor information
- KYC verification status
- Approval/rejection details
- Disbursement tracking
- Repayment tracking

### LoanDocument
Supporting documents for loan applications:
- Conference budget
- Business plan
- Financial statements
- Guarantor ID and letter
- Other documents

### LoanRepayment
Track loan repayments:
- Payment amount and reference
- Payment status
- Transave payment tracking

### LoanComment
Comments and notes on loan applications:
- Public and internal comments
- Audit trail

## Installation

1. Add `conference_loan` to `INSTALLED_APPS` in settings:
```python
INSTALLED_APPS = [
    # ... other apps
    'conference_loan',
]
```

2. Include URLs in main `urls.py`:
```python
urlpatterns = [
    # ... other patterns
    path('loans/', include('conference_loan.urls')),
]
```

3. Run migrations:
```bash
python manage.py makemigrations conference_loan
python manage.py migrate conference_loan
```

## Usage

### For Conference Organizers

1. **Check KYC Status**
   - Ensure your KYC/KYB is complete and verified
   - Visit the loan dashboard to check eligibility

2. **Create Loan Application**
   - Navigate to Loans > Apply for New Loan
   - Select your conference
   - Fill in loan details and guarantor information
   - Save as draft

3. **Upload Documents**
   - Add supporting documents (budget, business plan, etc.)
   - Upload guarantor ID and letter

4. **Submit for Review**
   - Review all information
   - Submit the application
   - Wait for review

5. **Track Status**
   - Monitor application status
   - Respond to comments
   - View approval details

### For Staff/Reviewers

1. **Review Applications**
   - View pending loan applications
   - Check KYC/KYB verification
   - Review documents and details

2. **Approve or Reject**
   - Set approved amount
   - Define interest rate and repayment terms
   - Or reject with reason

3. **Track Disbursement**
   - Mark loans as disbursed
   - Track repayments
   - Monitor outstanding balances

## API Integration (Transave)

The module is ready for Transave API integration. To implement:

1. Add Transave API credentials to `.env`:
```
TRANSAVE_API_KEY=your_api_key
TRANSAVE_API_URL=https://api.transave.com/v1
```

2. Implement the `submit_to_transave()` method in `models.py`:
```python
def submit_to_transave(self):
    import requests
    from django.conf import settings
    
    payload = {
        'reference': self.reference_number,
        'amount': float(self.amount),
        'currency': self.currency,
        'conference_id': self.conference.id,
        # ... other fields
    }
    
    response = requests.post(
        f"{settings.TRANSAVE_API_URL}/loans",
        headers={'Authorization': f'Bearer {settings.TRANSAVE_API_KEY}'},
        json=payload
    )
    
    if response.status_code == 200:
        data = response.json()
        self.transave_loan_id = data.get('loan_id')
        self.transave_response = data
        self.status = 'submitted_to_transave'
        self.save()
        return True
    return False
```

## Permissions

- **Any authenticated user**: Can view their own loan applications
- **Conference organizers**: Can create and submit loan applications
- **Tenant Administrators**: Can review, approve, and reject loans for their organization
- **Superusers**: Can review, approve, and reject all loans
- **KYC verified users only**: Can submit loan applications

**Note**: Only the tenant administrator (the user set as `tenant.admin`) and superusers can approve or reject loans. Regular staff members cannot review loans.

## URLs

- `/loans/` - Loan dashboard
- `/loans/list/` - List all loans
- `/loans/create/` - Create new loan application
- `/loans/<id>/` - View loan details
- `/loans/<id>/edit/` - Edit draft loan
- `/loans/<id>/submit/` - Submit loan for review
- `/loans/<id>/review/` - Review loan (staff only)
- `/loans/<id>/upload-document/` - Upload supporting documents
- `/loans/check-kyc/` - Check KYC eligibility (AJAX)

## Future Enhancements

1. Email notifications for status changes
2. Automated repayment schedule generation
3. Integration with payment gateways
4. Loan calculator
5. Credit scoring system
6. Bulk loan processing
7. Reporting and analytics dashboard
8. Mobile app support

## Support

For issues or questions, contact the development team.
