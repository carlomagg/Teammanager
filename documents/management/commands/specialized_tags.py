from django.core.management.base import BaseCommand
from documents.models import VacancyTag

class Command(BaseCommand):
    help = 'Import specialized tags for niche industries and emerging fields'
    
    def handle(self, *args, **options):
        specialized_tags = {
            'emerging_tech': [
                'quantum-computing', 'metaverse', 'web3', 'nft', 'dao', 'defi',
                'generative-ai', 'large-language-models', 'computer-vision',
                'autonomous-vehicles', 'drone-technology', 'smart-cities',
                'digital-twin', 'edge-computing', '5g-technology', '6g-research',
            ],
            'sustainability': [
                'esg', 'carbon-neutral', 'net-zero', 'circular-economy',
                'sustainable-development', 'green-building', 'renewable-energy',
                'carbon-capture', 'climate-tech', 'environmental-social-governance',
                'sustainable-investing', 'impact-investing',
            ],
            'healthcare_specialties': [
                'telemedicine', 'digital-health', 'health-informatics',
                'precision-medicine', 'genomic-medicine', 'personalized-medicine',
                'medical-ai', 'healthcare-analytics', 'patient-engagement',
                'value-based-care', 'population-health',
            ],
            'finance_specialties': [
                'cryptocurrency', 'digital-assets', 'algorithmic-trading',
                'quantitative-analysis', 'risk-modeling', 'financial-technology',
                'regtech', 'payments', 'digital-banking', 'wealth-tech',
            ],
            'creative_industries': [
                'motion-graphics', '3d-animation', 'vfx', 'game-design',
                'ux-research', 'service-design', 'design-thinking',
                'content-strategy', 'brand-strategy', 'creative-technology',
            ],
            'academic_research': [
                'postdoc', 'research-fellow', 'principal-investigator',
                'lab-manager', 'research-assistant', 'grant-writing',
                'peer-review', 'academic-publishing', 'qualitative-research',
                'quantitative-research', 'mixed-methods',
            ],
        }
        
        created_count = 0
        for category, tags in specialized_tags.items():
            for tag_name in tags:
                tag, created = VacancyTag.objects.get_or_create(
                    name=tag_name.lower().strip()
                )
                if created:
                    created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully imported {created_count} specialized tags')
        )