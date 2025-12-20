import os 
import re
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

# --- GAME LORE CONTEXT ---
GAME_LORE = """
Title: NOVA FORGE
Setting: Post-Apocalyptic Cyberpunk (Year 2140).
Visual Style: High contrast, neon purple/blue, rusty metal, rain-slicked streets.
Key Factions:
1. The Ascended (High-tech, clean white/gold aesthetics).
2. The Rustborn (Scavengers, improvised tech, messy cables, graffiti).
Current Location: Sector 7 Slums.
"""

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Database Config
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

class GenerationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    original_prompt = db.Column(db.String(500), nullable=False)
    refined_prompt = db.Column(db.String(1000)) 
    dimensions_json = db.Column(db.String(500)) 
    worker_type = db.Column(db.String(20))
    status = db.Column(db.String(50), default="Processing")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# --- GEMINI AGENT: THE BRAIN ---
def orchestrate_with_gemini(user_prompt, image_url=None):
    """
    Gemini acts as BOTH Architect (Math) and Narrator (Lore).
    Returns structured JSON with everything we need.
    """
    print(f"Gemini Processing: {user_prompt}")
    
    model = genai.GenerativeModel('gemini-2.5-flash')

    system_instruction = f"""
    You are the AI Engine for a Unity game called 'NovaForge'.
    
    CONTEXT (GAME LORE):
    {GAME_LORE}
    
    TASK:
    Analyze the user's request: '{user_prompt}'.
    
    1. ARCHITECT (Math): Determine the best physical dimensions for this object in Unity (meters).
    2. NARRATOR (Lore): Rewrite the prompt to fit the visual style of the Lore provided above. Be specific with textures and mood.
    3. DISPATCHER: Decide if this is a 'Character' (complex) or 'Prop/Terrain' (simple).

    OUTPUT FORMAT (JSON ONLY):
    {{
        "refined_prompt": "The lore-accurate description...",
        "dimensions": {{ "height": float, "width": float, "depth": float }},
        "category": "Character" or "Prop" or "Terrain",
        "complexity": "High" or "Low"
    }}
    """
    
    inputs = [system_instruction]
    
    if image_url:
        inputs.append(f"Reference Image URL: {image_url} (Use this for layout/dimensions)")

    try:
        response = model.generate_content(
            inputs, 
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Gemini Error: {e}")
        return {
            "refined_prompt": user_prompt,
            "dimensions": {"height": 1.0, "width": 1.0, "depth": 1.0},
            "category": "Prop",
            "complexity": "Low"
        }

# --- ARTIST AGENTS ---
def generate_concept(prompt):
    """Leonardo AI generates concept art."""
    print(f"Leonardo Painting: {prompt}")
    url = "https://cloud.leonardo.ai/api/rest/v1/generations"
    headers = {"Authorization": f"Bearer {LEONARDO_API_KEY}", "Content-Type": "application/json"}
    
    try:
        res = requests.post(url, headers=headers, json={
            "prompt": f"{prompt}, isolated, 3d render style, game asset, neutral lighting",
            "modelId": "6b645e3a-d64f-4341-a6d8-7a3690fbf042",
            "width": 1024, "height": 1024, "num_images": 1
        })
        gen_id = res.json()['sdGenerationJob']['generationId']
        time.sleep(8)
        res = requests.get(f"{url}/{gen_id}", headers=headers)
        return res.json()['generations_by_pk']['generated_images'][0]['url']
    except Exception as e:
        print(f"Leonardo Error: {e}")
        return None

def generate_meshy(prompt, image_url=None):
    """Meshy AI generates 3D models."""
    print(f"Meshy Sculpting...")
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

    try:
        s3_client.put_object(
            Bucket=os.environ.get('DO_SPACES_BUCKET'),
            Key=f"novaforge/novaforge/queue/{job_id}.json",
            Body=json.dumps(job_data),
            ContentType='application/json'
        )
        print(f"Job {job_id} successfully uploaded to Queue!")
    except Exception as e:
        print(f"FAILED to dispatch job: {e}")

# --- API ROUTES ---
@app.route('/api/generate', methods=['POST'])
def generate():
    print(">>> INCOMING SIGNAL FROM UNITY <<<")
    data = request.json
    api_key = data.get('api_key')
    prompt = data.get('prompt')
    user_image = data.get('image_url')
    
    user = User.query.filter_by(api_key=api_key).first()
    if not user:
        return jsonify({"error": "Invalid API Key"}), 401

    # 1. ASK GEMINI (The Brain)
    gemini_data = orchestrate_with_gemini(prompt, user_image)
    
    refined_prompt = gemini_data['refined_prompt']
    dims = gemini_data['dimensions']
    worker = "Blender"

    # 2. DISPATCHER LOGIC
    if gemini_data['category'] == 'Character' or gemini_data['complexity'] == 'High':
        worker = "Meshy"
        concept_url = generate_concept(refined_prompt)
        generate_meshy(refined_prompt, concept_url)
    else:
        # Readable naming: "glowing blue cube" -> "glowing_blue_cube_1734567890"
        safe_name = re.sub(r'[^a-zA-Z0-9]', '_', prompt)[:30]
        timestamp = int(time.time())
        job_id = f"{safe_name}_{timestamp}"
        dispatch_to_blender(job_id, refined_prompt, dims)

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
        "dimensions": dims,
        "message": f"Job dispatched to {worker}."
    })

# --- USER ROUTES ---
@app.route('/')
def home():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    with app.app_context():
        db.create_all()
        if not User.query.first():
            db.session.add(User(
                username="Commander",
                api_key=f"nf_live_{uuid.uuid4().hex[:8]}",
                credits_total=1000,
                credits_used=0
            ))
            db.session.commit()
    user = User.query.first()
    logs = GenerationLog.query.order_by(GenerationLog.timestamp.desc()).limit(10).all()
    return render_template('dashboard.html', user=user, activity=logs)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
