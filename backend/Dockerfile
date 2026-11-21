FROM python:3.12-slim
WORKDIR /app
# XGBoost needs OpenMP at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY backend/app ./app
COPY progress_forecast.py weight_forecast_model.py exercise_ranker.py adaptation_model.py weekly_plan.py Fitsense-Issue-5.py gym.json home.json /opt/fitsense/
# Bootstrap adaptation model from simulated users; retrain on real data with `train --supabase`.
RUN cd /opt/fitsense && python adaptation_model.py train
ENV FITSENSE_FORECAST_ROOT=/opt/fitsense
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
