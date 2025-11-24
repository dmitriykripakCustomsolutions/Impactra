FROM python:3.12-slim

WORKDIR /app

# Copy the shared module
COPY shared /app/shared

# Copy CodeRunner service code
COPY CodeRunner /app/CodeRunner

# Install dependencies
RUN pip install --no-cache-dir -r /app/CodeRunner/requirements.txt

# Mount volume for persistent task storage
VOLUME ["/data"]

EXPOSE 5002

CMD ["python", "/app/CodeRunner/main.py"]

