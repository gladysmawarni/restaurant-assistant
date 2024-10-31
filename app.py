import os
import warnings
import streamlit as st
import time
import requests
import json
import numpy as np

# langchain libraries
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate

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

# openai API key
os.environ['OPENAI_API_KEY'] = st.secrets['OPENAI_API_KEY']
gmap_api = st.secrets['GOOGLE_API_KEY']

# webapp title
st.title('London Restaurant AI Assitant')

# Vector DB
embeddings = OpenAIEmbeddings()
faiss_db = FAISS.load_local("faiss_db", embeddings, allow_dangerous_deserialization=True)

### ---------- FUNCTIONS ------------
def stream_data(response):
    for word in response.split(" "):
        yield word + " "
        time.sleep(0.04)

def get_context(preference):
    print(preference)
    docs_faiss = faiss_db.similarity_search_with_relevance_scores(preference, k=15)
    return docs_faiss

def check_response(user_input):
    model = ChatOpenAI(model="gpt-4o")
    prompt = f"""
        Based on this input: {user_input}, determine if:
        - It indicates agreement, yes, or if the user wants another options, answer ONLY 'other'
        - It indicates the user wants to choose/set another preference, answer ONLY 'preference'
        - If it indicates neither, answer ONLY 'neither'
        - If it is a number, do not change it and answer as it is
        - If it mentions a number, answer ONLY the number
        - Do not answer more than the 1 word / 1 number
    """
    response_text = model.invoke(prompt).content

    return response_text


def get_geolocation(place):
    geocoding_url = "https://maps.googleapis.com/maps/api/geocode/json?"
    address = place
    # Define the parameters
    params = {
        "address": address,
        "key": gmap_api, # Replace with your actual API key
    }
    response = requests.get(geocoding_url, params=params)
    geodata=response.json()
    
    latitude = geodata['results'][0]['geometry']['location']['lat']
    longitude = geodata['results'][0]['geometry']['location']['lng']
    return (latitude, longitude)


def get_place_info(place_id):
    url = f"https://places.googleapis.com/v1/places/{place_id}"

    # Define the headers
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Goog-FieldMask": "displayName,formattedAddress,internationalPhoneNumber,priceLevel,reservable,googleMapsUri,websiteUri,regularOpeningHours",
    }

    # Define the headers
    params = {
        "key": gmap_api
    }

    response = requests.get(url, params=params, headers=headers).json()

    restaurant_data = {}
    restaurant_data['restaurant'] = response.get('displayName', {}).get('text', 'N/A')  # Handles missing 'displayName' or 'text'
    restaurant_data['address'] = response.get('formattedAddress', 'N/A')
    restaurant_data['phone number'] = response.get('internationalPhoneNumber', 'N/A')
    restaurant_data['price level'] = response.get('priceLevel', 'N/A')
    restaurant_data['reservable'] = response.get('reservable', 'N/A')
    restaurant_data['google maps uri'] = response.get('googleMapsUri', 'N/A')
    restaurant_data['website uri'] = response.get('websiteUri', 'N/A')
    restaurant_data['open now'] = response.get('regularOpeningHours', {}).get('openNow', 'N/A')  # Handles missing 'regularOpeningHours' or 'openNow'
    restaurant_data['opening hours'] = response.get('regularOpeningHours', {}).get('weekdayDescriptions', 'N/A')  # Handles missing 'weekdayDescriptions'

    return restaurant_data


def nearest_metro_walk(latitude, longitude, destination):
    # Define the URL
    url = "https://places.googleapis.com/v1/places:searchNearby"

    # Define the headers
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": gmap_api, 
        "X-Goog-FieldMask": "*"
    }

    # Define the data payload
    data = {
        "includedTypes": ["subway_station", "light_rail_station", 'train_station', 'transit_station'],
        "maxResultCount": 1,
        "locationRestriction": {
        "circle": {
        "center": {
            "latitude": latitude,
            "longitude": longitude},
        "radius": 1000
        }
    }
    }

    # Make the POST request
    response = requests.post(url, headers=headers, json=data)
    nearest_subway_name = response.json()['places'][0]['displayName']
    nearest_subway_address = response.json()['places'][0]['formattedAddress']
    distance, duration = get_distance(nearest_subway_address, destination)

    return nearest_subway_name, distance, duration


# function in the case the question is not on topic
def off_topic_response(topic):
    if topic == 'preference':
        answer = "\nSorry, I didn’t quite catch your dining preference. Could you please rephrase or clarify it?"
        st.session_state.memories.append({"role": "assistant", "content": answer})
        st.session_state.state = 'prepare'

        with st.chat_message("assistant"):
            st.write_stream(stream_data(answer))
    
    elif topic == 'location':
        answer = "\nI’m sorry, but I wasn’t able to find your location. Could you please try rephrasing or provide a different address?"
        st.session_state.memories.append({"role": "assistant", "content": answer})
        st.session_state.state = 'location'

        with st.chat_message("assistant"):
            st.write_stream(stream_data(answer))
    
    elif topic == 'far':
        answer = "\nIt seems there are no restaurants nearby that match your preferences in our database. Please try entering a different location."
        st.session_state.memories.append({"role": "assistant", "content": answer})
        st.session_state.state = 'location'

        with st.chat_message("assistant"):
            st.write_stream(stream_data(answer))


