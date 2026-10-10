# The API: FastAPI wrapping engine/, with the catalog and surrogate models from data/.
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engine ./engine
COPY api ./api
COPY data ./data

EXPOSE 8001
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
