FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ownerrez_mcp ./ownerrez_mcp
COPY http_app.py .

# Most hosts (Render, Railway, Fly) inject PORT at runtime; 8080 is the local default.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn http_app:app --host 0.0.0.0 --port ${PORT}"]
