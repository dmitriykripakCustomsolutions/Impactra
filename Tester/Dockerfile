FROM python:3.12-slim

WORKDIR /app

# Copy the shared module
COPY shared /app/shared

COPY Tester /app/Tester

RUN pip install --no-cache-dir -r /app/Tester/requirements.txt

EXPOSE 5003

# Use absolute path to avoid issues if WORKDIR is overridden by a volume
CMD ["python", "/app/Tester/main.py"]
