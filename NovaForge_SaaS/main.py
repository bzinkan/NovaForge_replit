from flask import Flask, render_template, redirect, url_for, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///novaforge.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- DATABASE MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    api_key = db.Column(db.String(120), unique=True, nullable=False)
    credits_total = db.Column(db.Integer, default=1000)
    credits_used = db.Column(db.Integer, default=0)
    plan = db.Column(db.String(50), default="Free Tier")
    logs = db.relationship('GenerationLog', backref='user', lazy=True)

class GenerationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    prompt = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default="Processing")

# --- INITIALIZATION ---
def init_db():
    with app.app_context():
        db.create_all()
        # Create a mock user if none exists (Auto-Signup for demo)
        if not User.query.first():
            test_user = User(
                username="Commander",
                api_key="nf_live_" + str(uuid.uuid4())[:8],
                credits_total=1000,
                credits_used=450,
                plan="Pro Tier"
            )
            db.session.add(test_user)
            db.session.commit()
            print("Initialized Database with Mock User")

# --- ROUTES ---
@app.route('/')
def home():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    # For prototype, always grab the first user
    user = User.query.first()
    
    # Calculate usage percentage
    usage_percent = 0
    if user.credits_total > 0:
        usage_percent = int((user.credits_used / user.credits_total) * 100)
    
    # Get recent activity from DB
    activity_logs = GenerationLog.query.filter_by(user_id=user.id).order_by(GenerationLog.timestamp.desc()).limit(10).all()

    return render_template(
        'dashboard.html',
        user=user,
        usage_percent=usage_percent,
        activity=activity_logs
    )

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    api_key = data.get('api_key')
    prompt = data.get('prompt')

    user = User.query.filter_by(api_key=api_key).first()
    
    if not user:
        return jsonify({"status": "error", "message": "Invalid API Key"}), 401
    
    if user.credits_used >= user.credits_total:
        return jsonify({"status": "error", "message": "Insufficient Credits"}), 403

    # Logic: Deduct credits and log the attempt
    user.credits_used += 10 # Cost per generation
    new_log = GenerationLog(user_id=user.id, prompt=prompt, status="Complete")
    db.session.add(new_log)
    db.session.commit()

    return jsonify({
        "status": "success", 
        "message": "Forge sequence initiated", 
        "credits_remaining": user.credits_total - user.credits_used
    })

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080)
