FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (ffmpeg is required by pydub/audio processing)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Script to run seed_db.py before starting uvicorn
# We use a simple shell script inline here in the CMD or copy an entrypoint
CMD python seed_db.py && uvicorn main:app --host 0.0.0.0 --port 8000
