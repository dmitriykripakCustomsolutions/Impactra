FROM python:3.12-slim

ENV OPENAI_API_KEY=""
ENV CEREBRAS_API_KEY=""

WORKDIR /app

# Copy the shared module
COPY shared /app/shared

# Copy Programmer service code
COPY Programmer /app/Programmer

# Install dependencies
RUN pip install --no-cache-dir -r /app/Programmer/requirements.txt

# Mount volume for persistent task storage
VOLUME ["/data"]

EXPOSE 5001

CMD ["python", "/app/Programmer/main.py"]

