# 1. Use a stable, official Python Linux environment
FROM python:3.12-slim

# 2. Force the installation of the missing system libraries
RUN apt-get update -y && apt-get install -y libatomic1 nodejs npm

# 3. Set up our project folder
WORKDIR /app

# 4. Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of your app's code
COPY . .

# 6. Execute the start sequence (Prisma + Gunicorn)
CMD prisma db push && prisma generate && gunicorn -w 4 -b 0.0.0.0:$PORT app:app
