import time
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
import streamlit as st
from functools import wraps

# Vector DB
embeddings = OpenAIEmbeddings()
faiss_db = FAISS.load_local("faiss_db", embeddings, allow_dangerous_deserialization=True)

def stream_data(response):
    for word in response.split(" "):
        yield word + " "
        time.sleep(0.04)

def get_context(preference):
    # print(preference)
    docs_faiss = faiss_db.similarity_search_with_relevance_scores(preference, k=15)
    return docs_faiss

def off_topic_response(topic):
    # Define response messages and states for each topic
    responses = {
        'preference': {
            "answer": "\nSorry, I didn’t quite catch your dining preference. Could you please rephrase or clarify it?",
            "state": 'prepare'
        },
        'location': {
            "answer": "\nI’m sorry, but I wasn’t able to find your location. Could you please try rephrasing or provide a different address?",
            "state": 'location'
        },
        'far': {
            "answer": "\nIt seems there are no restaurants nearby that match your preferences in our database. Please try entering a different location.",
            "state": 'location'
        },
        'out of range': {
            "answer": "\nPlease pick a number from the restaurants listed above.",
            "state": 'continuation'
        }
    }

    # Get the response data for the provided topic, or return if topic is invalid
    response_data = responses.get(topic)
    if response_data:
        answer = response_data["answer"]
        st.session_state.memories.append({"role": "assistant", "content": answer})
        st.session_state.state = response_data["state"]

        with st.chat_message("assistant"):
            st.write_stream(stream_data(answer))


def retry_on_failure(retries=5, delay=1):
    """
    Decorator that retries a function call up to a specified number of times if it fails.
    
    Parameters:
        retries (int): The number of retry attempts. Default is 5.
        delay (int): Delay (in seconds) between retry attempts. Default is 1 second.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(retries):
                try:
                    # Try to execute the function
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    print(f"Attempt {attempt + 1} failed: {e}")
                    time.sleep(delay)  # Wait before retrying
            # Raise the last exception if all retries failed
            raise last_exception
        return wrapper
    return decorator