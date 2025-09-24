FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt* /tmp/
RUN if [ -f /tmp/requirements.txt ]; then pip install --no-cache-dir -r /tmp/requirements.txt; fi
COPY . .
RUN mkdir -p /data
ENV PYTHONUNBUFFERED=1
CMD ["python","-u","app/paper_runner.py"]
