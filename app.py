from flask import Flask, request, jsonify
import json
import os
from flask_cors import CORS
import google.generativeai as genai
from dotenv import load_dotenv
import re
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# Load environment variables from .env file
load_dotenv()

# Configure Generative AI
API_KEY = os.getenv('GOOGLE_API_KEY')
if not API_KEY:
    print("Error: GOOGLE_API_KEY not found in .env file.")
    # Handle this error appropriately in a real application
    # For now, we'll just print and proceed, but the LLM part won't work.
else:
    genai.configure(api_key=API_KEY)
    # Choose a model
    generation_config = {
        "temperature": 0.5,
        "top_p": 1,
        "top_k": 1,
        "max_output_tokens": 2048,
    }
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash-preview-05-20", # Or another suitable model
        generation_config=generation_config,
    )

app = Flask(__name__)
CORS(app)

# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("Error: DATABASE_URL not found in .env file.")
    # Handle this error appropriately, maybe exit or disable email collection
    # For now, we'll print and proceed, but email saving won't work.
    db_engine = None
else:
    db_engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base = declarative_base()

    # Define the Email model
    class Email(Base):
        __tablename__ = "emails"

        id = Column(Integer, primary_key=True, index=True)
        email = Column(String, unique=True, index=True)

    # Create database tables (if they don't exist)
    Base.metadata.create_all(bind=db_engine)

# Define the path to the faqs.json file (use the corrected path)
FAQ_FILE_PATH = './faqs.json' # Use the relative path from chatbot/ to the root faqs.json

# In-memory storage for conversation state (for demonstration)
# In production, use a database (e.g., SQLite, PostgreSQL)
conversation_state = {}

# Remove file-based email storage
# In-memory storage for collected emails (for demonstration)
# In production, use a secure database
# collected_emails = set()
# Define a file path for storing emails (for demonstration)
# EMAIL_STORAGE_FILE = 'collected_emails.txt'

# Remove file-based email loading
# Load existing emails from file on startup (basic)
# if os.path.exists(EMAIL_STORAGE_FILE):
#     with open(EMAIL_STORAGE_FILE, 'r') as f:
#         for line in f:
#             collected_emails.add(line.strip())

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def save_email(email: str):
    """Saves an email to the database."""
    if not db_engine:
        print("Database engine not configured, cannot save email.")
        return False

    db = SessionLocal()
    try:
        # Check if email already exists
        existing_email = db.query(Email).filter(Email.email == email).first()
        if existing_email:
            print(f"Email already collected: {email}")
            return False # Indicates email was already present

        # Add new email
        new_email = Email(email=email)
        db.add(new_email)
        db.commit()
        db.refresh(new_email)
        print(f"Email saved to database: {email}")
        return True # Indicates a new email was saved
    except Exception as e:
        db.rollback()
        print(f"Error saving email to database: {e}")
        return False
    finally:
        db.close()

def extract_email_from_text(text):
    """Searches for and returns the first valid email address found in the text."""
    # A simple regex to find an email pattern anywhere in the text
    email_regex = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    match = re.search(email_regex, text)
    if match:
        return match.group(0)
    return None

def extract_url_from_text(text):
    """Searches for and returns all valid URLs found in the text."""
    # A simple regex to find URLs. This regex might need refinement depending on the exact URL formats expected.
    url_regex = r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s]*'
    return re.findall(url_regex, text)

def load_faqs(file_path):
    """Loads FAQs from a JSON file."""
    if not os.path.exists(file_path):
        print(f"Error: FAQ file not found at {file_path}")
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        faqs_data = json.load(f)
    return faqs_data.get('faqs', [])

faqs_data = load_faqs(FAQ_FILE_PATH)

def get_answer(query, faqs):
    """Finds an answer for a given query using the LLM and FAQs."""
    if not API_KEY:
        return "Sorry, the chatbot is not configured correctly (API key missing)."
        
    # Format FAQs for the prompt
    faqs_text = ""
    for faq in faqs:
        faqs_text += f"Q: {faq['question']}\nA: {faq['answer']}\n\n"

    # Create the prompt for the LLM
    prompt = f"""You are a helpful AI assistant for the Black Belt Test Prep question bank. 
    Your goal is to answer user questions based *only* on the following list of Frequently Asked Questions (FAQs).
    If a user asks a question that cannot be answered from the provided FAQs, politely state that you cannot find the answer in the FAQ and suggest they visit the contact page.

    Here are the FAQs:
    {faqs_text}

    User Question: {query}

    Based *only* on the FAQs provided, please answer the User Question:
    Chatbot Answer:"""

    try:
        response = model.generate_content(prompt)
        # Check if the response has content and extract the text
        if response and response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
             # Join the text parts of the response
            return "".join(part.text for part in response.candidates[0].content.parts)
        else:
            return "Sorry, I couldn't generate a response at this time."

    except Exception as e:
        print(f"Error generating response: {e}")
        return "Sorry, I encountered an error while trying to find an answer."

@app.route('/ask', methods=['POST'])
def ask_chatbot():
    data = request.json
    user_input = data.get('query')
    # Removed session_id and conversation_state as they are no longer needed for this email handling logic
    # session_id = data.get('session_id', 'default_session') 

    if not user_input:
        return jsonify({'answer': 'Error: No query provided.'}), 400

    print(f"Received user input: {user_input}") # Debug print

    extracted_email = extract_email_from_text(user_input)
    print(f"Extracted email: {extracted_email}") # Debug print

    if extracted_email:
        if save_email(extracted_email):
            # In a real app, generate a unique code and store it associated with the email
            discount_code = "BBTPOFF5"
            return jsonify({'answer': f"Thank you for subscribing! Here is your $5 discount code: **{discount_code}**. You can now ask me questions about the FAQs."})
        else:
            # Email was already collected, or there was a file saving error
            # If already collected, acknowledge it and let them ask questions.
            return jsonify({'answer': "It looks like that email has already been subscribed. You can now ask me questions about the FAQs."})
    
    # If no email was extracted, or if the email was handled (and returned),
    # proceed with regular FAQ answering using the LLM.
    answer = get_answer(user_input, faqs_data) # Use the loaded faqs_data and the updated get_answer
    
    # Extract URLs from the answer
    urls = extract_url_from_text(answer)

    # Return the answer and the extracted URLs
    return jsonify({'answer': answer, 'urls': urls})

@app.route('/')
def index():
    return "Chatbot backend is running."

# if __name__ == '__main__':
#     # In a production environment, use a production-ready web server like Gunicorn or uWSGI
#     # Before deploying, make sure to handle the GOOGLE_API_KEY and email storage securely.
#     # app.run(debug=True) 