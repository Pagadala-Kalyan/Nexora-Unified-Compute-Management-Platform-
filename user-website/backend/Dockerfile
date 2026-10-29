FROM python:3.12-slim
WORKDIR /app
ENV NEXORA_IN_DOCKER=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
