from flask import Flask, request, jsonify
import json
import os
from flask_cors import CORS
import google.generativeai as genai
from dotenv import load_dotenv

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

# Define the path to the faqs.json file (use the corrected path)
FAQ_FILE_PATH = 'C:/Users/quang/Desktop/Code/Blackbelt/chatbot/faqs.json' # Using the absolute path you confirmed

app = Flask(__name__)
CORS(app)

# Load FAQs when the application starts
faqs_data = []
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
    user_input = request.json.get('query')
    if not user_input:
        return jsonify({'answer': 'Error: No query provided.'}), 400

    answer = get_answer(user_input, faqs_data) # Use the loaded faqs_data and the updated get_answer
    return jsonify({'answer': answer})

@app.route('/')
def index():
    return "Chatbot backend is running."

if __name__ == '__main__':
    # In a production environment, use a production-ready web server like Gunicorn or uWSGI
    # Before deploying, make sure to handle the GOOGLE_API_KEY securely.
    app.run(debug=True) 