WORKDIR /app
ENV PYTHONUNBUFFERED=1
CMD ["python", "paper_runner.py"]


FROM python:3.11-slim
WORKDIR /app
COPY ./app /app
RUN pip install --no-cache-dir ccxt pandas numpy requests
CMD ["python", "paper_runner.py"]
