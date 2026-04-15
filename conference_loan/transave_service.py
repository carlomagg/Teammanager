"""
Transave API Service for Conference Loan Integration

This service handles all interactions with the Transave API for loan processing.
"""

import requests
from django.conf import settings
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class TransaveService:
    """Service class for Transave API integration"""
    
    def __init__(self):
        self.api_key = settings.TRANSAVE_API_KEY
        self.api_url = settings.TRANSAVE_API_URL
        self.secret_key = settings.TRANSAVE_SECRET_KEY
        self.enabled = settings.TRANSAVE_ENABLED
    
    def is_configured(self):
        """Check if Transave API is properly configured"""
        return bool(self.api_key and self.api_url and self.secret_key)
    
    def get_headers(self):
        """Get API request headers"""
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'X-Secret-Key': self.secret_key
        }
    
    def submit_loan_application(self, loan):
        """
        Submit a loan application to Transave
        
        Args:
            loan: ConferenceLoan instance
            
        Returns:
            dict: API response data
        """
        if not self.is_configured():
            logger.error("Transave API is not configured")
            return {
                'success': False,
                'error': 'Transave API is not configured'
            }
        
        # Prepare loan data
        payload = {
            'reference': loan.reference_number,
            'applicant': {
                'name': loan.applicant.get_full_name() or loan.applicant.username,
                'email': loan.applicant.email,
                'phone': getattr(loan.applicant, 'phone_number', ''),
            },
            'company': {
                'name': loan.tenant.name,
                'registration_number': getattr(loan.tenant.company_profile, 'reg_number', ''),
            },
            'loan': {
                'amount': float(loan.amount),
                'currency': loan.currency,
                'reason': loan.reason,
                'expected_date': loan.expected_date.isoformat(),
            },
            'conference': {
                'title': loan.conference.title,
                'start_date': loan.conference.start_date.isoformat(),
                'end_date': loan.conference.end_date.isoformat(),
                'venue': loan.conference.venue,
                'description': loan.conference_description,
                'expected_revenue': float(loan.expected_revenue) if loan.expected_revenue else None,
                'expected_expenses': float(loan.expected_expenses) if loan.expected_expenses else None,
            },
            'guarantor': {
                'name': loan.guarantor_name,
                'phone': loan.guarantor_phone,
                'email': loan.guarantor_email,
                'address': loan.guarantor_address,
                'relationship': loan.guarantor_relationship,
                'occupation': loan.guarantor_occupation,
            },
            'kyc_verified': loan.kyc_verified,
        }
        
        try:
            # TODO: Replace with actual Transave API endpoint
            response = requests.post(
                f"{self.api_url}/loans/submit",
                headers=self.get_headers(),
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200 or response.status_code == 201:
                data = response.json()
                logger.info(f"Loan {loan.reference_number} submitted to Transave successfully")
                return {
                    'success': True,
                    'loan_id': data.get('loan_id'),
                    'data': data
                }
            else:
                logger.error(f"Transave API error: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f"API returned status {response.status_code}",
                    'details': response.text
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Transave API request failed: {str(e)}")
            return {
                'success': False,
                'error': f"Request failed: {str(e)}"
            }
    
    def check_loan_status(self, transave_loan_id):
        """
        Check the status of a loan with Transave
        
        Args:
            transave_loan_id: Loan ID from Transave
            
        Returns:
            dict: Loan status data
        """
        if not self.is_configured():
            return {
                'success': False,
                'error': 'Transave API is not configured'
            }
        
        try:
            # TODO: Replace with actual Transave API endpoint
            response = requests.get(
                f"{self.api_url}/loans/{transave_loan_id}/status",
                headers=self.get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'status': data.get('status'),
                    'data': data
                }
            else:
                return {
                    'success': False,
                    'error': f"API returned status {response.status_code}"
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Transave status check failed: {str(e)}")
            return {
                'success': False,
                'error': f"Request failed: {str(e)}"
            }
    
    def process_disbursement(self, loan, bank_details):
        """
        Process loan disbursement through Transave
        
        Args:
            loan: ConferenceLoan instance
            bank_details: Dict with bank account information
            
        Returns:
            dict: Disbursement response
        """
        if not self.is_configured():
            return {
                'success': False,
                'error': 'Transave API is not configured'
            }
        
        payload = {
            'loan_id': loan.transave_loan_id,
            'amount': float(loan.approved_amount),
            'currency': loan.currency,
            'bank_details': bank_details
        }
        
        try:
            # TODO: Replace with actual Transave API endpoint
            response = requests.post(
                f"{self.api_url}/loans/{loan.transave_loan_id}/disburse",
                headers=self.get_headers(),
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'reference': data.get('reference'),
                    'data': data
                }
            else:
                return {
                    'success': False,
                    'error': f"API returned status {response.status_code}"
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Transave disbursement failed: {str(e)}")
            return {
                'success': False,
                'error': f"Request failed: {str(e)}"
            }
    
    def record_repayment(self, loan, amount, payment_reference):
        """
        Record a loan repayment with Transave
        
        Args:
            loan: ConferenceLoan instance
            amount: Repayment amount
            payment_reference: Payment transaction reference
            
        Returns:
            dict: Repayment response
        """
        if not self.is_configured():
            return {
                'success': False,
                'error': 'Transave API is not configured'
            }
        
        payload = {
            'loan_id': loan.transave_loan_id,
            'amount': float(amount),
            'currency': loan.currency,
            'reference': payment_reference
        }
        
        try:
            # TODO: Replace with actual Transave API endpoint
            response = requests.post(
                f"{self.api_url}/loans/{loan.transave_loan_id}/repayment",
                headers=self.get_headers(),
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'payment_id': data.get('payment_id'),
                    'data': data
                }
            else:
                return {
                    'success': False,
                    'error': f"API returned status {response.status_code}"
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Transave repayment recording failed: {str(e)}")
            return {
                'success': False,
                'error': f"Request failed: {str(e)}"
            }
    
    def get_repayment_schedule(self, loan):
        """
        Get the repayment schedule for a loan
        
        Args:
            loan: ConferenceLoan instance
            
        Returns:
            dict: Repayment schedule data
        """
        if not self.is_configured():
            return {
                'success': False,
                'error': 'Transave API is not configured'
            }
        
        try:
            # TODO: Replace with actual Transave API endpoint
            response = requests.get(
                f"{self.api_url}/loans/{loan.transave_loan_id}/schedule",
                headers=self.get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'schedule': data.get('schedule', []),
                    'data': data
                }
            else:
                return {
                    'success': False,
                    'error': f"API returned status {response.status_code}"
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Transave schedule fetch failed: {str(e)}")
            return {
                'success': False,
                'error': f"Request failed: {str(e)}"
            }


# Convenience function for easy import
def get_transave_service():
    """Get an instance of TransaveService"""
    return TransaveService()
