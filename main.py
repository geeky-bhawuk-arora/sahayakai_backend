import os
import uuid
import speech_recognition as sr
from gtts import gTTS
import chromadb
from sentence_transformers import SentenceTransformer
from fastapi import FastAPI, Depends, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_
import asr_utils # Hypothetical helper we'll inline logic for simplicity
import io
from pydub import AudioSegment

from database import Base, engine, get_db
from models import UserProfile, Scheme, SessionHistory, Turn

# Create tables if not exists
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Sahayak AI Local Backend")

# Initialize RAG Components
print("Initializing Embedder + VectorDB in backend...")
embedder = SentenceTransformer('all-MiniLM-L6-v2')
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="schemes")

# Local storage for audio files (TTS outputs)
AUDIO_DIR = "audio_outputs"
os.makedirs(AUDIO_DIR, exist_ok=True)


class ProfileCreateReq(BaseModel):
    phone_number: str = None
    name: str = None
    age: int = None
    income: int = None
    state: str = None

@app.post("/conversations")
def create_conversation(req: ProfileCreateReq, db: Session = Depends(get_db)):
    """
    Initializes a new session. If phone_number is provided, links it to a user.
    """
    session_id = str(uuid.uuid4())
    user_id = None
    
    if req.phone_number:
        # Check if user exists, else create
        user = db.query(UserProfile).filter(UserProfile.phone_number == req.phone_number).first()
        if not user:
            user = UserProfile(
                phone_number=req.phone_number,
                name=req.name,
                age=req.age,
                income=req.income,
                state=req.state
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        user_id = user.id

    new_session = SessionHistory(
        user_id=user_id,
        session_id=session_id,
        context={"history": []}
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return {"session_id": session_id, "message": "Conversation started successfully."}


def audio_to_text(audio_bytes: bytes) -> str:
    """Uses SpeechRecognition (Google Web Speech) to transcribe audio. Ensure audio is WAV format first."""
    # Convert incoming webm/ogg (common from browsers) to WAV via pydub
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
        wav_io = io.BytesIO()
        audio.export(wav_io, format="wav")
        wav_io.seek(0)
    except Exception as e:
        print(f"Audio conversion failed: {e}")
        return ""

    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(wav_io) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data) # Uses public Google STT, requires internet. For 100% offline, use Vosk/Whisper.
            return text
    except sr.UnknownValueError:
        return ""
    except Exception as e:
        print(f"STT Error: {e}")
        return f"Error transcribing audio: {str(e)}"

def text_to_audio(text: str, session_id: str, turn_index: int) -> str:
    """Uses gTTS to generate an audio response."""
    tts = gTTS(text=text, lang='en', tld='co.in') # Set to Indian English accent
    filename = f"{session_id}_turn_{turn_index}.mp3"
    filepath = os.path.join(AUDIO_DIR, filename)
    tts.save(filepath)
    return filepath

def generate_local_response(query: str, schemes_context: list, history: list) -> str:
    """Simulates LLM response generation based on retrieved context."""
    # In a full setup, this would call a local model (e.g. Llama 3 via Ollama) 
    # For now, we construct a deterministic but context-rich response.
    if not schemes_context:
        return "I'm sorry, I couldn't find any relevant schemes based on your query."
    
    response = "Based on your query, here is what I found:\n"
    for s in schemes_context:
        response += f"\n- **{s['name']}**: {s['description']}\n  - Eligibility: {s['eligibility_criteria']}\n  - Benefits: {s['benefits']}\n"
        
    response += "\nWould you like to know more about how to apply for any of these?"
    return response

@app.post("/turns")
async def process_turn(
    session_id: str = Form(...),
    text_input: str = Form(None),
    audio_file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    """
    Core orchestrator:
    1. STT (if audio)
    2. Retrieve Context & History
    3. RAG Search inside ChromaDB
    4. Generate Response & action items
    5. TTS Generation
    6. Update DB
    """
    # 1. Input Processing
    user_query = ""
    if audio_file:
        audio_bytes = await audio_file.read()
        user_query = audio_to_text(audio_bytes)
        if not user_query:
            return {"error": "Could not understand audio"}
    elif text_input:
        user_query = text_input
    else:
        raise HTTPException(status_code=400, detail="Must provide either text_input or audio_file")

    # 2. Fetch Session History
    session = db.query(SessionHistory).filter(SessionHistory.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    history_list = session.context.get("history", [])
    turn_index = len(history_list) + 1

    # 3. RAG Search (Vector Similarity)
    query_embedding = embedder.encode(user_query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=3 # Top 3 most relevant schemes
    )
    
    cited_schemes = []
    if results['metadatas'] and len(results['metadatas'][0]) > 0:
        for index, meta in enumerate(results['metadatas'][0]):
            cited_schemes.append({
                "id": meta["id"],
                "name": meta["name"],
                "state": meta["state"],
                "text": results['documents'][0][index]
            })

    # 4. Generate Response
    bot_response = generate_local_response(user_query, cited_schemes, history_list)
    action_items = ["Submit Application", "Check Required Documents"] if cited_schemes else []

    # 5. TTS 
    audio_path = text_to_audio(bot_response, session_id, turn_index)
    
    # 6. Database Update
    new_turn = Turn(
        session_id=session_id,
        user_message=user_query,
        bot_response=bot_response,
        action_items=action_items,
        cited_schemes=cited_schemes
    )
    db.add(new_turn)
    
    # Update context
    history_list.append({"user": user_query, "bot": bot_response})
    session.context = {"history": history_list}
    
    db.commit()
    
    return {
        "user_query": user_query,
        "bot_response": bot_response,
        "action_items": action_items,
        "cited_schemes": cited_schemes,
        "audio_url": f"/audio/{os.path.basename(audio_path)}" # Assume frontend appends base URL
    }


@app.get("/audio/{filename}")
def get_audio(filename: str):
    path = os.path.join(AUDIO_DIR, filename)
    if os.path.exists(path):
        return FileResponse(path, media_type="audio/mpeg")
    raise HTTPException(status_code=404, detail="Audio file not found")


class EligibilityReq(BaseModel):
    age: int = None
    income: int = None
    state: str = None
    occupation: str = None

@app.post("/eligibility/check")
def check_eligibility(req: EligibilityReq, db: Session = Depends(get_db)):
    """
    Deterministic check against the database based on simple profile criteria.
    (In a real app, this logic handles complex rule parsing. Here we do an approximation).
    """
    # Simple deterministic search overriding semantic search
    query = db.query(Scheme)
    
    if req.state:
        query = query.filter(or_(Scheme.state == req.state, Scheme.state == "Central"))
    
    # Fallback to text matching for occupation
    schemes = query.all()
    eligible = []
    
    for s in schemes:
        if req.occupation and req.occupation.lower() in s.tags:
             eligible.append({"id": s.id, "name": s.name, "reason": "Matches occupation tag."})
        elif req.income and req.income < 300000 and "poor" in s.eligibility_criteria.lower():
             eligible.append({"id": s.id, "name": s.name, "reason": "Low income criteria met."})
        # Add more deterministic rules here
             
    return {"eligible_schemes": eligible}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
