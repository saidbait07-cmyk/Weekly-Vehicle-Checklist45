FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary
COPY . .
RUN mkdir -p private_uploads
EXPOSE 8000
CMD ["gunicorn", "-b", "0.0.0.0:8000", "--workers", "3", "app:app"]
