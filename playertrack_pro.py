# SQLite tabanlı, kurulumsuz versiyon (çoklu oyuncu, tarih & antrenman filtresi, yorumlu analiz)

import pytesseract
from pdf2image import convert_from_path
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

def reset_database():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS performance")
    cur.execute("DROP TABLE IF EXISTS player")
    conn.commit()
    conn.close()
    st.success("Veritabanı sıfırlandı.")

def preprocess_image(image):
    image = image.convert('L')
    image = image.point(lambda x: 0 if x < 140 else 255)
    return image

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

def extract_data_from_pdf(uploaded_file):
    file_name = uploaded_file.name
    match = re.match(r"(.*?) - (Training|Match) (\w+ \d{1,2}) (\d{4})", file_name.strip())

    player_name = match.group(1).strip() if match else "Bilinmeyen"
    session_type = match.group(2) if match else "Antrenman"
    date_part = match.group(3) + " " + match.group(4) if match else date.today().strftime("%b %d %Y")

    with open("temp.pdf", "wb") as f:
        f.write(uploaded_file.getbuffer())
    images = convert_from_path("temp.pdf", dpi=300)
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
    else:
        session_detail = 'Genel'

    duration = int(re.search(r'(\d+)\s*Min\.', text).group(1)) if re.search(r'(\d+)\s*Min\.', text) else 0
    total_touches = int(re.search(r'(\d+)\s*Total Touches', text).group(1)) if re.search(r'(\d+)\s*Total Touches', text) else 0

    leg_match = re.search(r'L\s*(\d+)\s*\|\s*R\s*(\d+)', text)
    left_leg = int(leg_match.group(1)) if leg_match else 50
    right_leg = int(leg_match.group(2)) if leg_match else 50

    distance = float(re.search(r'(\d+\.\d+)\s*Distance Covered', text).group(1)) if re.search(r'(\d+\.\d+)\s*Distance Covered', text) else 0.0
    sprint_distance = float(re.search(r'(\d+\.\d+)\s*Sprint Distance', text).group(1)) if re.search(r'(\d+\.\d+)\s*Sprint Distance', text) else 0.0
    accl_decl = int(re.search(r'(\d+)\s*Accl/Decl', text).group(1)) if re.search(r'(\d+)\s*Accl/Decl', text) else 0
    work_rate = float(re.search(r'(\d+\.\d+)\s*Work Rate', text).group(1)) if re.search(r'(\d+\.\d+)\s*Work Rate', text) else 0.0

    if os.path.exists("temp.pdf"):
        os.remove("temp.pdf")

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

def main():
    st.set_page_config(page_title="PlayerTrack Pro", layout="wide")
    st.title("📊 PlayerTrack Pro")

    st.sidebar.title("📤 PDF Veri Yükle")
    if st.sidebar.button("Veritabanını Sıfırla"):
        reset_database()
        st.rerun()

    init_db()

    uploaded_files = st.file_uploader("PDF Raporlarını Seçin", type="pdf", accept_multiple_files=True)
    if uploaded_files:
        for uploaded_file in uploaded_files:
            data = extract_data_from_pdf(uploaded_file)
            if data:
                save_to_db(data)
                st.success(f"Veri yüklendi: {data['player_name']} - {data['date']} - {data['session_type']} [{data['session_detail']}]")

if __name__ == "__main__":
    main()

