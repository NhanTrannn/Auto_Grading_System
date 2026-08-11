FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# All three must be siblings inside /app, matching the local layout:
# app/services/grading_engine/wrapper.py adds this directory to sys.path to
# import pipeline.py, and app/services/ocr_engine.py adds ./ocr to import
# ocr_main + ocr_modules. Leaving ocr/ out makes the container fail at
# startup, since a route module imports it while building the app.
COPY app ./app
COPY pipeline.py ./pipeline.py
COPY ocr ./ocr

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
