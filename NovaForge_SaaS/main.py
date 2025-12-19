import os
import time
import json
import uuid
import requests
import google.generativeai as genai
from flask import Flask, render_template, redirect, url_for, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# --- f510 SECRETS ---
# Add 'GEMINI_API_KEY' to your Replit Secrets!
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
LEONARDO_API_KEY = os.environ.get('LEONARDO_API_KEY')
MESHY_API_KEY = os.environ.get('MESHY_API_KEY')

# --- f4da GAME LORE CONTEXT ---
# PASTE YOUR ENTIRE GAME DESIGN DOCUMENT HERE (Gemini can handle ~1M tokens)
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

# --- f5c4e0f DATABASE MODELS ---
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

# --- f4ca GEMINI AGENT: THE BRAIN ---
def orchestrate_with_gemini(user_prompt, image_url=None):
    """
    Gemini 1.5 Pro acts as BOTH Architect (Math) and Narrator (Lore).
    It returns a structured JSON with everything we need.
    """
    print(f"f4ca Gemini Processing: {user_prompt}")
    
    # Use 'gemini-1.5-pro' for complex reasoning/vision, or 'gemini-1.5-flash' for speed
    model = genai.GenerativeModel('gemini-1.5-pro')

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
    
    # If user provided a sketch, Gemini "looks" at it
    if image_url:
        inputs.append(f"Reference Image URL: {image_url} (Use this for layout/dimensions)")

    try:
        # Force JSON response
        response = model.generate_content(
            inputs, 
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Gemini Error: {e}")
        # Fallback
        return {
            "refined_prompt": user_prompt,
            "dimensions": {"height": 1.0, "width": 1.0, "depth": 1.0},
            "category": "Prop",
            "complexity": "Low"
        }

# --- f3a8 ARTIST AGENTS (Leonardo & Meshy) ---
def generate_concept(prompt):
    print(f"f3a8 Leonardo Painting: {prompt}")
    url = "https://cloud.leonardo.ai/api/rest/v1/generations"
    headers = {"Authorization": f"Bearer {LEONARDO_API_KEY}", "Content-Type": "application/json"}
    
    try:
        res = requests.post(url, headers=headers, json={
            "prompt": f"{prompt}, isolated, 3d render style, game asset, neutral lighting",
            "modelId": "6b645e3a-d64f-4341-a6d8-7a3690fbf042",
            "width": 1024, "height": 1024, "num_images": 1
        })
        gen_id = res.json()['sdGenerationJob']['generationId']
        time.sleep(8) # Poll wait
        res = requests.get(f"{url}/{gen_id}", headers=headers)
        return res.json()['generations_by_pk']['generated_images'][0]['url']
    except Exception as e:
        print(f"Leonardo Error: {e}")
        return None

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
