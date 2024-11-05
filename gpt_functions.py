from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
import streamlit as st

from utils import stream_data, off_topic_response
from maps_function import get_geolocation, nearest_metro_walk, get_place_info

def check_response(user_input):
    model = ChatOpenAI(model="gpt-4o")
    prompt = f"""
        Based on this input: {user_input}, determine if:
        - It indicates agreement, yes, or if the user wants another options, answer ONLY 'other'
        - It indicates the user wants to choose/set/adjust to another preference, answer ONLY 'preference'
        - If it indicates neither, answer ONLY 'neither'
        - If it is a number, do not change it and answer as it is
        - If it mentions a number, answer ONLY the number
        - Do not answer more than the 1 word / 1 number
    """
    response_text = model.invoke(prompt).content

    return response_text


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
            st.session_state.lat, st.session_state.lng = get_geolocation(st.session_state.location)
            st.session_state.state = 'generate'
            return response_text.replace(st.session_state.location, "") + f" latitude: {st.session_state.lat}, longitude: {st.session_state.lng}"

        else:
            answer = "\nNoted! Can you please tell me your starting point? It can be a specific address or an area."
            st.session_state.memories.append({"role": "assistant", "content": answer})

            with st.chat_message("assistant"):
                st.write_stream(stream_data(answer))

            st.session_state.state = 'location'
            st.session_state.input = None
            return response_text
        
def restaurant_summary(restaurant):
    system = f"""
    You are a polite and professional restaurant recommender assistant. Your task is to suggest restaurants based on user preferences inferred from chat history and context, which includes details about three restaurants (cuisine, location, and distance).

    Instructions:
    - Identify user needs based on chat history (e.g., cuisine type, location).
    - Format responses clearly and professionally, in the style of a restaurant reviewer.
    - All restaurant given should be considered (3 recommendation if there's 3 restaurants)
    - For each restaurant, include and format the answer as following, the number should range between 1-3:
        introduction:
        ## number. The name of the restaurant as a large heading.

        (small italic text)*A description of the restaurant (no more than 5 sentences), do not consider google reviews comments.*
        ---
        Google review: A short and concise summarization of google reviews (if available), end by mentioning the average rating of the last 5 reviews and the relative latest review date (e.g: a week ago), no more than 3 lines
        - Distance from the user’s location.
        - Duration to get there.
        - The transportation fare, skip this if the fare is None
        - Address of the restaurant.
        - The restaurant's instagram  (skip this line if their instagram is not available)
        - After each restaurant insert a "<ig_placeholder>"
    - Keep responses courteous and helpful, without making assumptions beyond the provided data.
    - End by asking if the user would like to see other options or adjust their preferences, or to put the number of the restaurant they want to know more in detail.
    """
    
    # prompt template, format the system message and user question
    TEMPLATE = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            ("system", "Chat history: {chat_history}"),
            ("system", "Here are the restaurants data: {restaurant}"),
            # ("human", "User question: {input}"),
        ]
    )
    prompt = TEMPLATE.format(chat_history= st.session_state.memories, restaurant=restaurant)

    with st.spinner('Fetching information...'):
        model = ChatOpenAI(model="gpt-4o")
        response_text = model.invoke(prompt).content
        st.session_state.memories.append({"role": "assistant", "content": response_text})

    return response_text


def generate_recommendations(context):
    if st.session_state.options <= 2:
        # Define the slice size
        slice_size = 3
        # Calculate the start and end positions based on the index and slice size
        start = st.session_state.options * slice_size
        end = start + slice_size

        restaurants = context[start:end]
        ig_handle = [ig[next(iter(ig))]['Instagram'] for ig in restaurants]
    
        response_text = restaurant_summary(restaurants)
        response_text_list = response_text.split('<ig_placeholder>')
        response_text_list

        with st.chat_message("assistant"):
            for idx, response in enumerate(response_text_list):
                st.write_stream(stream_data(response))
                try:
                    if type(ig_handle[idx]) == str:
                        st.components.v1.iframe(f"{ig_handle[idx].strip('/')}/embed/", height=380, scrolling=True)
                except IndexError:
                    pass
        

        st.session_state.options += 1
        st.session_state.state = 'continuation'

    else:
        answer = "\nI apologize, but I currently don't have any additional recommendations based on your preferences. Please try to specify your preference in more details."
        st.session_state.memories.append({"role": "assistant", "content": answer})

        with st.chat_message("assistant"):
            st.write_stream(stream_data(answer))
        
        st.session_state.state = 'prepare'
        st.session_state.options = 0


def further_info(context, number):
    with st.spinner('Fetching information...'):
        # Define the slice size
        slice_size = 3
        # Calculate the start and end positions based on the index and slice size
        # start = st.session_state.options * slice_size
        start = (st.session_state.options -1) * slice_size
        end = start + slice_size

        try:
            selected = context[start:end][number-1]
        except IndexError:
            off_topic_response('out of range')
            st.session_state.state == 'continuation'
            return False
        
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