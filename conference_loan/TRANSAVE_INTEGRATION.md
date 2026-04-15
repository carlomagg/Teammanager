# Transave API Integration Guide

## Overview
This document provides instructions for integrating the Conference Loan module with Transave's API.

## Configuration

### 1. Environment Variables
Add the following to your `.env` file:

```env
# Transave API Configuration
TRANSAVE_API_KEY=your_api_key_here
TRANSAVE_API_URL=https://api.transave.com/v1
TRANSAVE_SECRET_KEY=your_secret_key_here
TRANSAVE_ENABLED=True
```

### 2. Settings
The settings are already configured in `raadaa/settings.py`:

```python
TRANSAVE_API_KEY = os.getenv('TRANSAVE_API_KEY', '')
TRANSAVE_API_URL = os.getenv('TRANSAVE_API_URL', 'https://api.transave.com/v1')
TRANSAVE_SECRET_KEY = os.getenv('TRANSAVE_SECRET_KEY', '')
TRANSAVE_ENABLED = os.getenv('TRANSAVE_ENABLED', 'False') == 'True'
```

## Service Implementation

The `TransaveService` class in `conference_loan/transave_service.py` provides the following methods:

### 1. Submit Loan Application
```python
from conference_loan.transave_service import get_transave_service

transave = get_transave_service()
result = transave.submit_loan_application(loan)

if result['success']:
    loan.transave_loan_id = result['loan_id']
    loan.transave_response = result['data']
    loan.status = 'submitted_to_transave'
    loan.save()
```

### 2. Check Loan Status
```python
result = transave.check_loan_status(loan.transave_loan_id)

if result['success']:
    status = result['status']
    # Update loan status based on Transave response
```

### 3. Process Disbursement
```python
bank_details = {
    'account_name': 'Company Name',
    'account_number': '1234567890',
    'bank_code': '058',
    'bank_name': 'GTBank'
}

result = transave.process_disbursement(loan, bank_details)

if result['success']:
    loan.disbursement_reference = result['reference']
    loan.disbursement_date = timezone.now()
    loan.status = 'disbursed'
    loan.save()
```

### 4. Record Repayment
```python
result = transave.record_repayment(
    loan=loan,
    amount=Decimal('50000.00'),
    payment_reference='PAY-123456'
)

if result['success']:
    # Create LoanRepayment record
    from conference_loan.models import LoanRepayment
    
    repayment = LoanRepayment.objects.create(
        loan=loan,
        amount=amount,
        payment_reference=payment_reference,
        status='completed',
        transave_payment_id=result['payment_id']
    )
```

### 5. Get Repayment Schedule
```python
result = transave.get_repayment_schedule(loan)

if result['success']:
    schedule = result['schedule']
    # Display or process schedule
```

## API Endpoints to Implement

The following Transave API endpoints need to be implemented (replace with actual endpoints):

### 1. Submit Loan
```
POST /loans/submit
Headers:
  - Authorization: Bearer {API_KEY}
  - X-Secret-Key: {SECRET_KEY}
  - Content-Type: application/json

Body:
{
  "reference": "LOAN-20260409-0001",
  "applicant": {
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+2348012345678"
  },
  "company": {
    "name": "Tech Company Ltd",
    "registration_number": "RC123456"
  },
  "loan": {
    "amount": 1000000.00,
    "currency": "NGN",
    "reason": "Conference venue booking",
    "expected_date": "2026-05-01"
  },
  "conference": {
    "title": "Tech Summit 2026",
    "start_date": "2026-06-15",
    "end_date": "2026-06-17",
    "venue": "Eko Hotel, Lagos",
    "description": "Annual technology conference",
    "expected_revenue": 5000000.00,
    "expected_expenses": 3000000.00
  },
  "guarantor": {
    "name": "Jane Smith",
    "phone": "+2348098765432",
    "email": "jane@example.com",
    "address": "123 Main St, Lagos",
    "relationship": "Business Partner",
    "occupation": "CEO"
  },
  "kyc_verified": true
}

Response:
{
  "success": true,
  "loan_id": "TRV-LOAN-123456",
  "status": "pending_review",
  "message": "Loan application submitted successfully"
}
```

### 2. Check Loan Status
```
GET /loans/{loan_id}/status
Headers:
  - Authorization: Bearer {API_KEY}
  - X-Secret-Key: {SECRET_KEY}

Response:
{
  "success": true,
  "loan_id": "TRV-LOAN-123456",
  "status": "approved",
  "approved_amount": 1000000.00,
  "interest_rate": 5.5,
  "repayment_period_months": 12
}
```

### 3. Process Disbursement
```
POST /loans/{loan_id}/disburse
Headers:
  - Authorization: Bearer {API_KEY}
  - X-Secret-Key: {SECRET_KEY}
  - Content-Type: application/json

Body:
{
  "loan_id": "TRV-LOAN-123456",
  "amount": 1000000.00,
  "currency": "NGN",
  "bank_details": {
    "account_name": "Tech Company Ltd",
    "account_number": "1234567890",
    "bank_code": "058",
    "bank_name": "GTBank"
  }
}

Response:
{
  "success": true,
  "reference": "DISB-123456",
  "status": "processing",
  "message": "Disbursement initiated"
}
```

