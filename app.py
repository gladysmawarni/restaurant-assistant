import os
import warnings
import streamlit as st
import requests


# langchain libraries
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# custom functions
from utils import stream_data, get_context
from maps_function import get_distance_and_review
from gpt_functions import check_response, get_preference, generate_recommendations, further_info

st.set_page_config(page_title="Restaurant Assistant")

### -------- SESSION STATE ---------
if 'memories' not in st.session_state:
    st.session_state.memories = []
if 'preference' not in st.session_state:
    st.session_state.preference = None
if 'location' not in st.session_state:
    st.session_state.location = None
if 'input' not in st.session_state:
    st.session_state.input = None
if 'state' not in st.session_state:
    st.session_state.state = None
if 'options' not in st.session_state:
    st.session_state.options = 0
if 'context' not in st.session_state:
    st.session_state.context = None
if 'london' not in st.session_state:
    st.session_state.london = False
if ('lat' not in st.session_state) or ('lng' not in st.session_state):
    st.session_state.lat = None
    st.session_state.lng = None

# Suppress warnings related to date parsing
warnings.filterwarnings("ignore")

# openai & google maps API key
os.environ['OPENAI_API_KEY'] = st.secrets['OPENAI_API_KEY']
gmap_api = st.secrets['GOOGLE_API_KEY']


# webapp title
st.title('London Restaurant AI Assitant')


### ----------- APP -------------
for memory in st.session_state.memories:
    with st.chat_message(memory["role"]):
        st.write(memory["content"])

if st.session_state.state == None:
    with st.chat_message("assistant"):
        intro = """
                 Hello! I'm here to help you find the perfect restaurant today. \n
                 To get started, could you please let me know your preferences? \n
                 Feel free to mention any specific dietary restrictions or the type of restaurant ambiance you prefer, so I can find the best match for you.
                  \n"""
        st.write(intro)
    # Add intro message to chat history
    st.session_state.memories.append({"role": "assistant", "content": intro})
    st.session_state.state = 'prepare'

# Accept user input
if user_input := st.chat_input("Say Something"):
    st.session_state.input = user_input
    # Add user message to chat history
    st.session_state.memories.append({"role": "user", "content": user_input})
    # Display user message in chat message container
    with st.chat_message("user"):
        st.write(user_input)

if st.session_state.input and (st.session_state.state == 'prepare'):
    st.session_state.preference = get_preference(user_input)

if st.session_state.input and (st.session_state.state == 'location'):
    st.session_state.preference = get_preference(st.session_state.preference + f" preferred location: {user_input}")
    st.session_state.state = 'generate'

if st.session_state.state == 'generate':
    restaurants_context = get_context(st.session_state.preference)
    st.session_state.context = get_distance_and_review(st.session_state.location, restaurants_context)
    if st.session_state.context != False:
        generate_recommendations(st.session_state.context)
        st.session_state.input = None

if st.session_state.input and (st.session_state.state == 'continuation'):
    response = check_response(st.session_state.input)

    if response.lower() == 'other':
        generate_recommendations(st.session_state.context)
        st.session_state.input = None
    if response.lower() == 'preference':
        answer = "\nPlease specify your new preferences"
        st.session_state.memories.append({"role": "assistant", "content": answer})

        with st.chat_message("assistant"):
            st.write_stream(stream_data(answer))

        st.session_state.state = 'prepare'
        st.session_state.input = None
        st.session_state.options = 0
    
    if response.isdigit():
        further_info(st.session_state.context, int(response))
    
    if response.lower() == 'neither':
        answer = "\nI'm sorry, I didn't quite understand. Let me know if you'd like to see other options, set new preferences, or get more details about a specific restaurant."
        st.session_state.memories.append({"role": "assistant", "content": answer})

        with st.chat_message("assistant"):
            st.write_stream(stream_data(answer))




