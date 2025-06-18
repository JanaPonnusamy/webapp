FROM python:3.10-slim

WORKDIR /app

# Install dependencies and ODBC Driver 18
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        unixodbc \
        unixodbc-dev \
        curl \
        gnupg2 \
        ca-certificates && \
    curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /etc/apt/trusted.gpg.d/microsoft.gpg && \
    curl https://packages.microsoft.com/config/debian/11/prod.list -o /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:app"]
