FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y curl gnupg2 ca-certificates unixodbc unixodbc-dev gcc g++ \
 && curl -sSL https://packages.microsoft.com/keys/microsoft-prod.pub | gpg --dearmor | tee /usr/share/keyrings/microsoft-prod.gpg > /dev/null \
 && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/11/prod bullseye main" > /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update \
 && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "app.py"]
