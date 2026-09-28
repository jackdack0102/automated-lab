FROM python:3.10-slim

WORKDIR /app

# 1. Copy requirements.txt 
COPY requirements.txt .

# 2. Install dependencies 
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copy source code 
COPY main.py .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]