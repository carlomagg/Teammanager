FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    libreoffice \
    # wkhtmltopdf \
    wget \
    gnupg \
    # software-properties-common \
    xfonts-75dpi \
    xfonts-base \
    libxrender1 \
    libxtst6 \
    libjpeg62-turbo \
    libx11-dev \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libasound2 \
    libfontconfig1 \
    libfreetype6 \
    libssl-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Confirm LibreOffice installed (debug step)
RUN libreoffice --version

# Set workdir
WORKDIR /app

# Copy project
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# RUN python manage.py setup_vacancy_data

# Run collectstatic
RUN python manage.py collectstatic --noinput

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Ensure build.sh is executable
RUN chmod +x build.sh

# Expose port
EXPOSE 8000

# Start the server
CMD ["gunicorn", "raadaa.wsgi:application", "--bind", "0.0.0.0:8000"]
