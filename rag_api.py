import PyPDF2
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import openai
import textwrap
import re
from fastapi import FastAPI, Request, Form, File, UploadFile
from pydantic import BaseModel
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import os
from evaluate import load

bertscore = load("bertscore")

openai.api_key = "**"  # <-- Replace with your OpenAI API key

app = FastAPI()
# Create directories if they don't exist
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- PDF and RAG setup (run once at startup) ---

def extract_text_from_pdf(pdf_path):
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

def split_text(text, chunk_size=500):
    words = text.split()
    return [' '.join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]

def embed_chunks(chunks, model):
    return model.encode(chunks, convert_to_numpy=True)

def build_faiss_index(embeddings):
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)
    return index

def retrieve(query, model, index, chunks, embeddings, top_k=3):
    query_vec = model.encode([query], convert_to_numpy=True)
    D, I = index.search(query_vec, top_k)
    return [chunks[i] for i in I[0]], I[0]

def generate_answer(context, query):
    prompt = f"Use the following context to answer the question:\n\nContext:\n{context}\n\nQuestion: {query}\nAnswer:"
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()

def recommend_question(following_text):
    prompt = (
    f"""You are a curious chatbot that comes up with questions from the provided context {following_text}.
            Suggest a question to the user in the form: Do you want to know why, what, etc."""
    )
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()

def clean_followup_question(question):
    # Patterns to match common pretexts
    pretext_patterns = [
        r"^(Do|Would|Did|Are|Can|Could|Will|Shall|May|Might|Should|Have|Has|Had)\s+you\s+(want|like|wish|care)\s+to\s+know\s+",  # e.g., Do you want to know
        r"^(Do|Would|Did|Are|Can|Could|Will|Shall|May|Might|Should|Have|Has|Had)\s+you\s+want\s+to\s+learn\s+",
        r"^(Do|Would|Did|Are|Can|Could|Will|Shall|May|Might|Should|Have|Has|Had)\s+you\s+wish\s+to\s+know\s+",
        r"^(Do|Would|Did|Are|Can|Could|Will|Shall|May|Might|Should|Have|Has|Had)\s+you\s+want\s+to\s+find\s+out\s+",
        r"^(Do|Would|Did|Are|Can|Could|Will|Shall|May|Might|Should|Have|Has|Had)\s+you\s+want\s+to\s+see\s+",
        r"^(Do|Would|Did|Are|Can|Could|Will|Shall|May|Might|Should|Have|Has|Had)\s+you\s+want\s+to\s+understand\s+",
    ]
    # Remove pretext
    for pattern in pretext_patterns:
        question = re.sub(pattern, '', question, flags=re.IGNORECASE)
    # Remove leading "about" or "more about"
    question = re.sub(r"^(about|more about)\s+", '', question, flags=re.IGNORECASE)
    # Capitalize first letter
    question = question.strip()
    if question and not question[0].isupper():
        question = question[0].upper() + question[1:]
    # Ensure it ends with a question mark
    if question and not question.endswith('?'):
        question += '?'
    return question

def wrap_text(text, width=130):
    return '\n'.join(textwrap.wrap(text, width=width))

# Global variables
model = SentenceTransformer('all-MiniLM-L6-v2')
chunks = []
embeddings = None
index = None
cache = {}
pdf_loaded = False

class ChatRequest(BaseModel):
    question: str
    use_followup: bool = False
    followup_text: str = None

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "pdf_loaded": pdf_loaded})

@app.post("/upload-pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    global chunks, embeddings, index, pdf_loaded, cache

    # Save the uploaded file
    file_path = f"uploads/{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    # Process the PDF
    text = extract_text_from_pdf(file_path)
    chunks = split_text(text)
    embeddings = embed_chunks(chunks, model)
    index = build_faiss_index(np.array(embeddings))
    pdf_loaded = True
    cache = {}  # Clear cache when new PDF is loaded
    
    return {"filename": file.filename, "status": "PDF processed successfully"}

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    global cache

    if not pdf_loaded:
        return {"answer": "Please upload a PDF document first.", "followup": None}

    if req.use_followup and req.followup_text:
        query = clean_followup_question(req.followup_text)
    else:
        query = req.question.strip()
    if query.lower() == 'exit':
        return {"answer": "Goodbye!", "followup": None}

    # Check cache first
    try:
        bertscore_list = bertscore.compute(predictions = [query]*len(cache),
                                references = list(cache.keys()),
                                lang = 'en', model_type="distilbert-base-uncased")
    except:
        bertscore_list = {'f1': [0]}

    if max(bertscore_list['f1']) > 0.95:
        response_index = np.argmax(bertscore_list['f1'])
        cached_response = list(cache.values())[response_index]
        print('from cache')
        answer = cached_response[0]
        followup = cached_response[1]
    else:
        relevant_chunks, chunk_indices = retrieve(query, model, index, chunks, embeddings)
        context = "\n\n".join(relevant_chunks)
        answer = generate_answer(context, query)
        last_chunk_id = chunk_indices[-1]
        next_chunks = []
        for i in range(1, 4):
            next_id = last_chunk_id + i
            if next_id < len(chunks):
                next_chunks.append(chunks[next_id])
        followup_context = "\n\n".join(next_chunks)
        if followup_context.strip():
            followup = recommend_question(followup_context)
        else:
            followup = None
        cache[query] = (answer, followup)

    return {
        "answer": wrap_text(answer),
        "followup": followup
    }

if __name__ == "__main__":
    uvicorn.run("rag_api:app", host="127.0.0.1", port=8080, reload=True)
