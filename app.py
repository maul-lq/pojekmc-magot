import streamlit as st
import paho.mqtt.client as mqtt
import json
import pandas as pd
import time

from datetime import datetime
from paho.mqtt.enums import CallbackAPIVersion

# ==========================================
# KONFIGURASI MQTT (Sesuaikan dengan ESP32)
# ==========================================
MQTT_BROKER = "10.41.199.90"  # Ganti dengan IP Mosquitto kamu
MQTT_PORT = 1883
MQTT_TOPIC = "esp32/sensor_data"

# ==========================================
# SETUP HALAMAN STREAMLIT
# ==========================================
st.set_page_config(page_title="IoT Dashboard ESP32", layout="wide")
st.title("📡 Real-Time IoT Dashboard (ESP32 + Mosquitto)")

# ==========================================
# MEMORI GLOBAL (THREAD-SAFE)
# ==========================================
# Menggunakan cache_resource agar data list tidak ter-reset saat auto-refresh
@st.cache_resource
def get_sensor_data_buffer():
    return []

# Variabel ini bisa diakses dari background thread MQTT maupun main thread Streamlit
sensor_data_buffer = get_sensor_data_buffer()

# ==========================================
# FUNGSI CALLBACK & SETUP MQTT
# ==========================================
@st.cache_resource
def init_mqtt_client():
    client = mqtt.Client(CallbackAPIVersion.VERSION2)
    
    # Callback saat berhasil terhubung ke broker
    def on_connect(client, userdata, flags, reason_code, properties):
        print(f"Terhubung ke MQTT Broker dengan kode: {reason_code}")
        client.subscribe(MQTT_TOPIC)

    # Callback saat menerima pesan (Berjalan di background thread)
    def on_message(client, userdata, msg):
        try:
            payload = msg.payload.decode("utf-8")
            data = json.loads(payload)
            data['waktu'] = datetime.now().strftime("%H:%M:%S")
            
            # Simpan data ke buffer global (bukan ke st.session_state)
            sensor_data_buffer.append(data)
            
            # Batasi hanya menyimpan 50 data terakhir
            if len(sensor_data_buffer) > 50:
                sensor_data_buffer.pop(0)
                
        except Exception as e:
            print("Gagal memproses pesan:", e)

    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()  # Berjalan di background (non-blocking)
    except Exception as e:
        st.error(f"Gagal terhubung ke MQTT Broker: {e}")
        
    return client

# Panggil fungsi untuk inisiasi MQTT hanya sekali berkat @st.cache_resource
mqtt_client = init_mqtt_client()

# ==========================================
# TAMPILAN DASHBOARD UI
# ==========================================
metric_placeholder = st.empty()
chart_placeholder = st.empty()

# Baca data dari memori global
if len(sensor_data_buffer) > 0:
    # Ambil data paling terakhir
    latest_data = sensor_data_buffer[-1]
    
    with metric_placeholder.container():
        col1, col2, col3, col4 = st.columns(4)
        
        col1.metric("Suhu", f"{latest_data.get('temperature', 0)} °C")
        col2.metric("Kelembaban", f"{latest_data.get('humidity', 0)} %")
        col3.metric("Kadar Gas", latest_data.get('gas', 0))
        
        relay_status = latest_data.get('relay', 'OFF')
        if relay_status == "ON":
            col4.error(f"Status Relay: {relay_status}")
        else:
            col4.success(f"Status Relay: {relay_status}")

    # Ubah list dictionary menjadi Pandas DataFrame
    df = pd.DataFrame(sensor_data_buffer)
    df.set_index('waktu', inplace=True)
    
    with chart_placeholder.container():
        st.subheader("Grafik Suhu & Kelembaban (Real-time)")
        st.line_chart(df[['temperature', 'humidity']])
        
        st.subheader("Grafik Level Gas")
        st.line_chart(df[['gas']], color="#ffaa00")

else:
    st.info("Menunggu data dari ESP32...")

# ==========================================
# AUTO-REFRESH LOGIC
# ==========================================
time.sleep(2)
st.rerun()