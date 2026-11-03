FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY backend/app ./app
COPY progress_forecast.py weight_forecast_model.py exercise_ranker.py weekly_plan.py Fitsense-Issue-5.py gym.json home.json /opt/fitsense/
ENV FITSENSE_FORECAST_ROOT=/opt/fitsense
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
