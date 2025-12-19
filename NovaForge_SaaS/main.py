import os
import requests
import json
import uuid
import time
from flask import Flask, render_template, redirect, url_for, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# --- SECRETS ---
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')       # The Architect (Vision/Math)
GRADIENT_AI_TOKEN = os.environ.get('GRADIENT_AI_TOKEN') # The Narrator (Lore)
GRADIENT_WORKSPACE_ID = os.environ.get('GRADIENT_WORKSPACE_ID')
LEONARDO_API_KEY = os.environ.get('LEONARDO_API_KEY')   # The Concept Artist
MESHY_API_KEY = os.environ.get('MESHY_API_KEY')         # The Hero Builder

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///novaforge.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    api_key = db.Column(db.String(120), unique=True, nullable=False)
    credits_total = db.Column(db.Integer, default=1000)
    credits_used = db.Column(db.Integer, default=0)

class GenerationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    original_prompt = db.Column(db.String(500), nullable=False)
    
    # The "Brains" Output
    refined_prompt = db.Column(db.String(1000)) # From Gradient
    dimensions_json = db.Column(db.String(500)) # From OpenAI (Height/Width)
    
    # The "Visuals" Output
    concept_art_url = db.Column(db.String(500)) # From Leonardo
    result_url = db.Column(db.String(500))      # Final 3D Model
    
    status = db.Column(db.String(50), default="Processing")
    worker_type = db.Column(db.String(20), default="Blender")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# --- 1. THE ARCHITECT (OpenAI GPT-4o) ---
def analyze_dimensions(prompt, image_url=None):
    """Determines height, scale, and layout details."""
    print(f"📐 Architect Analyzing: {prompt}")
    
    messages = [
        {
            "role": "system", 
            "content": """You are a 3D Technical Director. Analyze the request.
            Return a JSON object with:
            - 'height': Estimated height in meters (float).
            - 'width': Estimated width in meters (float).
            - 'category': 'Terrain', 'Prop', or 'Character'.
            - 'complexity': 'High' or 'Low'.
            """
        },
        {"role": "user", "content": prompt}
    ]
    
    if image_url:
        messages[1]["content"] = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]

    try:
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": "gpt-4o", "messages": messages, "response_format": {"type": "json_object"}}
        )
        return res.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"Architect Error: {e}")
        return json.dumps({"height": 1.0, "width": 1.0, "complexity": "Low"})

# --- 2. THE NARRATOR (Gradient / Llama-3) ---
def refine_with_gradient(prompt):
    """Rewrites the prompt to match Game Lore."""
    print(f"📜 Narrator Refining: {prompt}")
    # Placeholder for Gradient Llama-3 call
    # In production, use the Gradient SDK or API endpoint here
    return f"Lore-Accurate: {prompt} with ancient runes and weathered textures."

# --- 3. THE CONCEPT ARTIST (Leonardo) ---
def generate_concept(prompt):
    """Generates a reference image for Meshy to use."""
    print(f"🎨 Painting Concept: {prompt}")
    url = "https://cloud.leonardo.ai/api/rest/v1/generations"
    headers = {"Authorization": f"Bearer {LEONARDO_API_KEY}", "Content-Type": "application/json"}
    
    try:
        # Start Generation
        res = requests.post(url, headers=headers, json={
            "prompt": f"{prompt}, game asset, white background, 3d style",
            "modelId": "6b645e3a-d64f-4341-a6d8-7a3690fbf042", # Phoenix
            "width": 1024, "height": 1024, "num_images": 1
        })
        gen_id = res.json()['sdGenerationJob']['generationId']
        
        # Poll for Result
        time.sleep(8) 
        res = requests.get(f"{url}/{gen_id}", headers=headers)
        return res.json()['generations_by_pk']['generated_images'][0]['url']
    except Exception as e:
        print(f"Leonardo Error: {e}")
        return None

# --- 4. THE HERO BUILDER (Meshy) ---
def generate_meshy(prompt, image_url):
    print(f"✨ Meshy Building from Concept...")
    headers = {"Authorization": f"Bearer {MESHY_API_KEY}"}
    payload = {"mode": "preview", "prompt": prompt, "art_style": "realistic"}
    
    if image_url:
        payload = {"image_url": image_url, "enable_pbr": True}
        endpoint = "https://api.meshy.ai/v1/image-to-3d"
    else:
        endpoint = "https://api.meshy.ai/v2/text-to-3d"
        
    try:
        res = requests.post(endpoint, headers=headers, json=payload)
        return res.json().get("result")
    except Exception as e:
        print(f"Meshy Error: {e}")
        return None

# --- API ROUTES ---
@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    api_key = data.get('api_key')
    prompt = data.get('prompt')
    user_image = data.get('image_url') # User can upload sketch
    
    user = User.query.filter_by(api_key=api_key).first()
    if not user: return jsonify({"error": "Invalid Key"}), 401

    # PHASE 1: BRAINSTORM
    dimensions = analyze_dimensions(prompt, user_image) # OpenAI
    refined_prompt = refine_with_gradient(prompt)       # Gradient
    
    # Parse dimensions to decide worker
    dim_data = json.loads(dimensions)
    worker = "Blender"
    
    # Logic: Complex Characters go to Meshy, Terrain/Props go to Blender
    if dim_data.get('complexity') == 'High' or dim_data.get('category') == 'Character':
        worker = "Meshy"
    
    concept_url = None
    result_id = None
    
    # PHASE 2: EXECUTION
    if worker == "Meshy":
        # Generate Concept Art first (Leonardo)
        concept_url = generate_concept(refined_prompt)
        # Build 3D from Concept (Meshy)
        result_id = generate_meshy(refined_prompt, concept_url)
        
    else:
        # Queue for Paperspace Blender Worker
        # The worker will fetch 'dimensions' to scale the cube/terrain correctly
        worker = "Blender (Paperspace)"
    
    # PHASE 3: SAVE
    log = GenerationLog(
        user_id=user.id,
        original_prompt=prompt,
        refined_prompt=refined_prompt,
        dimensions_json=dimensions,
        concept_art_url=concept_url,
        worker_type=worker,
        status="Queued" if worker == "Blender (Paperspace)" else "Generating"
    )
    db.session.add(log)
    db.session.commit()
    
    return jsonify({
        "status": "success",
        "worker": worker,
        "dimensions": dim_data,
        "message": f"Dispatched to {worker}"
    })

# --- WORKER POLLING (For Paperspace) ---
@app.route('/api/jobs/poll', methods=['GET'])
def poll():
    # Paperspace calls this to find work
    job = GenerationLog.query.filter_by(status="Queued").first()
    if job:
        job.status = "Processing"
        db.session.commit()
        return jsonify({
            "job_id": job.id,
            "prompt": job.refined_prompt,
            "dimensions": json.loads(job.dimensions_json) # Sends Height/Width to Blender!
        })
    return jsonify({"msg": "No jobs"}), 204

@app.route('/')
def home(): return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    with app.app_context(): db.create_all()
    user = User.query.first()
    logs = GenerationLog.query.order_by(GenerationLog.timestamp.desc()).limit(10).all()
    return render_template('dashboard.html', user=user, activity=logs)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
