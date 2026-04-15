from django.core.management.base import BaseCommand
from documents.models import VacancySkill

class Command(BaseCommand):
    help = 'Import comprehensive skills list across all industries'
    
    def handle(self, *args, **options):
        comprehensive_skills = self.get_comprehensive_skills_list()
        
        created_count = 0
        for skill_name in comprehensive_skills:
            skill, created = VacancySkill.objects.get_or_create(
                name=skill_name.lower().strip()
            )
            if created:
                created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully imported {created_count} new skills. '
                f'Total skills in database: {VacancySkill.objects.count()}'
            )
        )
    
    def get_comprehensive_skills_list(self):
        return [
            # ==================== TECHNOLOGY & IT ====================
            # Programming Languages
            'Python', 'JavaScript', 'Java', 'C++', 'C#', 'PHP', 'Ruby', 'Go', 'Rust', 'Swift',
            'Kotlin', 'TypeScript', 'SQL', 'HTML5', 'CSS3', 'R', 'MATLAB', 'Shell Scripting', 'PowerShell',
            'Scala', 'Perl', 'Haskell', 'Dart', 'Elixir', 'Clojure', 'Objective-C', 'VBA', 'Assembly',
            
            # Web Development Frameworks
            'Django', 'Flask', 'FastAPI', 'React', 'Angular', 'Vue.js', 'Node.js', 'Express.js',
            'Spring Boot', 'Laravel', 'Ruby on Rails', 'ASP.NET', 'jQuery', 'Bootstrap', 'Tailwind CSS',
            'SASS', 'LESS', 'Ember.js', 'Backbone.js', 'Meteor', 'Svelte', 'Next.js', 'Nuxt.js',
            
            # Mobile Development
            'React Native', 'Flutter', 'iOS Development', 'Android Development', 'Xamarin',
            'Ionic', 'Cordova', 'PhoneGap', 'SwiftUI', 'Jetpack Compose',
            
            # Databases
            'PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'SQLite', 'Oracle Database', 'Microsoft SQL Server',
            'Cassandra', 'Elasticsearch', 'DynamoDB', 'Firebase', 'Cosmos DB', 'MariaDB', 'DB2',
            'Neo4j', 'InfluxDB', 'ClickHouse', 'Snowflake', 'BigQuery', 'Redshift',
            
            # DevOps & Cloud
            'AWS', 'Azure', 'Google Cloud Platform', 'Docker', 'Kubernetes', 'Terraform', 'Ansible',
            'Jenkins', 'GitLab CI', 'GitHub Actions', 'Linux System Administration', 'Unix', 'Bash',
            'Nginx', 'Apache', 'Helm', 'Prometheus', 'Grafana', 'Nagios', 'Splunk', 'ELK Stack',
            'CI/CD', 'Infrastructure as Code', 'Microservices', 'Serverless', 'Containerization',
            
            # Software Development Tools
            'Git', 'GitHub', 'GitLab', 'Bitbucket', 'JIRA', 'Confluence', 'Slack', 'Trello',
            'Visual Studio Code', 'IntelliJ IDEA', 'Eclipse', 'PyCharm', 'WebStorm', 'Android Studio',
            'Xcode', 'Postman', 'Swagger', 'Figma', 'Sketch', 'Adobe XD',
            
            # Cybersecurity
            'Network Security', 'Information Security', 'Ethical Hacking', 'Penetration Testing',
            'Vulnerability Assessment', 'SIEM', 'Firewall Management', 'Identity & Access Management',
            'Cryptography', 'SSL/TLS', 'PKI', 'SOC Operations', 'Incident Response', 'Digital Forensics',
            'GDPR Compliance', 'HIPAA Compliance', 'PCI DSS', 'NIST Framework', 'ISO 27001',
            
            # Data Science & AI
            'Machine Learning', 'Deep Learning', 'Natural Language Processing', 'Computer Vision',
            'Data Mining', 'Predictive Modeling', 'Statistical Analysis', 'Data Visualization',
            'Tableau', 'Power BI', 'Looker', 'Qlik', 'TensorFlow', 'PyTorch', 'Keras', 'Scikit-learn',
            'Pandas', 'NumPy', 'Matplotlib', 'Seaborn', 'Plotly', 'Hadoop', 'Spark', 'Hive',
            'Data Engineering', 'ETL', 'Data Warehousing', 'Business Intelligence',
            
            # ==================== BUSINESS & MANAGEMENT ====================
            # Project Management
            'Agile Methodology', 'Scrum', 'Kanban', 'Waterfall', 'PMBOK', 'PRINCE2',
            'Project Planning', 'Risk Management', 'Stakeholder Management', 'Budget Management',
            'Resource Allocation', 'Project Lifecycle', 'JIRA Management', 'Asana', 'Monday.com',
            
            # Product Management
            'Product Strategy', 'Roadmapping', 'User Stories', 'Backlog Grooming', 'A/B Testing',
            'Market Research', 'Competitive Analysis', 'Product Launch', 'Go-to-Market Strategy',
            'Customer Development', 'Requirements Gathering', 'UX/UI Collaboration',
            
            # Business Analysis
            'Requirements Analysis', 'Process Modeling', 'Stakeholder Analysis', 'SWOT Analysis',
            'Use Case Development', 'Business Process Reengineering', 'Data Modeling', 'UML',
            'BPMN', 'Gap Analysis', 'Cost-Benefit Analysis',
            
            # Operations Management
            'Supply Chain Management', 'Logistics', 'Inventory Management', 'Quality Control',
            'Six Sigma', 'Lean Manufacturing', 'Kaizen', 'Process Improvement', 'ERP Systems',
            'SAP', 'Oracle E-Business Suite', 'Workflow Optimization',
            
            # Strategic Management
            'Strategic Planning', 'Business Development', 'Market Analysis', 'Corporate Strategy',
            'Mergers & Acquisitions', 'Partnership Development', 'Strategic Partnerships',
            'Change Management', 'Organizational Development',
            
            # ==================== SALES & MARKETING ====================
            # Digital Marketing
            'SEO', 'SEM', 'Google Ads', 'Facebook Ads', 'Social Media Marketing', 'Content Marketing',
            'Email Marketing', 'Inbound Marketing', 'Marketing Automation', 'Google Analytics',
            'Google Tag Manager', 'HubSpot', 'Marketo', 'Pardot', 'Copywriting', 'Content Strategy',
            'Conversion Rate Optimization', 'Landing Page Optimization',
            
            # Traditional Marketing
            'Brand Management', 'Market Research', 'Consumer Behavior', 'Advertising',
            'Public Relations', 'Media Planning', 'Event Marketing', 'Trade Shows',
            'Marketing Strategy', 'Product Marketing', 'Go-to-Market Strategy',
            
            # Sales
            'B2B Sales', 'B2C Sales', 'Enterprise Sales', 'SaaS Sales', 'Solution Selling',
            'Consultative Selling', 'Account Management', 'CRM Management', 'Salesforce',
            'HubSpot CRM', 'Pipeline Management', 'Sales Forecasting', 'Negotiation',
            'Prospecting', 'Lead Generation', 'Cold Calling', 'Sales Presentations',
            'Contract Negotiation', 'Revenue Operations',
            
            # E-commerce
            'Shopify', 'WooCommerce', 'Magento', 'BigCommerce', 'Amazon FBA', 'E-commerce Strategy',
            'Online Merchandising', 'Shopping Cart Optimization', 'Payment Gateway Integration',
            
            # ==================== FINANCE & ACCOUNTING ====================
            # Accounting
            'Financial Accounting', 'Managerial Accounting', 'GAAP', 'IFRS', 'Bookkeeping',
            'Accounts Payable', 'Accounts Receivable', 'Payroll Processing', 'Tax Preparation',
            'Auditing', 'Internal Controls', 'Financial Reporting', 'QuickBooks', 'Sage', 'Xero',
            
            # Corporate Finance
            'Financial Analysis', 'Financial Modeling', 'Valuation', 'M&A', 'Corporate Finance',
            'Capital Budgeting', 'Cash Flow Management', 'Risk Management', 'Treasury Management',
            'Investor Relations', 'FP&A', 'Budgeting & Forecasting',
            
            # Banking & Investment
            'Investment Banking', 'Commercial Banking', 'Wealth Management', 'Portfolio Management',
            'Risk Assessment', 'Credit Analysis', 'Loan Origination', 'Securities Trading',
            'Derivatives', 'Fixed Income', 'Equity Research', 'Compliance', 'Anti-Money Laundering',
            
            # FinTech
            'Blockchain', 'Cryptocurrency', 'Digital Payments', 'Mobile Banking', 'Robo-advisors',
            'Regulatory Technology', 'InsurTech', 'Peer-to-Peer Lending',
            
            # ==================== HEALTHCARE & MEDICAL ====================
            # Clinical Skills
            'Patient Care', 'Medical Diagnosis', 'Treatment Planning', 'Clinical Research',
            'Electronic Health Records', 'Epic Systems', 'Cerner', 'Medical Coding', 'ICD-10',
            'HIPAA Compliance', 'Patient Safety', 'Telemedicine', 'Medical Billing',
            
            # Healthcare Administration
            'Healthcare Management', 'Hospital Administration', 'Healthcare Policy',
            'Medical Staff Coordination', 'Healthcare Compliance', 'Patient Relations',
            'Healthcare Informatics', 'Population Health Management',
            
            # Nursing & Allied Health
            'Nursing Care', 'Patient Assessment', 'Medication Administration', 'Wound Care',
            'Emergency Response', 'Critical Care', 'Pediatric Care', 'Geriatric Care',
            'Physical Therapy', 'Occupational Therapy', 'Radiology', 'Laboratory Techniques',
            
            # Pharmaceuticals
            'Clinical Trials', 'Pharmacovigilance', 'Regulatory Affairs', 'Drug Development',
            'Good Clinical Practice', 'Good Manufacturing Practice', 'Biostatistics',
            
            # ==================== ENGINEERING ====================
            # Civil Engineering
            'Structural Engineering', 'Geotechnical Engineering', 'Transportation Engineering',
            'Water Resources Engineering', 'Construction Management', 'AutoCAD Civil 3D',
            'Revit', 'BIM', 'Project Estimation', 'Site Inspection',
            
            # Mechanical Engineering
            'CAD', 'SolidWorks', 'AutoCAD', 'Finite Element Analysis', 'Thermodynamics',
            'Fluid Mechanics', 'HVAC', 'Product Design', 'Manufacturing Processes',
            'Quality Assurance', 'GD&T',
            
            # Electrical Engineering
            'Circuit Design', 'PCB Design', 'Power Systems', 'Control Systems', 'Embedded Systems',
            'VHDL', 'Verilog', 'MATLAB Simulink', 'PLC Programming', 'Renewable Energy Systems',
            
            # Chemical Engineering
            'Process Engineering', 'Chemical Process Design', 'Process Safety', 'P&ID',
            'Distillation', 'Reaction Engineering', 'Polymer Science', 'Petroleum Engineering',
            
            # ==================== CREATIVE & DESIGN ====================
            # Graphic Design
            'Adobe Creative Suite', 'Photoshop', 'Illustrator', 'InDesign', 'After Effects',
            'Premiere Pro', 'Typography', 'Brand Identity', 'Print Design', 'Digital Illustration',
            'UI Design', 'UX Design', 'Wireframing', 'Prototyping', 'Design Systems',
            
            # Web & Digital Design
            'Responsive Design', 'User Experience', 'User Interface Design', 'Interaction Design',
            'Information Architecture', 'Usability Testing', 'Accessibility Design', 'Web Accessibility',
            
            # Video & Animation
            'Video Editing', 'Motion Graphics', '3D Modeling', 'Blender', 'Maya', 'Cinema 4D',
            'Video Production', 'Color Grading', 'Sound Design', 'Visual Effects',
            
            # ==================== EDUCATION & TRAINING ====================
            'Curriculum Development', 'Instructional Design', 'E-learning', 'LMS Administration',
            'Classroom Management', 'Student Assessment', 'Educational Technology', 'Teaching',
            'Training Delivery', 'Workshop Facilitation', 'Course Design', 'Moodle', 'Blackboard',
            
            # ==================== LEGAL ====================
            'Legal Research', 'Contract Law', 'Corporate Law', 'Litigation', 'Legal Writing',
            'Document Review', 'Compliance', 'Intellectual Property', 'Employment Law',
            'Regulatory Compliance', 'Risk Assessment', 'Westlaw', 'LexisNexis',
            
            # ==================== HUMAN RESOURCES ====================
            'Recruitment', 'Talent Acquisition', 'Employee Relations', 'Performance Management',
            'Compensation & Benefits', 'HRIS', 'Workday', 'SuccessFactors', 'Training & Development',
            'Organizational Development', 'HR Compliance', 'Labor Relations', 'Onboarding',
            'Diversity & Inclusion', 'HR Analytics', 'Workplace Safety', 'OSHA Compliance',
            
            # ==================== CUSTOMER SERVICE ====================
            'Customer Support', 'Technical Support', 'Help Desk', 'Call Center Operations',
            'Customer Relationship Management', 'Client Services', 'Account Management',
            'Customer Success', 'Problem Resolution', 'Service Level Agreement Management',
            'Zendesk', 'Freshdesk', 'ServiceNow',
            
            # ==================== REAL ESTATE ====================
            'Property Management', 'Real Estate Sales', 'Commercial Real Estate', 'Real Estate Law',
            'Property Valuation', 'Lease Negotiation', 'Facilities Management', 'Real Estate Development',
            'Mortgage Lending', 'Appraisal',
            
            # ==================== HOSPITALITY & TOURISM ====================
            'Hotel Management', 'Restaurant Management', 'Event Planning', 'Tourism Management',
            'Customer Service', 'Revenue Management', 'Hospitality Operations', 'Culinary Arts',
            'Food Safety', 'Menu Planning',
            
            # ==================== MANUFACTURING ====================
            'Production Planning', 'Quality Control', 'Lean Manufacturing', 'Six Sigma',
            'Supply Chain Management', 'Inventory Control', 'ERP Implementation', 'Shop Floor Management',
            'Safety Compliance', 'ISO 9001', 'Production Scheduling',
            
            # ==================== RETAIL ====================
            'Retail Management', 'Merchandising', 'Inventory Management', 'Visual Merchandising',
            'Store Operations', 'Loss Prevention', 'Retail Analytics', 'E-commerce Management',
            'Customer Experience', 'Point of Sale Systems',
            
            # ==================== SCIENCE & RESEARCH ====================
            'Laboratory Techniques', 'Research Methodology', 'Data Analysis', 'Scientific Writing',
            'Grant Writing', 'Experimental Design', 'Biotechnology', 'Chemistry Analysis',
            'Microbiology', 'Environmental Science', 'Geology',
            
            # ==================== MEDIA & COMMUNICATIONS ====================
            'Journalism', 'Content Writing', 'Copy Editing', 'Public Speaking', 'Media Relations',
            'Corporate Communications', 'Social Media Management', 'Content Strategy',
            'Broadcast Production', 'Script Writing', 'Audio Production',
            
            # ==================== CONSTRUCTION ====================
            'Construction Management', 'Blueprint Reading', 'Site Supervision', 'Safety Management',
            'Cost Estimation', 'Project Scheduling', 'Building Codes', 'Contract Management',
            'Subcontractor Management', 'Quality Assurance',
            
            # ==================== TRANSPORTATION & LOGISTICS ====================
            'Supply Chain Management', 'Logistics Planning', 'Fleet Management', 'Warehouse Management',
            'Inventory Control', 'Transportation Management', 'Customs Compliance', 'Freight Forwarding',
            'Route Optimization', 'Distribution Management',
            
            # ==================== ENERGY ====================
            'Renewable Energy', 'Solar Power', 'Wind Energy', 'Energy Management', 'Oil & Gas',
            'Power Systems', 'Energy Efficiency', 'Environmental Compliance', 'Project Development',
            
            # ==================== GOVERNMENT & PUBLIC SECTOR ====================
            'Public Policy', 'Government Relations', 'Program Management', 'Grant Management',
            'Community Development', 'Public Administration', 'Policy Analysis', 'Legislative Affairs',
            'Budget Analysis', 'Constituent Services',
            
            # ==================== NON-PROFIT ====================
            'Fundraising', 'Grant Writing', 'Donor Relations', 'Volunteer Management',
            'Program Development', 'Non-profit Management', 'Community Outreach', 'Advocacy',
            'Event Planning', 'Membership Management',
            
            # ==================== AGRICULTURE ====================
            'Crop Management', 'Soil Science', 'Agricultural Engineering', 'Livestock Management',
            'Precision Agriculture', 'Sustainable Farming', 'Agribusiness', 'Food Science',
            
            # ==================== ENVIRONMENTAL ====================
            'Environmental Science', 'Sustainability', 'Environmental Compliance', 'Conservation',
            'Environmental Impact Assessment', 'Waste Management', 'Water Quality', 'Climate Science',
            
            # ==================== SKILLED TRADES ====================
            'Electrical Work', 'Plumbing', 'Carpentry', 'Welding', 'HVAC Installation',
            'Automotive Repair', 'Equipment Maintenance', 'Blueprint Reading', 'Safety Protocols',
            
            # ==================== EMERGING TECHNOLOGIES ====================
            'Internet of Things', 'Quantum Computing', 'Augmented Reality', 'Virtual Reality',
            '5G Technology', 'Edge Computing', 'Robotic Process Automation', 'Digital Twin',
            'Metaverse Development', 'Web3', 'NFT', 'Smart Contracts',
            
            # ==================== SOFT SKILLS ====================
            'Communication', 'Teamwork', 'Problem Solving', 'Critical Thinking', 'Leadership',
            'Time Management', 'Adaptability', 'Creativity', 'Work Ethic', 'Attention to Detail',
            'Conflict Resolution', 'Emotional Intelligence', 'Presentation Skills', 'Negotiation',
            'Decision Making', 'Strategic Thinking', 'Customer Service', 'Mentoring', 'Coaching',
            'Collaboration', 'Innovation', 'Resilience', 'Stress Management', 'Cultural Awareness',
            'Networking', 'Public Speaking', 'Active Listening', 'Persuasion', 'Influence',
            'Delegation', 'Motivation', 'Change Management', 'Crisis Management',
            
            # ==================== LANGUAGE SKILLS ====================
            'English', 'Spanish', 'French', 'German', 'Chinese Mandarin', 'Japanese', 'Arabic',
            'Portuguese', 'Russian', 'Italian', 'Korean', 'Hindi', 'Dutch', 'Swedish',
            'Translation', 'Interpretation', 'Multilingual Communication',
            
            # ==================== PROFESSIONAL CERTIFICATIONS ====================
            'PMP', 'CPA', 'CFA', 'Six Sigma Black Belt', 'CISSP', 'AWS Certified', 'Google Cloud Certified',
            'Microsoft Certified', 'Cisco Certified', 'Salesforce Certified', 'Scrum Master',
            'Product Owner', 'ITIL', 'Lean Manufacturing', 'HR Certification',
        ]