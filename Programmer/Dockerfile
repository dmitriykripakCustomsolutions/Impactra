FROM python:3.12-slim

ENV OPENAI_API_KEY=""
ENV CEREBRAS_API_KEY=""

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5001

CMD ["python", "main.py"]
