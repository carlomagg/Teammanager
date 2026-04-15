from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from decimal import Decimal
from .models import Opportunity, PipelineStage
from documents.models import Contact


@receiver(pre_save, sender=Opportunity)
def auto_calculate_deal_size(sender, instance, **kwargs):
    """
    Automatically calculate and set deal_size based on estimated_amount.
    Ranges:
    - 0 to ₦1,000,000 = Small
    - ₦1,000,000 to ₦10,000,000 = Medium
    - ₦10,000,000 and above = Large
    """
    if instance.estimated_amount is not None:
        amount = Decimal(str(instance.estimated_amount))
        
        if amount < Decimal('1000000'):
            instance.deal_size = 'Small'
        elif amount < Decimal('10000000'):
            instance.deal_size = 'Medium'
        else:
            instance.deal_size = 'Large'
    else:
        instance.deal_size = ''


@receiver(pre_save, sender=Opportunity)
def auto_update_category_on_closed_won(sender, instance, **kwargs):
    """
    When a Deal moves to 'Closed Won' stage, automatically:
    1. Change category from 'Deal' to 'Customer'
    2. Set stage to first Customer stage (e.g., 'Happy Customer')
    
    This only triggers on updates, not new records.
    """
    if instance.pk:
        try:
            old_instance = Opportunity.objects.get(pk=instance.pk)
            
            # Check if stage changed to Closed Won
            if (instance.stage and 
                instance.stage != old_instance.stage and 
                instance.stage.name == 'Closed Won' and 
                instance.category == 'Deal'):
                
                # Change category to Customer
                instance.category = 'Customer'
                
                # Set stage to first Customer stage
                first_customer_stage = PipelineStage.objects.filter(
                    tenant=instance.tenant,
                    category='Customer'
                ).order_by('order').first()
                
                if first_customer_stage:
                    instance.stage = first_customer_stage
                    
        except Opportunity.DoesNotExist:
            pass


@receiver(post_save, sender=Opportunity)
def auto_save_contacts_from_opportunity(sender, instance, created, **kwargs):
    """
    Automatically create or update Contact records from opportunity contact fields.
    This prevents data duplication by saving contact, partner, contractor, and referrer
    information to the Contact model.
    """
    contacts_to_create = []
    
    # 1. Main Contact Person
    if instance.contact_email and not instance.contact:
        contact, created = Contact.objects.get_or_create(
            email=instance.contact_email,
            tenant=instance.tenant,
            defaults={
                'name': f"{instance.contact_first_name} {instance.contact_last_name}".strip() or 'Unknown',
                'title': instance.contact_title,
                'phone': instance.contact_phone,
                'organization': instance.company_name,
                'created_by': instance.created_by,
            }
        )
        if not created:
            # Update existing contact with latest info
            contact.name = f"{instance.contact_first_name} {instance.contact_last_name}".strip() or contact.name
            contact.title = instance.contact_title or contact.title
            contact.phone = instance.contact_phone or contact.phone
            contact.organization = instance.company_name or contact.organization
            contact.save()
        
        # Link contact to opportunity
        instance.contact = contact
        Opportunity.objects.filter(pk=instance.pk).update(contact=contact)
    
    # 2. Partner Contact
    if instance.partner_email and not instance.partner_contact:
        partner, created = Contact.objects.get_or_create(
            email=instance.partner_email,
            tenant=instance.tenant,
            defaults={
                'name': instance.partner_contact_name or instance.partner_org_name or 'Unknown Partner',
                'phone': instance.partner_phone,
                'organization': instance.partner_org_name,
                'created_by': instance.created_by,
            }
        )
        if not created:
            partner.phone = instance.partner_phone or partner.phone
            partner.organization = instance.partner_org_name or partner.organization
            partner.save()
        
        instance.partner_contact = partner
        Opportunity.objects.filter(pk=instance.pk).update(partner_contact=partner)
    
    # 3. Contractor Contact
    if instance.contractor_email and not instance.contractor_contact:
        contractor, created = Contact.objects.get_or_create(
            email=instance.contractor_email,
            tenant=instance.tenant,
            defaults={
                'name': instance.contractor_contact_name or instance.contractor_org_name or 'Unknown Contractor',
                'phone': instance.contractor_phone,
                'organization': instance.contractor_org_name,
                'created_by': instance.created_by,
            }
        )
        if not created:
            contractor.phone = instance.contractor_phone or contractor.phone
            contractor.organization = instance.contractor_org_name or contractor.organization
            contractor.save()
        
        instance.contractor_contact = contractor
        Opportunity.objects.filter(pk=instance.pk).update(contractor_contact=contractor)
    
    # 4. Referrer Contact (if source is Referral)
    if instance.source == 'Referral' and instance.referrer_email:
        referrer, created = Contact.objects.get_or_create(
            email=instance.referrer_email,
            tenant=instance.tenant,
            defaults={
                'name': instance.referrer_name or 'Unknown Referrer',
                'phone': instance.referrer_phone,
                'created_by': instance.created_by,
            }
        )
        if not created:
            referrer.name = instance.referrer_name or referrer.name
            referrer.phone = instance.referrer_phone or referrer.phone
            referrer.save()
