# GUH-26

for dashboard 

First time only: install the dependencies


python -m pip install -r requirements-dashboard.txt
Load the demo data


python scripts/seed_dashboard.py --reset
--reset also refreshes the message times, so "2 min ago" still looks right later in the day. Run it again just before you demo.

Start the server


$env:DEMO_MODE = "1"
uvicorn dashboard_dev:app --reload --port 8001
Open it at http://localhost:8001/account and click Try the demo to log in as Hadi.

If you sign up with your own number instead, the 6-digit code is printed in the terminal where uvicorn is running. Look for a line like [DEMO_MODE] Login code for +447...: 123456. In demo mode no real texts are sent.

If it says port 8001 is already in use: the copy I started earlier for testing is probably still running. Close it from the Claude Code background tasks, or just use another port:


uvicorn dashboard_dev:app --reload --port 8002
The $env:DEMO_MODE setting only lasts for that PowerShell window. To make it stick, copy .env.example to .env; the dev server reads that file automatically.
