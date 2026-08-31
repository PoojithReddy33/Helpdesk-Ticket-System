web: cd backend && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 3
worker: cd backend && python manage.py qcluster
release: cd backend && python manage.py migrate --noinput && python manage.py collectstatic --noinput