### 4. Record Repayment
```
POST /loans/{loan_id}/repayment
Headers:
  - Authorization: Bearer {API_KEY}
  - X-Secret-Key: {SECRET_KEY}
  - Content-Type: application/json

Body:
{
  "loan_id": "TRV-LOAN-123456",
  "amount": 50000.00,
  "currency": "NGN",
  "reference": "PAY-123456"
}

Response:
{
  "success": true,
  "payment_id": "TRV-PAY-789012",
  "outstanding_balance": 950000.00,
  "next_payment_date": "2026-07-01",
  "next_payment_amount": 50000.00
}
```

### 5. Get Repayment Schedule
```
GET /loans/{loan_id}/schedule
Headers:
  - Authorization: Bearer {API_KEY}
  - X-Secret-Key: {SECRET_KEY}

Response:
{
  "success": true,
  "loan_id": "TRV-LOAN-123456",
  "schedule": [
    {
      "payment_number": 1,
      "due_date": "2026-07-01",
      "amount": 50000.00,
      "principal": 45000.00,
      "interest": 5000.00,
      "status": "pending"
    },
    {
      "payment_number": 2,
      "due_date": "2026-08-01",
      "amount": 50000.00,
      "principal": 45500.00,
      "interest": 4500.00,
      "status": "pending"
    }
    // ... more payments
  ]
}
```

## Webhook Implementation

Create a webhook handler to receive updates from Transave:

```python
# In conference_loan/views.py

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
import hmac
import hashlib

@csrf_exempt
def transave_webhook(request):
    """Handle webhooks from Transave"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    # Verify webhook signature
    signature = request.headers.get('X-Transave-Signature')
    if not verify_transave_signature(request.body, signature):
        return JsonResponse({'error': 'Invalid signature'}, status=401)
    
    try:
        data = json.loads(request.body)
        event_type = data.get('event')
        loan_id = data.get('loan_id')
        
        # Find the loan
        loan = ConferenceLoan.objects.get(transave_loan_id=loan_id)
        
        # Handle different event types
        if event_type == 'loan.approved':
            loan.status = 'approved'
            loan.approved_amount = Decimal(data.get('approved_amount'))
            loan.interest_rate = Decimal(data.get('interest_rate'))
            loan.repayment_period_months = data.get('repayment_period_months')
            loan.save()
            
            # Send notification to applicant
            # TODO: Implement email notification
            
        elif event_type == 'loan.rejected':
            loan.status = 'rejected'
            loan.rejection_reason = data.get('reason')
            loan.save()
            
            # Send notification to applicant
            # TODO: Implement email notification
            
        elif event_type == 'loan.disbursed':
            loan.status = 'disbursed'
            loan.disbursement_date = timezone.now()
            loan.disbursement_reference = data.get('reference')
            loan.save()
            
            # Send notification to applicant
            # TODO: Implement email notification
            
        elif event_type == 'repayment.received':
            # Create repayment record
            LoanRepayment.objects.create(
                loan=loan,
                amount=Decimal(data.get('amount')),
                payment_reference=data.get('reference'),
                status='completed',
                transave_payment_id=data.get('payment_id')
            )
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


def verify_transave_signature(payload, signature):
    """Verify webhook signature from Transave"""
    from django.conf import settings
    
    expected_signature = hmac.new(
        settings.TRANSAVE_SECRET_KEY.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)
```

Add webhook URL to `conference_loan/urls.py`:
```python
path('webhook/transave/', views.transave_webhook, name='transave_webhook'),
```

## Testing

### 1. Test Configuration
```python
from conference_loan.transave_service import get_transave_service

transave = get_transave_service()
print(f"Configured: {transave.is_configured()}")
```

### 2. Test Loan Submission
```python
from conference_loan.models import ConferenceLoan

loan = ConferenceLoan.objects.get(reference_number='LOAN-20260409-0001')
result = loan.submit_to_transave()
print(f"Success: {result}")
print(f"Transave Loan ID: {loan.transave_loan_id}")
```

### 3. Test Status Check
```python
from conference_loan.transave_service import get_transave_service

transave = get_transave_service()
result = transave.check_loan_status(loan.transave_loan_id)
print(f"Status: {result}")
```

## Error Handling

The service includes comprehensive error handling:

1. **Configuration Errors**: Returns error if API keys are missing
2. **Network Errors**: Catches and logs request exceptions
3. **API Errors**: Handles non-200 status codes
4. **Validation Errors**: Validates data before sending

## Logging

All API interactions are logged:

```python
import logging
logger = logging.getLogger('conference_loan.transave')

# View logs
tail -f logs/transave.log
```

## Security Considerations

1. **API Keys**: Store in environment variables, never commit to git
2. **HTTPS**: Always use HTTPS for API calls
3. **Webhook Signatures**: Verify all webhook requests
4. **Rate Limiting**: Implement rate limiting on webhook endpoint
5. **Data Encryption**: Sensitive data should be encrypted in transit

## Support

For Transave API documentation and support:
- API Documentation: [Transave API Docs]
- Support Email: support@transave.com
- Developer Portal: [Transave Developer Portal]

## Next Steps

1. Get API credentials from Transave
2. Add credentials to `.env` file
3. Test API connection
4. Implement webhook handler
5. Test complete loan workflow
6. Deploy to production
7. Monitor API usage and errors
