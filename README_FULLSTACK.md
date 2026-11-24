# RentMyRide (Flask + SQLite)

## Run on Windows
1. Extract this ZIP.
2. Open the extracted project folder.
3. Double-click `run_windows.bat` (or in CMD run `py -m pip install -r requirements.txt`, then `py app.py`).
4. Open http://127.0.0.1:5000

Admin demo credentials: `admin@rentmyride.com` / `Admin@123`.

Signup/reset OTP: SMTP can be configured using environment variables `RMR_SMTP_HOST`, `RMR_SMTP_PORT`, `RMR_SMTP_EMAIL`, and `RMR_SMTP_PASSWORD`. Without SMTP configured, local testing displays a demo OTP in the page message. Demo OTP expires in 5 minutes.

Passwords: minimum 8 characters, uppercase, lowercase, number and special character.
Payments are simulated only; no real money is charged.
Database is local SQLite (`rentmyride.db`).
