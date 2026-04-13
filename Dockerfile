FROM python:3.10-slim

WORKDIR /app

# Install only basic system dependencies
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create necessary directories inside backend
RUN mkdir -p backend/uploads backend/gallery

# Change working directory to backend so app.py can find evaluator.py etc.
WORKDIR /app/backend

EXPOSE 8000
ENV PORT=8000

# Start the application from the backend directory
CMD ["python", "app.py"]
