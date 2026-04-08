FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Cloud Run sets the PORT environment variable
ENV HOST=0.0.0.0
ENV RELOAD=false

EXPOSE 8080

CMD ["python", "run_server.py"]
