#!/usr/bin/env bash
set -o errexit  # Exit on error
set -o pipefail  # Catch pipeline errors
set -x  # Enable debug output

echo "Starting build.sh at $(date)"

# Install dependencies
pip install --no-cache-dir -r requirements.txt

# Run migrations
echo "Running migrations..."
python manage.py migrate || { echo "Migration failed"; exit 1; }

# Create superuser
if [[ -n "$DJANGO_SUPERUSER_USERNAME" && -n "$DJANGO_SUPERUSER_EMAIL" && -n "$DJANGO_SUPERUSER_PASSWORD" ]]; then
    echo "Creating superuser: $DJANGO_SUPERUSER_USERNAME"
    # Check if user exists
    if python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); exit(0 if User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists() else 1)"; then
        echo "Superuser '$DJANGO_SUPERUSER_USERNAME' already exists, updating..."
        python manage.py shell <<EOF || { echo "Superuser update failed"; exit 1; }
from django.contrib.auth import get_user_model
User = get_user_model()
user = User.objects.get(username='$DJANGO_SUPERUSER_USERNAME')
user.email = '$DJANGO_SUPERUSER_EMAIL'
user.set_password('$DJANGO_SUPERUSER_PASSWORD')
user.is_staff = True
user.is_superuser = True
user.save()
print("Superuser updated successfully")
EOF
    else
        echo "Creating new superuser..."
        python manage.py createsuperuser --noinput --username "$DJANGO_SUPERUSER_USERNAME" --email "$DJANGO_SUPERUSER_EMAIL" || { echo "Superuser creation failed"; exit 1; }
    fi
    # Assign Admin role
    echo "Assigning Admin role to $DJANGO_SUPERUSER_USERNAME..."
    python manage.py assign_admin_role --username "$DJANGO_SUPERUSER_USERNAME" || { echo "Admin role assignment failed"; exit 1; }
else
    echo "Superuser environment variables not set: USERNAME=$DJANGO_SUPERUSER_USERNAME, EMAIL=$DJANGO_SUPERUSER_EMAIL, PASSWORD=$DJANGO_SUPERUSER_PASSWORD (hidden for security). Skipping superuser creation."
fi
echo "build.sh completed at $(date)"