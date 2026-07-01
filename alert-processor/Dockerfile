# alert-processor/Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY wazuh_listener.py .

CMD ["python3", "wazuh_listener.py"]