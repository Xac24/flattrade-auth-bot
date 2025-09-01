FROM mcr.microsoft.com/playwright/python:latest
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN playwright install --with-deps
ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]