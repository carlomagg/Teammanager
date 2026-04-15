# documents/services/youverify_service.py
"""
YouVerify API Integration Service
Provides automated verification for NIN, BVN, TIN, and CAC
"""

import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class YouVerifyService:
    """Service for YouVerify API integration"""
    
    def __init__(self):
        self.api_key = getattr(settings, 'YOUVERIFY_API_KEY', '')
        self.api_secret = getattr(settings, 'YOUVERIFY_API_SECRET', '')
        self.base_url = getattr(settings, 'YOUVERIFY_BASE_URL', 'https://api.youverify.co/v2')
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
    
    def verify_nin(self, nin, first_name, last_name, date_of_birth=None):
        """
        Verify NIN with YouVerify API
        
        Args:
            nin (str): 11-digit National Identification Number
            first_name (str): First name to verify
            last_name (str): Last name to verify
            date_of_birth (str): Date of birth in YYYY-MM-DD format (optional)
        
        Returns:
            dict: Verification result with status and data
        """
        try:
            url = f"{self.base_url}/identities/nin"
            payload = {
                "id": nin,
                "firstName": first_name,
                "lastName": last_name,
            }
            
            if date_of_birth:
                payload["dateOfBirth"] = date_of_birth
            
            logger.info(f"YouVerify NIN verification attempt for {nin}")
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"YouVerify NIN verification successful for {nin}")
                return {
                    'success': True,
                    'verified': data.get('verified', False),
                    'data': data,
                    'message': 'NIN verification successful'
                }
            else:
                logger.warning(f"YouVerify NIN verification failed for {nin}: {response.status_code}")
                return {
                    'success': False,
                    'verified': False,
                    'error': response.json().get('message', 'Verification failed'),
                    'status_code': response.status_code
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"YouVerify NIN verification error: {e}")
            return {
                'success': False,
                'verified': False,
                'error': str(e)
            }
    
    def verify_bvn(self, bvn, first_name, last_name, date_of_birth=None):
        """
        Verify BVN with YouVerify API
        
        Args:
            bvn (str): 11-digit Bank Verification Number
            first_name (str): First name to verify
            last_name (str): Last name to verify
            date_of_birth (str): Date of birth in YYYY-MM-DD format (optional)
        
        Returns:
            dict: Verification result with status and data
        """
        try:
            url = f"{self.base_url}/identities/bvn"
            payload = {
                "id": bvn,
                "firstName": first_name,
                "lastName": last_name,
            }
            
            if date_of_birth:
                payload["dateOfBirth"] = date_of_birth
            
            logger.info(f"YouVerify BVN verification attempt")
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"YouVerify BVN verification successful")
                return {
                    'success': True,
                    'verified': data.get('verified', False),
                    'data': data,
                    'message': 'BVN verification successful'
                }
            else:
                logger.warning(f"YouVerify BVN verification failed: {response.status_code}")
                return {
                    'success': False,
                    'verified': False,
                    'error': response.json().get('message', 'Verification failed'),
                    'status_code': response.status_code
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"YouVerify BVN verification error: {e}")
            return {
                'success': False,
                'verified': False,
                'error': str(e)
            }
    
    def verify_tin(self, tin, company_name):
        """
        Verify TIN with YouVerify API
        
        Args:
            tin (str): Tax Identification Number
            company_name (str): Company name to verify
        
        Returns:
            dict: Verification result with status and data
        """
        try:
            url = f"{self.base_url}/identities/tin"
            payload = {
                "id": tin,
                "companyName": company_name,
            }
            
            logger.info(f"YouVerify TIN verification attempt for {company_name}")
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"YouVerify TIN verification successful for {company_name}")
                return {
                    'success': True,
                    'verified': data.get('verified', False),
                    'data': data,
                    'message': 'TIN verification successful'
                }
            else:
                logger.warning(f"YouVerify TIN verification failed: {response.status_code}")
                return {
                    'success': False,
                    'verified': False,
                    'error': response.json().get('message', 'Verification failed'),
                    'status_code': response.status_code
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"YouVerify TIN verification error: {e}")
            return {
                'success': False,
                'verified': False,
                'error': str(e)
            }
    
    def verify_cac(self, rc_number, company_name):
        """
        Verify CAC registration with YouVerify API
        
        Args:
            rc_number (str): RC/BN number
            company_name (str): Company name to verify
        
        Returns:
            dict: Verification result with status and data
        """
        try:
            url = f"{self.base_url}/identities/cac"
            payload = {
                "rcNumber": rc_number,
                "companyName": company_name,
            }
            
            logger.info(f"YouVerify CAC verification attempt for {company_name}")
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"YouVerify CAC verification successful for {company_name}")
                return {
                    'success': True,
                    'verified': data.get('verified', False),
                    'data': data,
                    'message': 'CAC verification successful'
                }
            else:
                logger.warning(f"YouVerify CAC verification failed: {response.status_code}")
                return {
                    'success': False,
                    'verified': False,
                    'error': response.json().get('message', 'Verification failed'),
                    'status_code': response.status_code
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"YouVerify CAC verification error: {e}")
            return {
                'success': False,
                'verified': False,
                'error': str(e)
            }
    
    def check_api_status(self):
        """
        Check if YouVerify API is configured and accessible
        
        Returns:
            dict: Status information
        """
        if not self.api_key or not self.api_secret:
            return {
                'configured': False,
                'accessible': False,
                'message': 'YouVerify API credentials not configured in .env file'
            }
        
        try:
            # Try a simple API call to check connectivity
            # Note: Adjust this endpoint based on YouVerify's actual API
            url = f"{self.base_url}/status"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            return {
                'configured': True,
                'accessible': response.status_code == 200,
                'message': 'YouVerify API is ready' if response.status_code == 200 else 'API configured but not accessible'
            }
        except Exception as e:
            logger.error(f"YouVerify API status check error: {e}")
            return {
                'configured': True,
                'accessible': False,
                'message': f'YouVerify API credentials configured but not accessible: {str(e)}'
            }
    
    def is_configured(self):
        """Check if YouVerify is properly configured"""
        return bool(self.api_key and self.api_secret)
