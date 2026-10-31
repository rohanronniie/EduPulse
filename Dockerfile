FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EDUPULSE_ENV=production \
    PORT=8080

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home --uid 10001 edupulse \
    && chown -R edupulse:edupulse /app

USER edupulse
EXPOSE 8080
CMD ["python", "wsgi.py"]
