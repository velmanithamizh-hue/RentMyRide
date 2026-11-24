RentMyRide - Latest changes

1) Forgot Password OTP
- Send OTP button is disabled while sending.
- OTP is valid for 2 minutes.
- Button becomes Resend OTP after successful send and stays disabled for 2 minutes.
- Backend also prevents repeat requests during the OTP cooldown.

2) Fleet quantity / inventory
- Providers can enter one listing with quantity (1-500), instead of submitting duplicate model listings.
- Registration/reference number is optional for a quantity listing.
- Customers choose the quantity to book.
- Backend checks availability for the requested date range and prevents overbooking.
- Provider dashboard shows total units, available today, reserved today, and booking count.
- Search cards and booking records display quantities.

Existing database migration is automatic: quantity columns are added if missing; old records are treated as quantity 1.

SMTP setup:
- Copy .env.example to .env beside app.py.
- Replace the Gmail address and Google App Password.
- Never share the App Password.
- Install dependencies using: py -m pip install -r requirements.txt
- Run: py app.py (or run_windows.bat)
