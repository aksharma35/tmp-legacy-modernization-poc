# Legacy runtime: Python 2.7 (end-of-life since 2020). The official image is
# deprecated but still available on Docker Hub, so we pin it by tag.
FROM python:2.7.18-slim

WORKDIR /app/backend
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.txt

ENV PYTHONUNBUFFERED=1 PORT=5001 TEST_HOOKS=1
EXPOSE 5001
CMD ["python", "app.py"]