def get_preference(input):
    system = """
        Your role is to:
        1. Evaluate whether the input relates to dining preferences, food choices, or any dietary restrictions.
        2. Prioritize information based on: food type preference, dietary preference, restaurant type preference, and area/location preference.

        Instructions:
        - Rephrase the user's restaurant or food preference into a clear and concise statement, removing filler words and keeping only relevant information.
        - Prioritize food preference/allergy, put additional information in a bracket. example: vegan restaurant (family-friendly)
        - If the input is unrelated to dining or food preferences, return only "False"
        - Otherwise, return the answer in the format: Preference = user's preference
        - If the input indicate a location also return Location = user's location
        - The location should be cleaned, meaning it should be stripped of filler words such as 'near', 'to', 'in', etc
        """
    
    # prompt template, format the system message and user question
    TEMPLATE = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            ("human", "User question: {input}"),
        ]
      )
    prompt = TEMPLATE.format(input=input)
    
    model = ChatOpenAI(model="gpt-4o")
    response_text = model.invoke(prompt).content

    if response_text.lower() == 'false':
        off_topic_response('preference')
    else:
        if 'location' in response_text.lower():
            st.session_state.location = response_text.split(' = ')[-1]
            st.session_state.lat, st.session_state.lng = get_geolocation(st.session_state.location  if 'london' in st.session_state.location.lower() else st.session_state.location + ', London')
            st.session_state.state = 'generate'
            return response_text.lower() + f" (latitude: {st.session_state.lat}, longitude: {st.session_state.lng})"

        else:
            answer = "\nNoted! Can you please tell me your starting point? It can be a specific address or an area."
            st.session_state.memories.append({"role": "assistant", "content": answer})

            with st.chat_message("assistant"):
                st.write_stream(stream_data(answer))

            st.session_state.state = 'location'
            st.session_state.input = None
            return response_text
        
    
def generate_recommendations(context):
    if st.session_state.options <= 2:
        # Define the slice size
        slice_size = 3
        # Calculate the start and end positions based on the index and slice size
        start = st.session_state.options * slice_size
        end = start + slice_size

        selected = context[start:end]

        system = f"""
        You are a polite and professional restaurant recommender assistant. Your task is to suggest restaurants based on user preferences inferred from chat history and context, which includes details about three restaurants (cuisine, location, and distance).

        Instructions:
        - Identify user needs based on chat history (e.g., cuisine type, location).
        - Format responses clearly and professionally, in the style of a restaurant reviewer.
        - Indicate that choices are based on the nearest distance and user preferences.
        - All restaurant given should be considered (3 recommendation if there's 3 restaurants)
        - For each restaurant, include and format the answer as following, the number should range between 1-3:
            introduction:
            ## number. The name of the restaurant as a large heading.
            [new line] A short and concise description (no more than 3 sentences).
            ---
            Google review: A short and concise summarization of google reviews (if available), end by mentioning the average rating and the relative latest review date (e.g: a week ago)
            - Distance from the user’s location.
            - Duration to get there.
            - The transportation fare, skip this if the fare is None
            - The address of the restaurant.
            - The restaurant's instagram (skip if not available)
            Each separated by new line
        - Keep responses courteous and helpful, without making assumptions beyond the provided data.
        - End by asking if the user would like to see other options or adjust their preferences, or to put the number of the restaurant they want to know more in detail.

        """
        
        # prompt template, format the system message and user question
        TEMPLATE = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                ("system", "Chat history: {chat_history}"),
                ("system", "Here are the restaurants data: {selected}"),
                # ("human", "User question: {input}"),
            ]
        )
        prompt = TEMPLATE.format(chat_history= st.session_state.memories, selected=selected)

        with st.spinner('Fetching information...'):
            model = ChatOpenAI(model="gpt-4o")
            response_text = model.invoke(prompt).content
            st.session_state.memories.append({"role": "assistant", "content": response_text})

        st.session_state.options += 1

        with st.chat_message("assistant"):
            st.write_stream(stream_data(response_text))

        st.session_state.state = 'continuation'

    else:
        answer = "\nI apologize, but I currently don't have any additional recommendations based on your preferences. Please try to specify your preference in more details."
        st.session_state.memories.append({"role": "assistant", "content": answer})

        with st.chat_message("assistant"):
            st.write_stream(stream_data(answer))
        
        st.session_state.state = 'prepare'
        st.session_state.options = 0

