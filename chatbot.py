import json
import os

# Define the path to the faqs.json file
FAQ_FILE_PATH = 'C:/Users/quang/Desktop/Code/Blackbelt/chatbot/faqs.json'

def load_faqs(file_path):
    """Loads FAQs from a JSON file."""
    if not os.path.exists(file_path):
        print(f"Error: FAQ file not found at {file_path}")
        return None
    with open(file_path, 'r', encoding='utf-8') as f:
        faqs_data = json.load(f)
    return faqs_data.get('faqs', [])

def get_answer(query, faqs):
    """Finds an answer for a given query from the loaded FAQs."""
    # Simple case-insensitive matching for now
    query_lower = query.lower()
    for faq in faqs:
        if query_lower in faq['question'].lower():
            return faq['answer']
    return "Sorry, I couldn't find an answer to your question."

if __name__ == "__main__":
    faqs = load_faqs(FAQ_FILE_PATH)
    if faqs:
        print("Black Belt Prep FAQ Chatbot")
        print("Type 'quit' or 'exit' to end the conversation.")
        while True:
            user_input = input("You: ")
            if user_input.lower() in ['quit', 'exit']:
                break
            answer = get_answer(user_input, faqs)
            print(f"Chatbot: {answer}")
    else:
        print("Failed to load FAQs. Chatbot cannot start.") 