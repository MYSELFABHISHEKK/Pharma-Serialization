FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc files & enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create required output and IO folders
RUN mkdir -p output l2_io/shared_folder l2_io/outbound

# Expose default HTTP port
EXPOSE 8000

# Start Uvicorn application server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
