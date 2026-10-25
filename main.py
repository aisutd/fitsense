"""FitSense forecasting in one file: open it and press Run (the play button in VS Code).

Edit the three settings below, then run. No command line arguments are needed.

    ACTION = "forecast"  print one user's forecast (the XGBoost-corrected weight forecast)
    ACTION = "weekly"    save a forecast for every user to the progress_forecasts table
    ACTION = "train"     retrain the XGBoost weight model on real users from Supabase

The first run trains the model on simulated users if no model file exists yet, so it works
straight away. Real weigh-ins make it better: run ACTION = "train" once users have logged weight.
"""

import sys
from pathlib import Path

# ---- settings ---------------------------------------------------------------------------------
ACTION = "forecast"
WHO = "Grace"  # a name from USERS below, or paste any user_id
DRY_RUN = True  # for "weekly": True only counts the rows, False saves them
# -----------------------------------------------------------------------------------------------

USERS = {
    "Grace": "f449eafd-7993-4a4b-ad52-8adb9fef3270",  # completed week 1
    "James": "bd0b181f-7375-4040-a928-de0a4e21e19d",  # missed workouts in week 1
}

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import progress_forecast as pf  # noqa: E402
import weight_forecast_model as wfm  # noqa: E402


def connect():
    """A Supabase client built from SUPABASE_URL and SUPABASE_KEY in .env."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("recommender", BASE_DIR / "Fitsense-Issue-5.py")
    recommender = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recommender)
    return recommender.supabase_client()


def ensure_model():
    """Make sure a weight model exists, bootstrapping one on simulated users the first time."""
    if wfm.MODEL_PATH.exists():
        return
    print("No weight model yet: training one on simulated users (about 10 seconds)...")
    grouped = wfm.synthetic_rows()
    train_rows, validation_rows = wfm.split_by_user(grouped)
    model = wfm.train(train_rows, validation_rows)
    wfm.save_model(model)
    print(wfm.format_evaluation(wfm.evaluate(model, validation_rows)))
    print("(Simulated data: this shows the pipeline works, not accuracy on real people.)\n")


def forecast_one(client, user_id):
    forecasts = pf.forecast_from_supabase(client, user_id)
    print(pf.format_forecast(forecasts))
    weight = forecasts.get("weight_kg")
    if weight is not None and "baseline_predictions" not in weight:
        print(f"\nNote: the XGBoost correction needs {wfm.MIN_WEEKS_FOR_MODEL}+ weeks of logged weights; "
              f"this user has {weight['weeks_of_data']}, so the plain linear forecast is shown.")
    print('\nTo store forecasts in the progress_forecasts table, run ACTION = "weekly".')


def main():
    client = connect()
    if ACTION == "train":
        grouped = wfm.training_rows_from_supabase(client)
        total = sum(len(rows) for _, rows in grouped)
        print(f"{total} training rows from {len(grouped)} real users.")
        if total < wfm.MIN_TRAINING_ROWS:
            print(f"Need at least {wfm.MIN_TRAINING_ROWS} rows before real data can train the model; "
                  "keeping the current model.")
            return
        train_rows, validation_rows = wfm.split_by_user(grouped)
        model = wfm.train(train_rows, validation_rows or None)
        if validation_rows:
            print(wfm.format_evaluation(wfm.evaluate(model, validation_rows)))
        wfm.save_model(model)
        print(f"Saved {wfm.MODEL_PATH}.")
    elif ACTION == "weekly":
        ensure_model()
        rows = pf.run_weekly(client, dry_run=DRY_RUN)
        print(f"{'Would save' if DRY_RUN else 'Saved'} {len(rows)} forecasts to progress_forecasts.")
    elif ACTION == "forecast":
        ensure_model()
        forecast_one(client, USERS.get(WHO, WHO))
    else:
        print(f'ACTION must be "forecast", "weekly" or "train", not {ACTION!r}.')


if __name__ == "__main__":
    main()
