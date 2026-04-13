FROM python:3.10-slim

WORKDIR /app

# We are removing apt-get entirely to avoid deployment errors.
# Modern Python wheels for Pillow/Numpy/Scipy usually include all necessary dependencies.

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create necessary directories
RUN mkdir -p backend/uploads backend/gallery

EXPOSE 8000

ENV PORT=8000

# Start the application from the backend directory
CMD ["python", "backend/app.py"]
