import os
import time
import json
import uuid
import requests
import boto3
import google.generativeai as genai
from flask import Flask, render_template, redirect, url_for, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# --- SECRETS ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
LEONARDO_API_KEY = os.environ.get('LEONARDO_API_KEY')
MESHY_API_KEY = os.environ.get('MESHY_API_KEY')

# --- DIGITALOCEAN SPACES CONFIG ---
s3_client = boto3.client(
    's3',
    region_name='nyc3',
    endpoint_url='https://nyc3.digitaloceanspaces.com',
    aws_access_key_id=os.environ.get('DO_SPACES_KEY'),
    aws_secret_access_key=os.environ.get('DO_SPACES_SECRET')
)

# --- GAME LORE ---
GAME_LORE = """
Title: NOVA FORGE
Setting: Post-Apocalyptic Cyberpunk (Year 2140).
"""

genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Database Config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///novaforge.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELS ---

    refined_prompt = db.Column(db.String(1000))
    dimensions_json = db.Column(db.String(500))
# --- HELPER FUNCTIONS ---

def dispatch_to_blender(job_id, prompt, dimensions):
    """Creates a Job JSON and uploads it to the 'queue' folder in Spaces."""
    print(f"Dispatching Job {job_id} to Blender Queue...")
    job_data = {
        "job_id": job_id,
        "output_name": job_id,
        "output_prefix": "novaforge/outputs",
        "prompt": prompt,
        "terrain": {"type": "procedural", "dimensions": dimensions}
    }

    filename = f"{job_id}.json"
    try:
        with open(filename, 'w') as f:
            json.dump(job_data, f)

        s3_client.upload_file(
            filename,
            os.environ.get('DO_SPACES_BUCKET'),
            f"novaforge/queue/{filename}"
        )
        print(f"Job {job_id} successfully uploaded to Queue!")
    except Exception as e:
        print(f"FAILED to dispatch job: {e}")


    print(f"Gemini Processing: {user_prompt}")
    You are the AI Engine for 'NovaForge'.
    CONTEXT: {GAME_LORE}
    TASK: Analyze request '{user_prompt}'.
    OUTPUT JSON: {{
        "refined_prompt": "Lore description...",
        "category": "Prop",
        "complexity": "Low"
        inputs.append(f"Reference: {image_url}")
            inputs,
def generate_meshy(prompt):
    # (Placeholder for Meshy logic if needed later)
    return None
# --- API ROUTES ---


    if not user:
        return jsonify({"error": "Invalid API Key"}), 401

    # 1. GENERATE ID & LOG
    job_id = uuid.uuid4().hex
    # 2. ASK GEMINI
    gemini_data = orchestrate_with_gemini(prompt)
    # 3. DISPATCHER LOGIC
    # For this test, we default to Blender unless it's a Character
    if gemini_data.get('category') == 'Character':
        generate_meshy(refined_prompt)
        worker = "Blender"
        # THIS WAS MISSING BEFORE:
        dispatch_to_blender(job_id, refined_prompt, dims)
    # 4. SAVE LOG

        "job_id": job_id,
        "message": f"Job dispatched to {worker}."

def home():
    return redirect(url_for('dashboard'))

    with app.app_context():
        db.create_all()
        db.session.add(User(
            username="Commander",
            api_key=f"nf_live_{uuid.uuid4().hex[:8]}"
        ))

def generate_meshy(prompt, image_url=None):
    print(f"f528 Meshy Sculpting...")
    headers = {"Authorization": f"Bearer {MESHY_API_KEY}"}
    
    if image_url:
        payload = {"image_url": image_url, "enable_pbr": True}
        endpoint = "https://api.meshy.ai/v1/image-to-3d"
    else:
        payload = {"mode": "preview", "prompt": prompt, "art_style": "realistic"}
        endpoint = "https://api.meshy.ai/v2/text-to-3d"
        
    try:
        res = requests.post(endpoint, headers=headers, json=payload)
        return res.json().get("result")
    except Exception as e:
        print(f"Meshy Error: {e}")
        return None

# --- f680 API ROUTES ---
@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    api_key = data.get('api_key')
    prompt = data.get('prompt')
    user_image = data.get('image_url')
    
    user = User.query.filter_by(api_key=api_key).first()
    if not user: return jsonify({"error": "Invalid API Key"}), 401

    # 1. ASK GEMINI (The Brain)
    gemini_data = orchestrate_with_gemini(prompt, user_image)
    
    refined_prompt = gemini_data['refined_prompt']
    dims = gemini_data['dimensions']
    worker = "Blender"

    # 2. DISPATCHER LOGIC
    # Characters or High Complexity -> Cloud (Meshy)
    if gemini_data['category'] == 'Character' or gemini_data['complexity'] == 'High':
        worker = "Meshy"
        concept_url = generate_concept(refined_prompt) # Leonardo First
        generate_meshy(refined_prompt, concept_url)    # Then Meshy
    else:
        # Props/Terrain -> Local/Paperspace
        pass 

    # 3. SAVE LOG
    log = GenerationLog(
        user_id=user.id,
        original_prompt=prompt,
        refined_prompt=refined_prompt,
        dimensions_json=json.dumps(dims),
        worker_type=worker,
        status="Queued"
    )
    db.session.add(log)
    db.session.commit()
    
    return jsonify({
        "status": "success",
        "worker": worker,
        "dimensions": dims, # Sent to Unity!
        "message": f"Gemini orchestrated. Dispatched to {worker}."
    })

# --- USER ROUTES ---
@app.route('/')
def home(): return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    with app.app_context(): db.create_all()
    user = User.query.first()
    if not user:
        db.session.add(User(username="Commander", api_key=f"nf_live_{uuid.uuid4().hex[:8]}"))
        db.session.commit()
        user = User.query.first()
        
    logs = GenerationLog.query.order_by(GenerationLog.timestamp.desc()).limit(10).all()
    return render_template('dashboard.html', user=user, activity=logs)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
