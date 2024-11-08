import streamlit as st
import requests
from utils import off_topic_response
import json
import numpy as np

gmap_api = st.secrets['GOOGLE_API_KEY']

def get_geolocation(address):
    geocoding_url = "https://maps.googleapis.com/maps/api/geocode/json?"

    # Define the parameters
    params = {
        "address": address,
        "region": "GB",
        "components": "locality:london|country:GB",
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


def get_google_reviews(place_id):
    url = f"https://places.googleapis.com/v1/places/{place_id}"

    # Define the headers
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Goog-FieldMask": "rating,userRatingCount,reviews",
    }

    # Define the headers
    params = {
        "key": gmap_api,  # Replace with your actual API key
    }

    response = requests.get(url, params=params, headers=headers).json()
    
    reviews_data = response['reviews']
    reviews = [{'rating': i['rating'], 'text': i['text']['text'], 'published': i['publishTime'].split('T')[0]} for i in reviews_data]

    # turn dictionary to string
    # return [json.dumps(dictionary, ensure_ascii=False) for dictionary in reviews]
    return response['rating'], response['userRatingCount'], reviews


def get_distance_and_review(address, context):
    with st.spinner('Fetching information...'):
        final_li = []
        for doc in context:
            try:
                context_dict = json.loads(dict(doc[0])['page_content'])
                rest_address = context_dict[next(iter(context_dict))]['Address']
                place_id = context_dict[next(iter(context_dict))]['Place ID']
            except KeyError:
                continue
            
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


            distance_text = response['rows'][0]['elements'][0].get('distance', {}).get('text', 'NA')
            if distance_text != 'NA':
                # Convert distance to a numeric value (assuming it's in km or m format)
                distance_value = float(distance_text.split()[0])  # Extract numeric part of distance
                
                # Keep only entries with distance <= 2 km
                if distance_value <= 3:
                    context_dict['distance'] = distance_text
                    context_dict['duration'] = response['rows'][0]['elements'][0].get('duration', {}).get('text', 'NA')
                    context_dict['fare'] = response['rows'][0]['elements'][0].get('fare', {}).get('text', None)
                    
                    # Fetch Google reviews
                    try:
                        context_dict['total_rating'], context_dict['rating_counts'], context_dict['google_reviews'] = get_google_reviews(place_id)
                    except:
                        context_dict['total_rating'], context_dict['rating_counts'], context_dict['google_reviews'] = 'NA', 'NA', 'NA'
                    
                    final_li.append(context_dict)
           
            
    # Check the average distance and determine if the response is on-topic
    if not final_li or np.mean([float(str(i['distance']).split()[0]) for i in final_li]) > 50:
        off_topic_response('far')
        return False
    else:
        return final_li
    