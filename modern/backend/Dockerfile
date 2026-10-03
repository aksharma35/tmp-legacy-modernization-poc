# Modern runtime: Python 3.12.
FROM python:3.12-slim

WORKDIR /app/backend
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.txt

ENV PYTHONUNBUFFERED=1 PORT=5001 TEST_HOOKS=1
EXPOSE 5001
CMD ["python", "app.py"]
