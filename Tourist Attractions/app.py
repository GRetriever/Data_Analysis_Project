import streamlit as st
from openai import OpenAI
from pinecone import Pinecone
import requests
import json
from google.oauth2.service_account import Credentials
from google.cloud import translate
import pandas as pd
import folium

openai_client = OpenAI(api_key = st.secrets['OPENAI_API_KEY'])
pc = Pinecone(api_key = st.secrets['PINECONE_API_KEY'])
index = pc.Index('touristattraction')

# ========================================================

with open("./data/google_secret.json") as fr:
    google_secret = json.loads(fr.read())

credentials = Credentials.from_service_account_info(google_secret)
google_translate_client = translate.TranslationServiceClient(credentials=credentials)

def translation(query):
    parent = f"projects/{google_secret['project_id']}/locations/global"
    response = google_translate_client.translate_text(
        request={
            "parent": parent,
            "contents": [query],
            "mime_type": "text/plain",
            "source_language_code": "ko",
            "target_language_code": "en-US",
        }
    )
    return response.translations[0].translated_text

def get_embedding(text_list):
    response = openai_client.embeddings.create(
        input=text_list,
        model = 'text-embedding-3-small',
        dimensions=512
    )
    return [x.embedding for x in response.data]

def recommend(query,구분,지역):
    eng_query = translation(query)
    query_embedding = get_embedding([eng_query])[0]
    results = index.query(
        vector = query_embedding,
        filter = {
            "구분" : {"$in" : [구분]},
            "지역" : {"$in" : [지역]}
        },
        top_k = 3,
        include_metadata = True
    )
    matches = results['matches']
    return [x['metadata'] for x in matches]

def draw_items(items):
    for i,item in enumerate(items):
        with st.expander(f'{i+1}. {item['관광지명']}'):
            st.write(item['catch'])
            col1,col2 = st.columns([0.4,0.6])
            with col1:
                st.image(item['img'])
            with col2:
                st.write(item['description'])

def location(items):
    df = pd.DataFrame()
    for i,item in enumerate(items):
        df.at[i,'관광지명'] = item['관광지명']
        df.at[i,'longitude'] = item['longitude']
        df.at[i,'latitude'] = item['latitude']
    return df

def generate_prompt(query,items):
    item_text = ''
    for i,item in enumerate(items):
        item_text += f'''
추천 결과 : {i+1}
관광지명 : {item['관광지명']}
대분류 : {item['대분류']}
중분류 : {item['중분류']}
소분류 : {item['소분류']}
관광지 설명 : {item['description']}
'''
    item_text = item_text.strip()
    prompt = f'''
유저가 가고 싶은 관광지에 대한 묘사와 이에 대한 추천 결과가 주어집니다.
유저의 입력과 각 추천 결과 관광지명, 분류, 관광지 설명 등을 참고하여 추천사를 작성하세요.
당신에 대한 소개를 먼저 하고, 친절한 말투로 작성해주세요.
이모지를 적절히 사용해주세요.

---
유저 입력 : {query}
---

{item_text}
---
'''.strip()
    return prompt

def request_chat_completion(prompt):
    response = openai_client.chat.completions.create(
        model = 'gpt-3.5-turbo',
        messages = [
            {'role' : 'system', 'content' : '당신은 관광지를 추천해주는 AI 여행지기 트레블즈입니다'},
            {'role' : 'user', 'content' : prompt}
        ],
        stream = True
    )
    return response

def draw_streaming_response(response):
    st.subheader('AI 여행지기의 추천사')
    placeholder = st.empty()
    message = ''
    for chunk in response:
        delta = chunk.choices[0].delta
        if delta.content:
            message += delta.content
            placeholder.markdown(message + "▌")
    placeholder.markdown(message)

# =========================================================
st.title('마 여행지좀 추천해도')

area = ['부산','울산','경남','전남','광주']
p_up = ['숨은 명소','일반 명소']
area_location = {'부산':[35.1709666,129.0360398],'울산':[35.115225,129.042243],'경남':[35.2279728,128.681882],'전남':[34.7604121,127.6622848],'광주':[35.1599785,126.8513072]}

with st.form('form'):
    st.text('입력해라')
    col1,col2 = st.columns(2)
    with col1:
        지역 = st.selectbox(
            '지역',
            area
        )
    with col2:
        구분 = st.selectbox(
            '구분',
            p_up
        )
    query = st.text_input(
        label = '원하는 관광지 특징 입력해라',
        placeholder = 'ex) 사람이 적고 바다가 보이는 전망대'
    )
    submit = st.form_submit_button('제출')
    st.write('좀만 기다리라 와이래 급하노')
if submit:
    if not query:
        st.error('마 도랏나 여행지 특징 적으라고')
        st.stop()
    items = recommend(query,구분,지역)
    prompt = generate_prompt(query,items)
    response = request_chat_completion(prompt)
    draw_streaming_response(response)
    draw_items(items)
    
    map = folium.Map(location=area_location[지역],zoom_start=11)
    for i in range(len(items)):
        folium.Marker(
            [items[i]['latitude'],items[i]['longitude']],
            popup=folium.Popup(items[i]['관광지명'],maxwidth=300),
            fill_opacity=0.5,
            icon=folium.Icon(color='blue',icon_angle=0)
        ).add_to(map)
    st.components.v1.html(map._repr_html_(),width=800,height=800)