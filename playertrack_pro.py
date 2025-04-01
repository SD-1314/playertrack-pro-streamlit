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

    # Kayıt varsa tekrar etme
    cur.execute("""
        SELECT COUNT(*) FROM performance
        WHERE player_id = ? AND date = ? AND session_type = ?
    """, (player_id, data['date'], data['session_type']))
    if cur.fetchone()[0] > 0:
        conn.close()
        return
    cur = conn.cursor()
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
    st.set_page_config(page_title="PlayerTrack Pro", page_icon="⚽", layout="wide")
    st.sidebar.title("⚙️ Ayarlar")
    if st.sidebar.button("🧨 Verileri Sıfırla"):
        reset_database()
        st.rerun()

    st.title("⚽ PlayerTrack Pro - Gelişmiş Performans Takibi")
    init_db()

    uploaded_files = st.file_uploader("📤 PDF Rapor(lar)ı Yükle", type="pdf", accept_multiple_files=True)
    if uploaded_files:
        for uploaded_file in uploaded_files:
            data = extract_data_from_pdf(uploaded_file)
            if data:
                save_to_db(data)
                st.success(f"Veri yüklendi: {data['player_name']} - {data['date']}")

    st.markdown("---")
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

        st.sidebar.header("🎯 Filtrele")
        oyuncu_yasi = st.sidebar.number_input("Oyuncu Yaşı", min_value=11, max_value=21, step=1)
        selected_player = st.sidebar.selectbox("Oyuncu Seç", oyuncular)
        selected_type = st.sidebar.multiselect("Antrenman Türü", sorted(set(detaylar)), default=detaylar)
        tarih_aralik = st.sidebar.date_input("Tarih Aralığı", [df['date'].min(), df['date'].max()])

        filtered_df = df[
            (df['player_name'] == selected_player) &
            (df['session_detail'].isin(selected_type)) &
            (df['date'] >= pd.to_datetime(tarih_aralik[0])) &
            (df['date'] <= pd.to_datetime(tarih_aralik[1]))
        ]

        training_df = filtered_df[filtered_df['session_type'] == 'Antrenman']
        match_df = filtered_df[filtered_df['session_type'] == 'Maç']

        st.subheader(f"📈 {selected_player} Performansı - Antrenmanlar")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Seans", len(training_df))
        col2.metric("Ort. Sprint (m)", f"{training_df['sprint_distance'].mean():.1f}")
        col3.metric("Sol Bacak (%)", f"{training_df['left_leg'].mean():.1f}")
        col4.metric("Mesafe (km)", f"{training_df['distance'].mean():.1f}")

        with st.expander("📊 Antrenman Grafikler"):
            metric_options = {
                "sprint_distance": "Sprint Mesafesi (m)",
                "distance": "Toplam Mesafe (km)",
                "duration": "Süre (dk)",
                "total_touches": "Toplam Dokunuş",
                "work_rate": "Çalışma Oranı (m/dk)",
                "accl_decl": "İvmelenme/Sert Duruş"
            }
            selected_metric_key = st.selectbox("İncelenecek Metriği Seç", list(metric_options.keys()), format_func=lambda x: metric_options[x], key="training_metric")

            fig, ax = plt.subplots(figsize=(12, 5))
            ax.plot(training_df['date'], training_df[selected_metric_key], marker='o', linewidth=2)
            ax.set_title(f"{metric_options[selected_metric_key]} Zaman Serisi", fontsize=14)
            ax.set_xlabel("Tarih")
            ax.set_ylabel(metric_options[selected_metric_key])
            ax.grid(True, linestyle='--', alpha=0.5)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            fig.autofmt_xdate()
            st.pyplot(fig)

            fig2, ax2 = plt.subplots()
            left_avg = filtered_df['left_leg'].mean()
            right_avg = filtered_df['right_leg'].mean()

            if pd.notna(left_avg) and pd.notna(right_avg):
                wedges, texts, autotexts = ax2.pie([
                    left_avg,
                    right_avg
                ], labels=['Sol Bacak', 'Sağ Bacak'], autopct='%1.1f%%', explode=(0.05, 0), startangle=90, textprops={'fontsize': 12})
                ax2.axis('equal')
                ax2.set_title("Bacak Kullanım Oranı", fontsize=14)
                st.pyplot(fig2)

            st.markdown("### 📈 Hareketli Ortalama")
            if not training_df.empty:
                rolling_df = training_df.set_index('date')[selected_metric_key].rolling(window=3, min_periods=1).mean()
                fig_roll, ax_roll = plt.subplots(figsize=(12, 4))
                ax_roll.plot(training_df['date'], training_df[selected_metric_key], label='Günlük', marker='o')
                ax_roll.plot(training_df['date'], rolling_df, label='3 Günlük Ortalama', linestyle='--')
                ax_roll.set_title(f"{metric_options[selected_metric_key]} - Hareketli Ortalama")
                ax_roll.set_xlabel("Tarih")
                ax_roll.set_ylabel(metric_options[selected_metric_key])
                ax_roll.legend()
                ax_roll.grid(True, linestyle='--', alpha=0.6)
                ax_roll.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
                fig_roll.autofmt_xdate()
                st.pyplot(fig_roll)

            st.markdown("### 🔥 Haftalık Isı Haritası")
            if not training_df.empty:
                heat_df = training_df.copy()
                heat_df['Hafta'] = heat_df['date'].dt.strftime('%Y-%U')
                weekly_avg = heat_df.groupby('Hafta')[selected_metric_key].mean().reset_index()
                pivot = weekly_avg.pivot_table(index='Hafta', values=selected_metric_key)
                fig_hm, ax_hm = plt.subplots(figsize=(10, 2))
                im = ax_hm.imshow([pivot[selected_metric_key].fillna(0).tolist()], cmap='Oranges', aspect='auto')
                ax_hm.set_yticks([0])
                ax_hm.set_yticklabels([metric_options[selected_metric_key]])
                ax_hm.set_xticks(range(len(pivot.index)))
                ax_hm.set_xticklabels(pivot.index, rotation=45)
                ax_hm.set_title("Haftalık Ortalama Performans")
                fig_hm.colorbar(im, orientation='vertical')
                st.pyplot(fig_hm)
            else:
                st.warning("Bacak kullanım verileri yetersiz.")

        with st.expander("📋 Antrenman Verileri"):
            st.dataframe(
                training_df.drop(columns=['player_id']).rename(columns={
                    "date": "Tarih",
                    "session_type": "Oturum Türü",
                    "session_detail": "Antrenman Detayı",
                    "duration": "Süre (dk)",
                    "total_touches": "Toplam Dokunuş",
                    "left_leg": "Sol Bacak (%)",
                    "right_leg": "Sağ Bacak (%)",
                    "distance": "Mesafe (km)",
                    "sprint_distance": "Sprint Mesafesi (m)",
                    "work_rate": "Çalışma Oranı (m/dk)",
                    "accl_decl": "İvmelenme/Sert Duruş",
                    "player_name": "Oyuncu"
                }),
                use_container_width=True
            )
            st.download_button("⬇️ CSV İndir", training_df.to_csv(index=False).encode('utf-8'), file_name=f"{selected_player}_antrenman.csv")

        with st.expander("🧠 Yorumlar & Değerlendirme"):
            yorum = []
            referanslar = {
                11: {"sprint": 80, "mesafe": 3.5, "work_rate": 50, "sure": 40},
                13: {"sprint": 100, "mesafe": 4.5, "work_rate": 55, "sure": 45},
                15: {"sprint": 120, "mesafe": 5.5, "work_rate": 60, "sure": 50},
                17: {"sprint": 160, "mesafe": 6.5, "work_rate": 70, "sure": 60},
                19: {"sprint": 180, "mesafe": 7.2, "work_rate": 75, "sure": 70},
                21: {"sprint": 200, "mesafe": 8.0, "work_rate": 80, "sure": 75}
            }
            yas_keys = sorted(referanslar.keys())
            uygun_yas = min(yas_keys, key=lambda y: abs(y - oyuncu_yasi))
            ref = referanslar[uygun_yas]

            if training_df['sprint_distance'].mean() < ref['sprint']:
                yorum.append(f"Sprint mesafesi yaş grubuna göre düşük ({ref['sprint']} m altı). Hız antrenmanları önerilir.")
            if training_df['distance'].mean() < ref['mesafe']:
                yorum.append(f"Toplam mesafe yaş grubuna göre düşük ({ref['mesafe']} km altı). Dayanıklılık artırılmalı.")
            if training_df['work_rate'].mean() < ref['work_rate']:
                yorum.append(f"Çalışma oranı yaş grubuna göre düşük ({ref['work_rate']} m/dk altı). Kondisyon geliştirilmeli.")
            if training_df['duration'].mean() < ref['sure']:
                yorum.append(f"Antrenman süresi kısa ({ref['sure']} dk altı). Antrenman yoğunluğu artırılabilir.")

            if not yorum:
                yorum.append("Performans yaş grubuna göre dengeli ve gelişim olumlu.")
            for y in yorum:
                st.info(y)

        st.subheader(f"📈 {selected_player} Performansı - Maçlar")
        if not match_df.empty:
            match_metric_key = st.selectbox("Maçta İncelenecek Metriği Seç", list(metric_options.keys()), format_func=lambda x: metric_options[x], key="match_metric")
            fig_match, ax_match = plt.subplots(figsize=(12, 5))
            ax_match.plot(match_df['date'], match_df[match_metric_key], marker='s', color='orange', linewidth=2)
            ax_match.set_title(f"{metric_options[match_metric_key]} (Maç)", fontsize=14)
            ax_match.set_xlabel("Tarih")
            ax_match.set_ylabel(metric_options[match_metric_key])
            ax_match.grid(True, linestyle='--', alpha=0.5)
            ax_match.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            fig_match.autofmt_xdate()
            st.pyplot(fig_match)

            st.dataframe(match_df.drop(columns=['player_id']).rename(columns={
                "date": "Tarih",
                "session_type": "Oturum Türü",
                "session_detail": "Antrenman Detayı",
                "duration": "Süre (dk)",
                "total_touches": "Toplam Dokunuş",
                "left_leg": "Sol Bacak (%)",
                "right_leg": "Sağ Bacak (%)",
                "distance": "Mesafe (km)",
                "sprint_distance": "Sprint Mesafesi (m)",
                "work_rate": "Çalışma Oranı (m/dk)",
                "accl_decl": "İvmelenme/Sert Duruş",
                "player_name": "Oyuncu"
            }), use_container_width=True)

    else:
        st.info("Henüz analiz yapılacak veri yok. PDF yükleyin.")

if __name__ == "__main__":
    main()