def get_distance(start, end):
    # Define the base URL and parameters
    base_url = "https://maps.googleapis.com/maps/api/distancematrix/json"

    # Define the parameters
    params = {
        "destinations": end,
        "origins": start,
        "key": gmap_api,
        "mode": 'walking'
    }

    # Make the request
    response = requests.get(base_url, params=params).json()

    try:
        distance = response['rows'][0]['elements'][0]['distance']['text']
        duration = response['rows'][0]['elements'][0]['duration']['text']
        return distance, duration

    except KeyError:
        off_topic_response('location')
        return False

def get_google_reviews(place_id):
    url = f"https://places.googleapis.com/v1/places/{place_id}"

    # Define the headers
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Goog-FieldMask": "reviews",
    }

    # Define the headers
    params = {
        "key": gmap_api,  # Replace with your actual API key
    }

    response = requests.get(url, params=params, headers=headers)
    data = response.json()['reviews']

    reviews = [{'rating': i['rating'], 'text': i['text']['text'], 'published': i['publishTime'].split('T')[0]} for i in data]

    # turn dictionary to string
    # return [json.dumps(dictionary, ensure_ascii=False) for dictionary in reviews]
    return reviews

def get_distance_and_review(address, context):
    with st.spinner('Fetching information...'):
        final_li = []
        for doc in context:
            context_dict = json.loads(dict(doc[0])['page_content'])
            rest_address = context_dict[next(iter(context_dict))]['Address']
            place_id = context_dict[next(iter(context_dict))]['Place ID']
            
            context_dict['score'] = doc[1]

            # Define the base URL and parameters
            base_url = "https://maps.googleapis.com/maps/api/distancematrix/json"

            # Define the parameters
            params = {
                "destinations": rest_address,
                "origins": address if 'london' in address.lower() else address + ', London',
                "key": gmap_api,
                "mode": 'transit',
                'transit_mode': 'subway'
            }

            # Make the request
            response = requests.get(base_url, params=params).json()

            try:
                context_dict['distance'] = response['rows'][0]['elements'][0]['distance']['text']
                context_dict['duration'] = response['rows'][0]['elements'][0]['duration']['text']
                context_dict['fare'] = response['rows'][0]['elements'][0].get('fare', {}).get('text', None)
                final_li.append(context_dict)

            except KeyError:
                off_topic_response('location')
                return False
            
            try:
                context_dict['google_reviews'] = get_google_reviews(place_id)
            except:
                context_dict['google_reviews'] = 'NA'
            
    # Sort the list first by smallest distance, then by highest score
    sorted_data = sorted(
        final_li,
       key=lambda x: (-x['score'], float(x['distance'].replace(' km', '').replace(' m', '').replace(',', '.'))))

    if np.mean([float(i['distance'].split()[0]) for i in sorted_data]) > 50:
        off_topic_response('far')
        return False
    else:      
        return sorted_data
    
def further_info(context, number):
    with st.spinner('Fetching information...'):
        # Define the slice size
        slice_size = 3
        # Calculate the start and end positions based on the index and slice size
        # start = st.session_state.options * slice_size
        start = (st.session_state.options -1) * slice_size
        end = start + slice_size
        selected = context[start:end][number-1]
        
        restaurant_dict = selected[next(iter(selected))]

        metro_name, distance, duration = nearest_metro_walk(st.session_state.lat, st.session_state.lng, restaurant_dict['Address'])
        restaurant_info = get_place_info(restaurant_dict['Place ID'])
        

        system = f"""
        You are a restaurant reviewer tasked with providing detailed information about a specific restaurant.

        Instructions:
        - Format your response clearly, professionally, and in a friendly tone, including all available data from the context.
        - Avoid adding any information not explicitly provided in the context.
        - Emphasize key details, presenting each piece of information on a new line for better readability.
        - Display the restaurant name in a larger font.
        - Do not prompt the user to ask for additional details.
        - Include the nearest metro name, the distance by walking and estimated duration
        - Conclude by informing the user they can view information about other restaurants by selecting a number, explore more options based on their preferences, or set new preferences.
        """
        
        # prompt template, format the system message and user question
        TEMPLATE = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                ("system", "Here are the restaurants data: {restaurant_info}"),
                ("system", "Here are the nearest metro: {metro_name}, distance: {distance}, and duration by walking: {duration}"),
                # ("human", "User question: {input}"),
            ]
        )
        prompt = TEMPLATE.format( restaurant_info=restaurant_info, metro_name=metro_name, distance=distance, duration=duration)

        # with st.spinner('Fetching information...'):
        model = ChatOpenAI(model="gpt-4o")
        response_text = model.invoke(prompt).content
    
    
    st.session_state.memories.append({"role": "assistant", "content": response_text})
    with st.chat_message("assistant"):
        st.write_stream(stream_data(response_text))



            

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
    st.session_state.location = user_input
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



