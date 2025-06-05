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
from email.message import EmailMessage
import smtplib
from datetime import datetime, time
from pytz import timezone # Import timezone from pytz

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

# Email Configuration
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_PORT = os.getenv('EMAIL_PORT')
EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
SUPPORT_EMAIL = os.getenv('SUPPORT_EMAIL', 'info@blackbelttestprep.com') # Default to support email
SUPPORT_WEBHOOK_URL = os.getenv('SUPPORT_WEBHOOK_URL')

# Define the path to the faqs.json file (use the corrected path)
FAQ_FILE_PATH = './faqs.json' # Use the relative path from chatbot/ to the root faqs.json

# In-memory storage for conversation state (for demonstration)
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

def extract_name_from_text(text):
    """Attempts to extract a name from the text. This is a very basic implementation and might need refinement.
    It looks for capitalized words that are not common English words (e.g., pronouns, prepositions).
    This can be improved with more sophisticated NLP techniques if needed.
    """
    # Split the text into words and filter for capitalized words
    words = re.findall(r'\b[A-Z][a-z]*\b', text)
    # Filter out common short words that are often capitalized at sentence start
    common_words = {'I', 'A', 'The', 'And', 'Or', 'But', 'For', 'Nor', 'On', 'At', 'To', 'By', 'With'}
    name_candidates = [word for word in words if word not in common_words]
    
    # A very simple heuristic: if there are multiple capitalized words, join them as a name.
    # Otherwise, it might be just a capitalized word at the start of a sentence.
    if len(name_candidates) > 1:
        return " ".join(name_candidates)
    elif len(name_candidates) == 1 and len(name_candidates[0]) > 2: # Avoid single-letter or two-letter words
        return name_candidates[0]
    return None

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

def is_working_hours():
    """Checks if the current time is within working hours (9 AM - 12 PM and 1 PM - 5:30 PM ET)."""
    # Define the Eastern Timezone
    eastern_time = timezone('America/New_York')
    now_et = datetime.now(eastern_time)
    current_time = now_et.time()
    
    # Define working hour ranges
    morning_start = time(9, 0)  # 9:00 AM
    morning_end = time(12, 0)   # 12:00 PM (noon)
    afternoon_start = time(13, 0) # 1:00 PM
    afternoon_end = time(17, 30)  # 5:30 PM
    
    # Check if current time is within either range
    in_morning_hours = morning_start <= current_time <= morning_end
    in_afternoon_hours = afternoon_start <= current_time <= afternoon_end
    
    return in_morning_hours or in_afternoon_hours

def send_support_email(user_query: str, user_email: str | None = None, user_name: str | None = None):
    """Saves an email to the database."""
    if not all([EMAIL_HOST, EMAIL_PORT, EMAIL_USERNAME, EMAIL_PASSWORD]):
        print("Email sending is not fully configured (missing env vars).")
        return

    subject = "Unanswered Chatbot Question"
    if user_email:
        subject += f" from {user_email}"
    if user_name:
        subject += f" ({user_name})"
    
    body = f"The following user query could not be answered by the chatbot:\n\nUser Query: {user_query}\n\n"
    if user_email:
        body += f"User's Email (if provided): {user_email}\n"
    if user_name:
        body += f"User's Name (if provided): {user_name}\n"

    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_USERNAME
    msg['To'] = SUPPORT_EMAIL

    try:
        # Ensure port is an integer
        port = int(EMAIL_PORT)
        # Use SMTP and starttls for a more common secure connection
        with smtplib.SMTP(EMAIL_HOST, port) as smtp:
            smtp.starttls() # Upgrade the connection to a secure TLS connection
            smtp.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"Support email sent for query: {user_query}")
    except Exception as e:
        print(f"Failed to send support email: {e}")

@app.route('/ask', methods=['POST'])
def ask_chatbot():
    data = request.json
    user_input = data.get('query')
    session_id = data.get('session_id', 'default_session') 

    if not user_input:
        return jsonify({'answer': 'Error: No query provided.'}), 400

    print(f"Received user input: {user_input}") # Debug print

    extracted_email = extract_email_from_text(user_input)
    print(f"Extracted email: {extracted_email}") # Debug print

    # Check if the bot is waiting for contact information for this session
    session_context = conversation_state.get(session_id, {})

    if session_context.get('waiting_for_contact'):
        user_name = extract_name_from_text(user_input)
        user_email = extract_email_from_text(user_input)

        if user_name and user_email:
            original_query = session_context.get('original_query', 'N/A')
            send_support_email(original_query, user_email, user_name)
            del conversation_state[session_id] # Clear state after sending
            return jsonify({'answer': "Thank you for providing your information. Your question has been forwarded to info@blackbelttestprep.com, and we will get back to you as soon as possible."})
        elif "no" in user_input.lower() or "don't want to share" in user_input.lower():
            del conversation_state[session_id]
            return jsonify({'answer': "Understood. I cannot forward your question without your contact information."})
        else:
            return jsonify({'answer': "I still need your name and email to forward your question. Please provide them."})

    # If no email was extracted in the current turn, or if the email was handled (and returned for subscription),
    # proceed with regular FAQ answering using the LLM.
    if extracted_email:
        if save_email(extracted_email):
            # In a real app, generate a unique code and store it associated with the email
            discount_code = "BBTPOFF5"
            return jsonify({'answer': f"Thank you for subscribing! Here is your $5 discount code: **{discount_code}**. You can now ask me questions about the FAQs."})
        else:
            # Email was already collected, or there was a file saving error
            # If already collected, acknowledge it and let them ask questions.
            return jsonify({'answer': "It looks like that email has already been subscribed. You can now ask me questions about the FAQs."})

    answer = get_answer(user_input, faqs_data) # Use the loaded faqs_data and the updated get_answer

    # Check if the answer indicates an inability to find information
    # and prompt for contact info if so.
    unanswered_phrases = [
        "cannot find an answer",
        "couldn't generate a response",
        "encountered an error",
        "visit the contact page"
    ]
    
    # Check if any of the unanswered phrases are in the answer, case-insensitively
    if any(phrase in answer.lower() for phrase in unanswered_phrases):
        # Store the original query and set flag to wait for contact info
        conversation_state[session_id] = {
            'waiting_for_contact': True,
            'original_query': user_input
        }
        return jsonify({'answer': "I cannot find an answer to your question in our FAQs. To forward your question to our support team, please provide your name and email address."})

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