from django import forms
from django.core.exceptions import ValidationError
from .models import Opportunity, Product, PipelineStage, Activity
from documents.models import Contact
from .validators import validate_phone_number
from .form_widgets import CRMFormWidgets


class ProductForm(forms.ModelForm):
    """Form for creating and updating products"""
    
    class Meta:
        model = Product
        fields = [
            'name', 'description', 'category', 'unit_price', 'is_active'
        ]
        widgets = {
            'name': CRMFormWidgets.text_input('Product name'),
            'description': CRMFormWidgets.textarea(3, 'Product description'),
            'category': CRMFormWidgets.select(),
            'unit_price': CRMFormWidgets.number_input('0.00', '0.01'),
            'is_active': CRMFormWidgets.checkbox(),
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)


class OpportunityForm(forms.ModelForm):
    """
    Comprehensive form for creating and updating opportunities.
    Handles all sections: company info, contact, deal classification, products, etc.
    """
    
    class Meta:
        model = Opportunity
        fields = [
            'title', 'description',
            'company_name', 'company_type', 'company_size', 'company_website', 'industry',
            'country', 'city', 'address',
            'contact', 'contact_first_name', 'contact_last_name', 'contact_title', 
            'contact_email', 'contact_phone',
            'category', 'deal_type',
            'products', 'product_details',
            'delivery_method',
            'partner_contact', 'partner_org_name', 'partner_contact_name', 
            'partner_phone', 'partner_email', 'partner_address',
            'contractor_contact', 'contractor_org_name', 'contractor_contact_name',
            'contractor_phone', 'contractor_email', 'contractor_address',
            'estimated_amount', 'actual_amount',
            'recurring_revenue',
            'expected_close_date', 'contract_expiry_date',
            'source', 'referrer_name', 'referrer_phone', 'referrer_email', 'referrer_address',
            'is_competitive', 'competitor_names',
            'assigned_to', 'stage',
        ]
        widgets = {
            'title': CRMFormWidgets.text_input('Opportunity title'),
            'description': CRMFormWidgets.textarea(3, 'Brief description'),
            
            'company_name': CRMFormWidgets.text_input('Company name'),
            'company_type': CRMFormWidgets.select(),
            'company_size': CRMFormWidgets.select(),
            'company_website': CRMFormWidgets.url_input(),
            'industry': CRMFormWidgets.select(),
            
            'country': CRMFormWidgets.select(),
            'city': CRMFormWidgets.text_input('City'),
            'address': CRMFormWidgets.textarea(2, 'Full address'),
            
            'contact': CRMFormWidgets.select2('Select existing contact'),
            'contact_first_name': CRMFormWidgets.text_input('First name'),
            'contact_last_name': CRMFormWidgets.text_input('Last name'),
            'contact_title': CRMFormWidgets.text_input('e.g., CTO, Manager'),
            'contact_email': CRMFormWidgets.email_input(),
            'contact_phone': CRMFormWidgets.phone_input(),
            
            'category': CRMFormWidgets.select(),
            'deal_type': CRMFormWidgets.select(),
            
            'products': CRMFormWidgets.select2_multiple('Select products'),
            'product_details': CRMFormWidgets.textarea(3, 'Explanation of services to be delivered'),
            
            'delivery_method': CRMFormWidgets.select(),
            
            'partner_contact': CRMFormWidgets.select2('Select partner contact'),
            'partner_org_name': CRMFormWidgets.text_input('Partner organization name'),
            'partner_contact_name': CRMFormWidgets.text_input('Partner contact name'),
            'partner_phone': CRMFormWidgets.phone_input(),
            'partner_email': CRMFormWidgets.email_input('partner@example.com'),
            'partner_address': CRMFormWidgets.textarea(2, 'Partner address'),
            
            'contractor_contact': CRMFormWidgets.select2('Select contractor contact'),
            'contractor_org_name': CRMFormWidgets.text_input('Contractor organization name'),
            'contractor_contact_name': CRMFormWidgets.text_input('Contractor contact name'),
            'contractor_phone': CRMFormWidgets.phone_input(),
            'contractor_email': CRMFormWidgets.email_input('contractor@example.com'),
            'contractor_address': CRMFormWidgets.textarea(2, 'Contractor address'),
            
            'estimated_amount': CRMFormWidgets.number_input('0.00', '0.01'),
            'actual_amount': CRMFormWidgets.number_input('0.00', '0.01'),
            
            'recurring_revenue': CRMFormWidgets.select(),
            
            'expected_close_date': CRMFormWidgets.date_input(),
            'contract_expiry_date': CRMFormWidgets.date_input(),
            
            'source': CRMFormWidgets.select(),
            'referrer_name': CRMFormWidgets.text_input('Referrer name'),
            'referrer_phone': CRMFormWidgets.phone_input(),
            'referrer_email': CRMFormWidgets.email_input('referrer@example.com'),
            'referrer_address': CRMFormWidgets.textarea(2, 'Referrer address'),
            
            'is_competitive': CRMFormWidgets.checkbox(),
            'competitor_names': CRMFormWidgets.textarea(2, 'List competitor names, separated by commas'),
            
            'assigned_to': CRMFormWidgets.select2('Assign to user'),
            'stage': forms.Select(attrs={'class': 'form-control', 'id': 'id_stage'}),
        }
        labels = {
            'deal_type': 'Opportunity Type',
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request:
            tenant = self.request.effective_tenant
            user = self.request.effective_user
            
            # Filter contacts by tenant
            self.fields['contact'].queryset = Contact.objects.filter(
                tenant=tenant
            ).order_by('name')
            
            # Filter partner contacts by tenant
            self.fields['partner_contact'].queryset = Contact.objects.filter(
                tenant=tenant
            ).order_by('name')
            
            # Filter contractor contacts by tenant
            self.fields['contractor_contact'].queryset = Contact.objects.filter(
                tenant=tenant
            ).order_by('name')
            
            # Filter products by tenant
            self.fields['products'].queryset = Product.objects.get_assigned_or_all(
                user, tenant
            ).filter(is_active=True).order_by('name')
            
            # Filter stages by tenant and category
            if self.instance and self.instance.pk and self.instance.category:
                self.fields['stage'].queryset = PipelineStage.objects.filter(
                    tenant=tenant,
                    category=self.instance.category
                ).order_by('order')
            else:
                # For new opportunities, show all stages
                self.fields['stage'].queryset = PipelineStage.objects.filter(
                    tenant=tenant
                ).order_by('category', 'order')
            
            # Filter assigned_to by tenant users
            if tenant:
                from documents.models import CustomUser
                self.fields['assigned_to'].queryset = CustomUser.objects.filter(
                    tenant=tenant
                ).order_by('first_name', 'last_name')
            else:
                from documents.models import CustomUser
                self.fields['assigned_to'].queryset = CustomUser.objects.filter(
                    id=user.id
                )
    
    def clean(self):
        cleaned_data = super().clean()
        delivery_method = cleaned_data.get('delivery_method')
        partner_contact = cleaned_data.get('partner_contact')
        partner_org_name = cleaned_data.get('partner_org_name')
        partner_contact_name = cleaned_data.get('partner_contact_name')
        partner_email = cleaned_data.get('partner_email')
        partner_phone = cleaned_data.get('partner_phone')
        
        # Validate partner information when delivery method is Through Partner
        if delivery_method == 'Through Partner':
            if not partner_contact and not (
                partner_org_name and partner_contact_name and 
                partner_email and partner_phone
            ):
                raise ValidationError(
                    "Partner information is required when delivery method is 'Through Partner'. "
                    "Either select an existing partner contact or fill in all partner details."
                )
        
        return cleaned_data
    
    def _clean_phone_field(self, field_name):
        """
        Reusable phone validation method.
        DRY principle - single source of truth for phone validation.
        """
        phone = self.cleaned_data.get(field_name)
        if phone:
            return validate_phone_number(phone)
        return phone
    
    def clean_contact_phone(self):
        return self._clean_phone_field('contact_phone')
    
    def clean_partner_phone(self):
        return self._clean_phone_field('partner_phone')
    
    def clean_referrer_phone(self):
        return self._clean_phone_field('referrer_phone')
    
    def clean_contractor_phone(self):
        return self._clean_phone_field('contractor_phone')


class ActivityForm(forms.ModelForm):
    """Form for creating and updating activities"""
    
    class Meta:
        model = Activity
        fields = [
            'activity_type', 'subject', 'description', 
            'due_date', 'assigned_to', 'completed'
        ]
        widgets = {
            'activity_type': CRMFormWidgets.select(),
            'subject': CRMFormWidgets.text_input('Activity subject'),
            'description': CRMFormWidgets.textarea(3, 'Activity description'),
            'due_date': CRMFormWidgets.datetime_input(),
            'assigned_to': CRMFormWidgets.select2('Assign to user'),
            'completed': CRMFormWidgets.checkbox(),
        }
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if self.request:
            tenant = self.request.effective_tenant
            user = self.request.effective_user
            
            # Filter assigned_to by tenant users
            if tenant:
                from documents.models import CustomUser
                self.fields['assigned_to'].queryset = CustomUser.objects.filter(
                    tenant=tenant
                ).order_by('first_name', 'last_name')
            else:
                from documents.models import CustomUser
                self.fields['assigned_to'].queryset = CustomUser.objects.filter(
                    id=user.id
                )
