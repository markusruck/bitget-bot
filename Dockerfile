FROM python:3.11-slim

# System-Basics (optional, aber hilfreich für wheels)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Falls es eine requirements.txt gibt: installieren. Wenn nicht, wird einfach geskippt.
COPY requirements.txt* /tmp/
RUN if [ -f /tmp/requirements.txt ]; then pip install --no-cache-dir -r /tmp/requirements.txt; fi

# Code rein
COPY . .

# Sofortige Logausgabe
ENV PYTHONUNBUFFERED=1

# Worker start
CMD ["python","-u","paper_runner.py"]

WORKDIR /app
ENV PYTHONUNBUFFERED=1
CMD ["python", "paper_runner.py"]


FROM python:3.11-slim
WORKDIR /app
COPY ./app /app
RUN pip install --no-cache-dir ccxt pandas numpy requests
CMD ["python", "paper_runner.py"]
