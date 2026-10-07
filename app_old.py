import os
import re
import json
import uuid
import time
import urllib.parse
from datetime import datetime, timedelta
import threading
import io
import base64
import math
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image
from bs4 import BeautifulSoup
import requests
from fpdf import FPDF
import pdfplumber
import streamlit as st
import extra_streamlit_components as stx # Added cookie management library
from google import genai
from gtts import gTTS
# Attempt to import Supabase library
try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
# Import live IoT database library (IoT Database)
try:
    from influxdb_client import InfluxDBClient
except ImportError:
    InfluxDBClient = None
# Attempt to import barcode reading library
try:
    from pyzbar.pyzbar import decode as decode_qr
except ImportError:
    decode_qr = None
# =========================================================
# 0. Main Page Settings, AI, Audio, and Language Initialization
# =========================================================
st.set_page_config(
    page_title="Comprehensive Industrial Complex - Addoma Trading Services",
    page_icon="🔐",
    layout="wide",
)
# Initial setup for Session State variables
if "audio_muted" not in st.session_state:
    st.session_state.audio_muted = False
if "lang" not in st.session_state:
    st.session_state.lang = "ar" # 'ar' or 'en'
# Set default page upon entry
if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"
# Update mini database structure to support main and sub menus
if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "Khartoum (Main Menu)": {
            "Main Site - Kafouri (Sub Site)": {
                "address": "Khartoum - Industrial Zone - Kafouri",
                "technician_name": "Eng. Osman Adam Addoma",
                "technician_whatsapp": "249912345678",
                "generators": {
                    "G1": {
                        "model": "Perkins 410 kVA",
                        "run_hours": 700.0,
                        "target": 940.0,
                        "kw": 410.0,
                        "load": 250.0,
                        "calib_elec": {
                            "v_nominal": 400.0, "v_measured": 398.0,
                            "freq_nominal": 50.0, "freq_measured": 50.1,
                            "current_max": 600.0, "current_measured": 360.0,
                            "pf": 0.85, "ct_ratio": "600/5"
                        },
                        "calib_engine": {
                            "oil_press_bar": 4.5, "coolant_temp_c": 85.0,
                            "rpm": 1500.0, "battery_v": 26.5,
                            "ambient_temp": 43.0
                        }
                    },
                    "G2": {
                        "model": "Cummins 250 kVA",
                        "run_hours": 1200.0,
                        "target": 1500.0,
                        "kw": 250.0,
                        "load": 180.0,
                        "calib_elec": {
                            "v_nominal": 400.0, "v_measured": 402.0,
                            "freq_nominal": 50.0, "freq_measured": 49.9,
                            "current_max": 360.0, "current_measured": 260.0,
                            "pf": 0.82, "ct_ratio": "400/5"
                        },
                        "calib_engine": {
                            "oil_press_bar": 4.2, "coolant_temp_c": 88.0,
                            "rpm": 1500.0, "battery_v": 25.8,
                            "ambient_temp": 45.0
                        }
                    }
                }
            }
        }
    }
# Daily logs record and reading tracking
if "daily_logs" not in st.session_state:
    today_str = datetime.now().strftime("%Y-%m-%d")
    st.session_state.daily_logs = [
        {
            "timestamp": f"{today_str} 08:30:00",
            "date": today_str,
            "site": "Khartoum (Main Menu) - Main Site - Kafouri (Sub Site)",
            "generator": "G1",
            "technician": "Ahmed Maintenance Tech",
            "run_hours": 700.0,
            "v_measured": 398.0,
            "oil_press": 4.5,
            "coolant_temp": 85.0,
            "status": "Normal"
        }
    ]
# Safely fetch Gemini API key from secrets
gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not gemini_key and "supabase" in st.secrets:
    gemini_key = st.secrets["supabase"].get("GEMINI_API_KEY")
if not gemini_key:
    st.warning("⚠️ GEMINI_API_KEY not found. Please add it to st.secrets.")
# Initialize Gemini API client
client = genai.Client(api_key=gemini_key) if gemini_key else None
# Supabase database connection settings
supabase = None
if create_client:
    supabase_url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    supabase_key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
    if not supabase_url and "supabase" in st.secrets:
        supabase_url = st.secrets["supabase"].get("SUPABASE_URL")
        supabase_key = st.secrets["supabase"].get("SUPABASE_KEY")
    if supabase_url and supabase_key:
        try:
            supabase = create_client(supabase_url, supabase_key)
            response = supabase.table("subscriptions").select("*").limit(1).execute()
            st.success("✅ Application successfully connected and activated with Supabase database!")
        except Exception as e:
            st.error(f"❌ Database connection failed: {e}")
    else:
        st.info("💡 Supabase keys not found. Please add them (SUPABASE_URL and SUPABASE_KEY) to st.secrets file.")
else:
    st.warning("⚠️ Supabase library is not installed. Please install it using pip install supabase")

# Updated audio playback function with dual-language support, mute option, and continuous alarm looping
def play_audio(text, lang='ar', loop=False):
    """Convert text to speech using gTTS and play it if Mute is not enabled, with loop support"""
    if st.session_state.get("audio_muted", False):
        return
    try:
        tts_lang = 'en' if st.session_state.lang == 'en' or lang == 'en' else 'ar'
        tts = gTTS(text=text, lang=tts_lang)
        audio_data = io.BytesIO()
        tts.write_to_fp(audio_data)
        audio_bytes = audio_data.getvalue()
        if loop:
            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
            audio_html = f"""
                <audio autoplay loop controls style="width: 100%;">
                    <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
                    Your browser does not support audio playback.
                </audio>
            """
            st.components.v1.html(audio_html, height=60)
        else:
            audio_data.seek(0)
            st.audio(audio_data, format='audio/mp3', autoplay=True)
    except Exception as e:
        st.error(f"Error playing audio: {e}")
