"""
Reusable form widget configurations for CRM app.
"""
from django import forms


class CRMFormWidgets:
    """
    Centralized widget configurations for CRM forms.
    Ensures consistent styling across all forms.
    """
    
    @staticmethod
    def text_input(placeholder=''):
        """Standard text input widget"""
        return forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': placeholder
        })
    
    @staticmethod
    def email_input(placeholder='email@example.com'):
        """Standard email input widget"""
        return forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': placeholder
        })
    
    @staticmethod
    def phone_input(placeholder='+234-xxx-xxxx'):
        """Standard phone input widget"""
        return forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': placeholder
        })
    
    @staticmethod
    def url_input(placeholder='https://'):
        """Standard URL input widget"""
        return forms.URLInput(attrs={
            'class': 'form-control',
            'placeholder': placeholder
        })
    
    @staticmethod
    def textarea(rows=3, placeholder=''):
        """Standard textarea widget"""
        return forms.Textarea(attrs={
            'class': 'form-control',
            'rows': rows,
            'placeholder': placeholder
        })
    
    @staticmethod
    def select():
        """Standard select widget"""
        return forms.Select(attrs={'class': 'form-control'})
    
    @staticmethod
    def select2(placeholder=''):
        """Select2 enhanced select widget"""
        return forms.Select(attrs={
            'class': 'form-control select2',
            'data-placeholder': placeholder
        })
    
    @staticmethod
    def select2_multiple(placeholder=''):
        """Select2 enhanced multiple select widget"""
        return forms.SelectMultiple(attrs={
            'class': 'form-control select2',
            'data-placeholder': placeholder
        })
    
    @staticmethod
    def number_input(placeholder='0.00', step='0.01'):
        """Standard number input widget"""
        return forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': placeholder,
            'step': step
        })
    
    @staticmethod
    def date_input():
        """Standard date input widget"""
        return forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    
    @staticmethod
    def datetime_input():
        """Standard datetime input widget"""
        return forms.DateTimeInput(attrs={
            'class': 'form-control',
            'type': 'datetime-local'
        })
    
    @staticmethod
    def checkbox():
        """Standard checkbox widget"""
        return forms.CheckboxInput(attrs={'class': 'form-check-input'})
