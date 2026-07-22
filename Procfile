web: python init_db.py && exec gunicorn --bind 0.0.0.0:$PORT --threads 4 --timeout 120 --access-logfile - --error-logfile - run:app
