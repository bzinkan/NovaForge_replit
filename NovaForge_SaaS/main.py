from flask import Flask, render_template, redirect, url_for
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Mock Data for Prototype
MOCK_USER = {
    "name": "Commander",
    "api_key": "nf_live_99823_xQy7z_cosmic_forge",
    "credits_total": 1000,
    "credits_used": 450,
    "plan": "Pro Tier"
}

ACTIVITY_LOG = [
    {"date": "2025-12-18 14:30", "prompt": "Cyberpunk city street, rainy neon night", "status": "Complete"},
    {"date": "2025-12-18 12:15", "prompt": "Low poly forest glade, day time", "status": "Complete"},
    {"date": "2025-12-17 09:45", "prompt": "Medieval castle interior, stone walls", "status": "Failed"},
]


@app.route('/')
def home():
    # Redirect straight to dashboard for this demo
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
def dashboard():
    # Calculate usage percentage
    usage_percent = int((MOCK_USER["credits_used"] / MOCK_USER["credits_total"]) * 100)

    return render_template(
        'dashboard.html',
        user=MOCK_USER,
        usage_percent=usage_percent,
        activity=ACTIVITY_LOG
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
