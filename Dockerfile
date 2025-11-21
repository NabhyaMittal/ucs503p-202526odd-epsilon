# Use an official lightweight Python image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file first (for better caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code (app.py, templates/, static/)
COPY . .

# Expose the port usually used by Flask (Render sets the $PORT env var automatically)
EXPOSE 5000

# Command to run the app using Gunicorn (Production Server)
# "app:app" means: look in file 'app.py' for the object named 'app'
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]