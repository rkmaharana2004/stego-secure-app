FROM python:3.10-slim

WORKDIR /app

# Only install basic system dependencies if absolutely necessary.
# Pillow and Scikit-Image usually work fine on slim images.
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create necessary directories
RUN mkdir -p backend/uploads backend/gallery

EXPOSE 8000

ENV PORT=8000

# Start the application from the backend directory
CMD ["python", "backend/app.py"]
