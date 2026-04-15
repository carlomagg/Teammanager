from django.core.management.base import BaseCommand
from documents.models import VacancyTag

class Command(BaseCommand):
    help = 'Import comprehensive vacancy tags list across all categories'
    
    def handle(self, *args, **options):
        comprehensive_tags = self.get_comprehensive_tags_list()
        
        created_count = 0
        for tag_name in comprehensive_tags:
            tag, created = VacancyTag.objects.get_or_create(
                name=tag_name.lower().strip()
            )
            if created:
                created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully imported {created_count} new tags. '
                f'Total tags in database: {VacancyTag.objects.count()}'
            )
        )
    
    def get_comprehensive_tags_list(self):
        return [
            # ==================== EMPLOYMENT TYPE ====================
            'full-time', 'part-time', 'contract', 'freelance', 'internship', 'temporary',
            'seasonal', 'volunteer', 'permanent', 'fixed-term', 'zero-hours', 'casual',
            'gig-work', 'consultant', 'agency', 'subcontractor',
            
            # ==================== WORK ARRANGEMENT ====================
            'remote', 'onsite', 'hybrid', 'work-from-home', 'flexible', 'office-based',
            'field-work', 'travel-required', 'no-travel', 'shift-work', 'night-shift',
            'weekend-work', 'overtime', 'compressed-hours', 'job-share', 'telecommute',
            'mobile-work', 'remote-first', 'office-optional',
            
            # ==================== EXPERIENCE LEVEL ====================
            'entry-level', 'junior', 'mid-level', 'senior', 'lead', 'principal', 'executive',
            'director', 'manager', 'vp', 'c-level', 'ceo', 'cto', 'cfo', 'coo', 'cmo',
            'associate', 'assistant', 'trainee', 'apprentice', 'graduate', 'fresh-graduate',
            'student', 'experienced', 'expert', 'specialist',
            
            # ==================== INDUSTRIES ====================
            # Technology & IT
            'technology', 'it', 'software', 'hardware', 'saas', 'paas', 'iaas', 'fintech',
            'healthtech', 'edtech', 'agtech', 'legaltech', 'insurtech', 'proptech', 'ecommerce',
            'gaming', 'mobile-apps', 'web-development', 'cloud-computing', 'cybersecurity',
            'artificial-intelligence', 'machine-learning', 'data-science', 'blockchain',
            'iot', 'vr-ar', 'robotics', 'automation',
            
            # Business & Professional Services
            'consulting', 'professional-services', 'accounting', 'legal', 'recruitment',
            'hr', 'marketing', 'advertising', 'pr', 'market-research', 'business-services',
            'management-consulting', 'financial-services', 'banking', 'insurance',
            'investment', 'venture-capital', 'private-equity',
            
            # Healthcare & Life Sciences
            'healthcare', 'medical', 'pharmaceutical', 'biotech', 'life-sciences',
            'hospital', 'clinic', 'dental', 'mental-health', 'eldercare', 'home-healthcare',
            'medical-devices', 'clinical-research', 'health-insurance', 'telehealth',
            'wellness', 'fitness', 'nutrition',
            
            # Manufacturing & Engineering
            'manufacturing', 'engineering', 'industrial', 'automotive', 'aerospace',
            'defense', 'construction', 'civil-engineering', 'mechanical-engineering',
            'electrical-engineering', 'chemical-engineering', 'industrial-design',
            'supply-chain', 'logistics', 'procurement', 'quality-control',
            
            # Retail & Consumer Goods
            'retail', 'ecommerce', 'consumer-goods', 'fashion', 'apparel', 'beauty',
            'cosmetics', 'furniture', 'home-goods', 'grocery', 'food-beverage',
            'restaurant', 'hospitality', 'tourism', 'travel',
            
            # Education & Training
            'education', 'edtech', 'higher-education', 'k-12', 'online-education',
            'corporate-training', 'vocational', 'tutoring', 'academic', 'research',
            'library-sciences', 'educational-technology',
            
            # Government & Public Sector
            'government', 'public-sector', 'non-profit', 'ngo', 'charity', 'public-policy',
            'international-development', 'civil-service', 'military', 'defense',
            'intelligence', 'law-enforcement', 'security',
            
            # Media & Entertainment
            'media', 'entertainment', 'journalism', 'publishing', 'broadcasting',
            'film-tv', 'music', 'gaming', 'esports', 'social-media', 'content-creation',
            'digital-media', 'animation', 'graphic-design',
            
            # Real Estate & Property
            'real-estate', 'property', 'commercial-real-estate', 'residential-real-estate',
            'property-management', 'construction', 'architecture', 'interior-design',
            'facilities-management', 'urban-planning',
            
            # Energy & Utilities
            'energy', 'utilities', 'renewable-energy', 'solar', 'wind', 'oil-gas',
            'nuclear', 'electrical', 'water', 'waste-management', 'environmental',
            'sustainability', 'clean-tech',
            
            # Transportation & Logistics
            'transportation', 'logistics', 'shipping', 'freight', 'supply-chain',
            'aviation', 'maritime', 'rail', 'trucking', 'delivery', 'warehousing',
            'inventory-management',
            
            # Agriculture & Natural Resources
            'agriculture', 'farming', 'agtech', 'forestry', 'fishing', 'mining',
            'environmental', 'conservation', 'sustainability',
            
            # ==================== JOB FUNCTIONS ====================
            # Technology Roles
            'software-engineer', 'web-developer', 'mobile-developer', 'devops-engineer',
            'data-scientist', 'machine-learning-engineer', 'ai-engineer', 'cloud-engineer',
            'systems-administrator', 'network-engineer', 'security-analyst', 'qa-engineer',
            'database-administrator', 'technical-support', 'help-desk', 'it-manager',
            'cto', 'product-manager-tech', 'ux-ui-designer',
            
            # Business & Management Roles
            'project-manager', 'product-manager', 'program-manager', 'operations-manager',
            'business-analyst', 'strategic-planner', 'management-consultant', 'ceo',
            'coo', 'cfo', 'director', 'vp', 'general-manager',
            
            # Sales & Marketing Roles
            'sales-representative', 'account-executive', 'business-development',
            'sales-manager', 'account-manager', 'customer-success', 'marketing-manager',
            'digital-marketer', 'content-marketer', 'seo-specialist', 'social-media-manager',
            'brand-manager', 'product-marketer', 'market-researcher', 'cmo',
            
            # Finance & Accounting Roles
            'accountant', 'financial-analyst', 'controller', 'cpa', 'auditor',
            'tax-specialist', 'bookkeeper', 'financial-planner', 'investment-analyst',
            'risk-analyst', 'treasury-analyst', 'cfo',
            
            # HR & Recruitment Roles
            'hr-manager', 'recruiter', 'talent-acquisition', 'hr-business-partner',
            'compensation-analyst', 'training-specialist', 'recruitment-coordinator',
            'hr-generalist', 'diversity-inclusion',
            
            # Creative & Design Roles
            'graphic-designer', 'ux-designer', 'ui-designer', 'art-director',
            'creative-director', 'video-editor', 'animator', 'photographer',
            'copywriter', 'content-writer', 'technical-writer',
            
            # Operations & Supply Chain
            'operations-manager', 'supply-chain-manager', 'logistics-coordinator',
            'inventory-manager', 'procurement-specialist', 'quality-assurance',
            'production-supervisor', 'facilities-manager',
            
            # Customer Service Roles
            'customer-service', 'technical-support', 'call-center', 'client-services',
            'customer-success', 'account-coordinator', 'service-desk',
            
            # Legal & Compliance
            'lawyer', 'attorney', 'paralegal', 'legal-assistant', 'compliance-officer',
            'risk-manager', 'regulatory-affairs', 'corporate-counsel',
            
            # Healthcare Roles
            'doctor', 'physician', 'nurse', 'surgeon', 'therapist', 'pharmacist',
            'medical-assistant', 'healthcare-administrator', 'medical-researcher',
            
            # Education Roles
            'teacher', 'professor', 'instructor', 'tutor', 'educator', 'academic-advisor',
            'curriculum-developer', 'instructional-designer',
            
            # ==================== SALARY & COMPENSATION ====================
            'competitive-salary', 'performance-bonus', 'commission', 'profit-sharing',
            'stock-options', 'equity', 'signing-bonus', 'relocation-bonus',
            'salary-negotiable', 'above-market', 'high-earning-potential',
            'uncapped-commission', 'revenue-sharing',
            
            # ==================== BENEFITS & PERKS ====================
            # Health & Wellness
            'health-insurance', 'dental-insurance', 'vision-insurance', 'life-insurance',
            'disability-insurance', 'mental-health-support', 'wellness-program',
            'gym-membership', 'fitness-subsidy', 'health-savings-account',
            
            # Retirement & Financial
            '401k', 'pension', 'retirement-plan', '401k-matching', 'stock-options',
            'equity', 'profit-sharing', 'financial-planning', 'student-loan-assistance',
            
            # Time Off & Flexibility
            'paid-time-off', 'unlimited-pto', 'flexible-hours', 'compressed-workweek',
            'summer-hours', 'paid-holidays', 'sick-leave', 'parental-leave',
            'maternity-leave', 'paternity-leave', 'adoption-leave', 'sabbatical',
            'bereavement-leave',
            
            # Work-Life Balance
            'work-from-home', 'remote-work', 'flexible-schedule', 'work-life-balance',
            'mental-health-days', 'personal-days', 'caregiver-support',
            
            # Professional Development
            'training', 'professional-development', 'tuition-reimbursement',
            'certification-support', 'conference-budget', 'skill-development',
            'mentorship-program', 'leadership-training', 'career-advancement',
            
            # Workplace Amenities
            'free-lunch', 'snacks', 'coffee', 'company-events', 'team-outings',
            'onsite-gym', 'game-room', 'nap-room', 'pet-friendly', 'onsite-childcare',
            'commuter-benefits', 'parking', 'company-car',
            
            # ==================== COMPANY CULTURE ====================
            'startup-culture', 'corporate', 'fast-paced', 'collaborative', 'innovative',
            'creative', 'inclusive', 'diverse', 'team-oriented', 'autonomous',
            'entrepreneurial', 'structured', 'flat-hierarchy', 'meritocratic',
            'social-impact', 'mission-driven', 'customer-focused', 'data-driven',
            'agile', 'growth-mindset', 'work-hard-play-hard',
            
            # ==================== URGENCY & STATUS ====================
            'urgent', 'immediate', 'featured', 'hot-job', 'new', 'closing-soon',
            'multiple-openings', 'high-priority', 'critical-role', 'key-position',
            'recently-posted', 'ending-today', 'ending-this-week',
            
            # ==================== SPECIAL PROGRAMS ====================
            'visa-sponsorship', 'relocation-assistance', 'new-grad', 'fresh-graduate',
            'career-change', 'return-to-work', 'veteran-friendly', 'military-friendly',
            'diversity-inclusion', 'equal-opportunity', 'inclusive-workplace',
            'apprenticeship-program', 'graduate-program', 'leadership-program',
            'rotational-program', 'internship-to-hire',
            
            # ==================== EDUCATION REQUIREMENTS ====================
            'high-school-diploma', 'associates-degree', 'bachelors-degree',
            'masters-degree', 'phd', 'md', 'jd', 'mba', 'no-degree-required',
            'degree-preferred', 'equivalent-experience', 'certification-required',
            'license-required',
            
            # ==================== SECURITY CLEARANCE ====================
            'security-clearance', 'public-trust', 'secret-clearance', 'top-secret',
            'ts-sci', 'background-check', 'drug-test', 'credit-check',
            
            # ==================== TECHNICAL ENVIRONMENT ====================
            'macos', 'windows', 'linux', 'unix', 'aws', 'azure', 'google-cloud',
            'microsoft-stack', 'apple-ecosystem', 'open-source', 'proprietary',
            'enterprise-software', 'legacy-systems', 'modern-stack',
            
            # ==================== TEAM SIZE & STRUCTURE ====================
            'small-team', 'large-team', 'cross-functional', 'autonomous-team',
            'individual-contributor', 'people-manager', 'team-lead', 'scrum-team',
            'squad', 'chapter', 'guild',
            
            # ==================== COMPANY STAGE ====================
            'startup', 'early-stage', 'series-a', 'series-b', 'series-c', 'growth-stage',
            'established', 'enterprise', 'fortune-500', 'public-company',
            'non-profit', 'government-agency', 'educational-institution',
            
            # ==================== LOCATION SPECIFIC ====================
            'downtown', 'suburban', 'rural', 'urban', 'tech-hub', 'financial-district',
            'research-park', 'industrial-park', 'headquarters', 'branch-office',
            'satellite-office', 'co-working-space',
            
            # ==================== INDUSTRY TRENDS ====================
            'digital-transformation', 'cloud-migration', 'ai-implementation',
            'automation', 'digitalization', 'sustainability-initiatives',
            'esg', 'remote-work-transition', 'hybrid-work-model',
            
            # ==================== PROJECT TYPE ====================
            'greenfield', 'brownfield', 'legacy-modernization', 'digital-transformation',
            'product-development', 'research-development', 'client-implementation',
            'internal-tools', 'customer-facing', 'b2b', 'b2c',
            
            # ==================== WORK SCHEDULE ====================
            '9-to-5', 'flexible-schedule', 'core-hours', 'results-only',
            'four-day-week', 'compressed-hours', 'shift-rotation', 'on-call',
            'after-hours', 'weekend-availability', 'holiday-cover',
            
            # ==================== APPLICATION PROCESS ====================
            'easy-apply', 'quick-application', 'multiple-interviews', 'technical-test',
            'assessment-center', 'case-study', 'portfolio-review', 'reference-check',
            'background-screening', 'immediate-start', 'notice-period-required',
            
            # ==================== COMPANY AWARDS & RECOGNITION ====================
            'best-places-to-work', 'fastest-growing', 'innovation-award',
            'customer-service-award', 'diversity-award', 'environmental-award',
            'industry-leader', 'award-winning',
            
            # ==================== SPECIALIZED EQUIPMENT ====================
            'company-provided-laptop', 'company-phone', 'equipment-provided',
            'tools-provided', 'vehicle-provided', 'safety-equipment',
            'specialized-software', 'professional-license',
            
            # ==================== INTERNATIONAL ====================
            'multinational', 'global-role', 'regional-role', 'local-role',
            'language-required', 'multilingual', 'international-travel',
            'cross-cultural', 'global-team',
            
            # ==================== SEASONAL & TIMING ====================
            'seasonal', 'holiday-season', 'summer-job', 'winter-season',
            'year-round', 'peak-season', 'off-peak', 'project-based',
            'fixed-duration', 'ongoing',
            
            # ==================== SECURITY & COMPLIANCE ====================
            'hipaa', 'gdpr', 'pci-dss', 'sox', 'ferpa', 'ccpa', 'iso-27001',
            'soc-2', 'nist', 'fedramp', 'compliance', 'regulatory',
            
            # ==================== ECONOMIC FACTORS ====================
            'recession-proof', 'essential-services', 'growth-industry',
            'emerging-market', 'stable-industry', 'cyclical',
        ]