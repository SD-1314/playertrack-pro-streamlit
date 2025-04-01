# SQLite tabanlı, kurulumsuz versiyon (çoklu oyuncu, tarih & antrenman filtresi, yorumlu analiz)

import pytesseract
import fitz  # PyMuPDF
import re
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
import os
import sqlite3
from datetime import datetime, date
import matplotlib.dates as mdates
from PIL import Image

DB_PATH = 'playertrack_pro.db'
RESET_DB = False

# === VERİTABANI VE VERİ YÜKLEME ===
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    if RESET_DB:
        cur.execute("DROP TABLE IF EXISTS performance")
        cur.execute("DROP TABLE IF EXISTS player")

    cur.execute('''
        CREATE TABLE IF NOT EXISTS player (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER,
            date TEXT,
            session_type TEXT,
            session_detail TEXT,
            duration INTEGER,
            total_touches INTEGER,
            left_leg INTEGER,
            right_leg INTEGER,
            distance FLOAT,
            sprint_distance FLOAT,
            work_rate FLOAT,
            accl_decl INTEGER,
            FOREIGN KEY (player_id) REFERENCES player(id)
        )
    ''')
    conn.commit()
    conn.close()

# === PDF OKUMA (Poppler'siz) ===
def pdf_to_images(file_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    return images

def preprocess_image(image):
    image = image.convert('L')
    image = image.point(lambda x: 0 if x < 140 else 255)
    return image

def extract_data_from_pdf(uploaded_file):
    file_name = uploaded_file.name
    match = re.match(r"(.*?) - (Training|Match) (\w+ \d{1,2}) (\d{4})", file_name.strip())

    player_name = match.group(1).strip() if match else "Bilinmeyen"
    session_type = match.group(2) if match else "Antrenman"
    date_part = match.group(3) + " " + match.group(4) if match else date.today().strftime("%b %d %Y")

    images = pdf_to_images(uploaded_file.read())
    text = "\n".join([pytesseract.image_to_string(preprocess_image(img)) for img in images])

    session_detail = 'Genel'
    keywords = {
        'technical': 'Teknik',
        'physical': 'Fiziksel',
        'conditioning': 'Kondisyon',
        'strength': 'Kuvvet'
    }
    for key, label in keywords.items():
        if re.search(key, text, re.IGNORECASE):
            session_detail = label
            break

    duration = int(re.search(r'(\d+)\s*Min\.', text).group(1)) if re.search(r'(\d+)\s*Min\.', text) else 0
    total_touches = int(re.search(r'(\d+)\s*Total Touches', text).group(1)) if re.search(r'(\d+)\s*Total Touches', text) else 0

    leg_match = re.search(r'L\s*(\d+)\s*\|\s*R\s*(\d+)', text)
    left_leg = int(leg_match.group(1)) if leg_match else 50
    right_leg = int(leg_match.group(2)) if leg_match else 50

    distance = float(re.search(r'(\d+\.\d+)\s*Distance Covered', text).group(1)) if re.search(r'(\d+\.\d+)\s*Distance Covered', text) else 0.0
    sprint_distance = float(re.search(r'(\d+\.\d+)\s*Sprint Distance', text).group(1)) if re.search(r'(\d+\.\d+)\s*Sprint Distance', text) else 0.0
    accl_decl = int(re.search(r'(\d+)\s*Accl/Decl', text).group(1)) if re.search(r'(\d+)\s*Accl/Decl', text) else 0
    work_rate = float(re.search(r'(\d+\.\d+)\s*Work Rate', text).group(1)) if re.search(r'(\d+\.\d+)\s*Work Rate', text) else 0.0

    return {
        'date': date_part,
        'session_type': 'Antrenman' if session_type == 'Training' else 'Maç',
        'session_detail': session_detail,
        'duration': duration,
        'total_touches': total_touches,
        'left_leg': left_leg,
        'right_leg': right_leg,
        'distance': distance,
        'sprint_distance': sprint_distance,
        'work_rate': work_rate,
        'accl_decl': accl_decl,
        'player_name': player_name
    }

def get_or_create_player(name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM player WHERE name = ?", (name,))
    result = cur.fetchone()
    if result:
        player_id = result['id']
    else:
        cur.execute("INSERT INTO player (name) VALUES (?)", (name,))
        conn.commit()
        player_id = cur.lastrowid
    conn.close()
    return player_id

def save_to_db(data):
    if not data:
        return

    player_id = get_or_create_player(data['player_name'])
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM performance
        WHERE player_id = ? AND date = ? AND session_type = ?
    """, (player_id, data['date'], data['session_type']))
    if cur.fetchone()[0] > 0:
        conn.close()
        return

    cur.execute('''
        INSERT INTO performance (
            player_id, date, session_type, session_detail, duration, total_touches,
            left_leg, right_leg, distance, sprint_distance, work_rate, accl_decl
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        player_id, data['date'], data['session_type'], data['session_detail'], data['duration'],
        data['total_touches'], data['left_leg'], data['right_leg'], data['distance'],
        data['sprint_distance'], data['work_rate'], data['accl_decl']
    ))
    conn.commit()
    conn.close()

# === STREAMLIT ARAYÜZ ===
def main():
    st.set_page_config(page_title="PlayerTrack Pro", page_icon="⚽", layout="wide")
    st.sidebar.title("📥 PDF Yükleme")
    uploaded_files = st.sidebar.file_uploader("PDF Rapor(lar)ı Seç", type="pdf", accept_multiple_files=True)

    init_db()

    if uploaded_files:
        for uploaded_file in uploaded_files:
            data = extract_data_from_pdf(uploaded_file)
            if data:
                save_to_db(data)
                st.sidebar.success(f"Veri yüklendi: {data['player_name']} - {data['date']}")

    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT pf.*, p.name as player_name
        FROM performance pf
        JOIN player p ON pf.player_id = p.id
    """, conn)
    conn.close()

    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        oyuncular = df['player_name'].unique().tolist()
        detaylar = df[df['session_type'] == 'Antrenman']['session_detail'].unique().tolist()
        oturumlar = df['session_type'].unique().tolist()

        st.sidebar.header("🎯 Filtrele")
        oyuncu_yasi = st.sidebar.number_input("Oyuncu Yaşı", min_value=11, max_value=21, step=1)
        selected_player = st.sidebar.selectbox("Oyuncu Seç", oyuncular)
        selected_type = st.sidebar.multiselect("Antrenman Türü", sorted(set(detaylar)), default=detaylar)
        selected_session = st.sidebar.multiselect("Oturum Türü", oturumlar, default=oturumlar)
        tarih_aralik = st.sidebar.date_input("Tarih Aralığı", [df['date'].min(), df['date'].max()])

        filtered_df = df[
            (df['player_name'] == selected_player) &
            (df['session_detail'].isin(selected_type)) &
            (df['session_type'].isin(selected_session)) &
            (df['date'] >= pd.to_datetime(tarih_aralik[0])) &
            (df['date'] <= pd.to_datetime(tarih_aralik[1]))
        ]

        st.subheader(f"📊 {selected_player} Antrenman Performansı")
        st.dataframe(filtered_df.drop(columns=['player_id']))
    else:
        st.info("Henüz analiz yapılacak veri yok. PDF yükleyin.")

if __name__ == '__main__':
    main()
