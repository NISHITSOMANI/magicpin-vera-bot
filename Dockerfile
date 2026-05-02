FROM python:3.11-slim

WORKDIR /app

# Install deps first for build cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY bot ./bot

# HF Spaces injects PORT=7860; default to 7860 for Spaces, 8080 elsewhere
ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "uvicorn bot.main:app --host 0.0.0.0 --port ${PORT}"]
