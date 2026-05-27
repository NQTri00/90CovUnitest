# Base image with Python 3.11
FROM python:3.11-slim

# Install system dependencies, including OpenJDK for running Java tests
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jdk-headless \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set Java home environment variable
ENV JAVA_HOME=/usr/lib/jvm/default-java
ENV PATH=$JAVA_HOME/bin:$PATH

# Set working directory
WORKDIR /app

# Copy python dependencies list
COPY requirements.txt /app/

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . /app

# Expose port 8000 for FastAPI
EXPOSE 8000

# Run FastAPI Web Server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
