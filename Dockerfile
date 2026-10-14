FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir "mistralai-workflows>=3.10" "httpx>=0.27"
CMD ["python", "src/entrypoints/worker.py"]
