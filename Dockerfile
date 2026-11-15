# Image for the PO score system: gunicorn serving the Django app on port 8000.
FROM python:3.12-slim

# No .pyc files, unbuffered logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first: this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then the project code (see .dockerignore for what is left out).
COPY . .

# Collect static files (admin CSS etc.) into STATIC_ROOT; WhiteNoise serves them.
# A throwaway secret key is enough for this build step. It is not stored in the image.
RUN DJANGO_SECRET_KEY=build-only USE_SQLITE=True python manage.py collectstatic --noinput

# Do not run as root.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# Migrations are NOT run here: whoever runs the container does that on purpose
# (docker run ... python manage.py migrate).
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000"]
