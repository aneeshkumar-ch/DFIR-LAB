FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_HOST=0.0.0.0
ENV FLASK_PORT=5000

# Install The Sleuth Kit, Perl, libmagic, and essential forensic libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    sleuthkit \
    perl \
    libmagic1 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and assets
COPY . /app/

# Ensure runtime directories exist
RUN mkdir -p /app/jobs && chmod -R 777 /app/jobs

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://127.0.0.1:5000/ || exit 1

CMD ["python", "app.py"]
