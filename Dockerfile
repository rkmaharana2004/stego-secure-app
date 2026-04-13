FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for image processing
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create necessary directories
RUN mkdir -p backend/uploads backend/gallery

EXPOSE 8000

# Set environment variable for the port (default to 8000)
ENV PORT=8000

# Start the application from the backend directory
CMD ["python", "backend/app.py"]
