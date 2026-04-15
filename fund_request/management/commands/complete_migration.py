from django.core.management.base import BaseCommand
from django.db import connection
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Complete the request type migration by faking it and manually fixing the database'

    def handle(self, *args, **options):
        self.stdout.write('Completing migration...')
        
        with connection.cursor() as cursor:
            # Step 1: Create the FundRequestType table manually
            self.stdout.write('Creating FundRequestType table...')
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS "fund_request_fundrequesttype" (
                    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                    "name" varchar(100) NOT NULL,
                    "created_at" datetime NOT NULL,
                    "created_by_id" bigint NULL REFERENCES "documents_customuser" ("id") DEFERRABLE INITIALLY DEFERRED,
                    "tenant_id" bigint NULL REFERENCES "tenants_tenant" ("id") DEFERRABLE INITIALLY DEFERRED
                )
            """)
            
            # Step 2: Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS "fund_request_fundrequesttype_created_by_id_idx" 
                ON "fund_request_fundrequesttype" ("created_by_id")
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS "fund_request_fundrequesttype_tenant_id_idx" 
                ON "fund_request_fundrequesttype" ("tenant_id")
            """)
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS "fund_request_fundrequesttype_tenant_id_name_uniq" 
                ON "fund_request_fundrequesttype" ("tenant_id", "name")
            """)
            
            # Step 3: Rename the old request_type column
            self.stdout.write('Renaming old request_type column...')
            cursor.execute("""
                ALTER TABLE fund_request_fundrequest 
                RENAME COLUMN request_type TO request_type_old
            """)
            
            # Step 4: Add new request_type_id column
            self.stdout.write('Adding new request_type_id column...')
            cursor.execute("""
                ALTER TABLE fund_request_fundrequest 
                ADD COLUMN request_type_id bigint NULL 
                REFERENCES fund_request_fundrequesttype(id) DEFERRABLE INITIALLY DEFERRED
            """)
            
            # Step 5: Mark migration as applied
            self.stdout.write('Marking migration as applied...')
            cursor.execute("""
                INSERT OR IGNORE INTO django_migrations (app, name, applied) 
                VALUES ('fund_request', '0004_alter_fundrequest_expense_date_fundrequesttype_and_more', datetime('now'))
            """)
            
        self.stdout.write(self.style.SUCCESS('\nMigration completed successfully!'))
        self.stdout.write('Now run: python manage.py setup_request_types')
