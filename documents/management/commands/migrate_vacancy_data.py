from django.core.management.base import BaseCommand
# from cities_light.models import City, Country
from documents.models import Vacancy, VacancySkill, VacancyTag
from cities_light.models import Region

class Command(BaseCommand):
    def handle(self, *args, **options):
        for vacancy in Vacancy.objects.all():
            if vacancy.old_skills:
                skills_list = [skill.strip() for skill in vacancy.old_skills.split(',') if skill.strip()]
                for skill_name in skills_list:
                    skill, created = VacancySkill.objects.get_or_create(name=skill_name.lower())
                    vacancy.skills.add(skill)
            
            if vacancy.old_city:
                try:
                    city = Region.objects.get(name=vacancy.old_city)
                    vacancy.city = city
                    vacancy.save()
                except (Region.DoesNotExist):
                    pass