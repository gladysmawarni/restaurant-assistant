import streamlit as st
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time



st.title('test')

url = 'https://www.sevenrooms.com/explore/thetamilcrown/reservations/create/search?venues=thetamilcrown%2Cthetamilprince'
# test = requests.get()
# print(test.content)

options = Options()
options.add_argument("--headless")
browser = webdriver.Firefox()
browser.get(url)
time.sleep(3)
browser.save_screenshot('screenie.png')
st.image('screenie.png')
browser.close()