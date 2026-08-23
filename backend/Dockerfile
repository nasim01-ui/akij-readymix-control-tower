# backend/Dockerfile - Runs the Akij Readymix API with ODBC Driver 18 preinstalled.
# Build as root (runs apt-get reliably) -> runs gunicorn as a non-root user.
FROM python:3.11-bookworm

# Install system deps + Microsoft ODBC Driver 18 for SQL Server
# (auto-detect Debian codename so the MS repo matches the base image)
RUN export DEBIAN_FRONTEND=noninteractive \
 && CODENAME=$(. /etc/os-release && echo $VERSION_CODENAME) \
 && apt-get update -y \
 && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        gnupg curl apt-transport-https ca-certificates unixodbc unixodbc-dev \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/${CODENAME}/prod ${CODENAME} main" \
        > /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update -y \
 && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY config.py database.py app.py ./

# Non-root user for runtime (gunicorn binds to $PORT from Render)
RUN useradd -m appuser
USER appuser

EXPOSE 8000

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000"]