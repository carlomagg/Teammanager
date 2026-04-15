from django.core.management.base import BaseCommand
from documents.models import VacancySkill

class Command(BaseCommand):
    help = 'Import specialized skills for specific industries'
    
    def handle(self, *args, **options):
        industry_skills = {
            'aviation': [
                'Aircraft Maintenance', 'Flight Operations', 'Air Traffic Control',
                'Avionics', 'Pilot Certification', 'Aircraft Dispatch', 'Flight Planning',
                'Aviation Safety', 'FAA Regulations', 'Aircraft Systems',
            ],
            'maritime': [
                'Marine Engineering', 'Navigation', 'Port Operations', 'Maritime Law',
                'Vessel Operations', 'Ship Maintenance', 'Marine Safety', 'Customs Clearance',
            ],
            'gaming': [
                'Game Development', 'Unity', 'Unreal Engine', 'Game Design', 'Level Design',
                'Character Animation', 'Game Programming', 'VR Development', 'AR Development',
                'Game Testing', 'Game Production', 'Shader Programming',
            ],
            'blockchain': [
                'Smart Contracts', 'Solidity', 'Web3.js', 'Ethereum', 'Cryptocurrency',
                'DeFi', 'NFT Development', 'Blockchain Architecture', 'Consensus Algorithms',
                'Tokenomics', 'Cryptography', 'Distributed Systems',
            ],
            'space_tech': [
                'Aerospace Engineering', 'Satellite Systems', 'Rocket Propulsion',
                'Spacecraft Design', 'Orbital Mechanics', 'Remote Sensing', 'GNSS',
                'Space Mission Planning', 'Astrodynamics',
            ],
            'biotech': [
                'CRISPR', 'Gene Editing', 'Bioinformatics', 'Genomic Sequencing',
                'Cell Culture', 'Molecular Biology', 'Protein Purification',
                'Clinical Trial Management', 'Regulatory Science',
            ],
        }
        
        created_count = 0
        for industry, skills in industry_skills.items():
            for skill_name in skills:
                skill, created = VacancySkill.objects.get_or_create(
                    name=skill_name.lower().strip()
                )
                if created:
                    created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully imported {created_count} industry-specific skills')
        )