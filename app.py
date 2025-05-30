from flask import Flask, request, jsonify
import json
import os
from flask_cors import CORS

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
    """Finds an answer for a given query from the loaded FAQs."""
    # Simple case-insensitive matching for now
    query_lower = query.lower()
    for faq in faqs:
        if query_lower in faq['question'].lower():
            return faq['answer']
    return "Sorry, I couldn't find an answer to your question."

@app.route('/ask', methods=['POST'])
def ask_chatbot():
    user_input = request.json.get('query')
    if not user_input:
        return jsonify({'answer': 'Error: No query provided.'}), 400

    answer = get_answer(user_input, faqs_data) # Use the loaded faqs_data
    return jsonify({'answer': answer})

@app.route('/')
def index():
    return "Chatbot backend is running."

if __name__ == '__main__':
    # In a production environment, use a production-ready web server like Gunicorn or uWSGI
    app.run(debug=True) 