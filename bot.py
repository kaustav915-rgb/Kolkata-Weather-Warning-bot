# Copyright (c) 2026 Kaustav Ray
# Kolkata Rain & Flood Alert Bot (Final - All Live Data)

import telebot
from telebot import types
import requests
import sqlite3
import os
from datetime import datetime, timezone, timedelta
from flask import Flask
from threading import Thread, Lock
import time
import re

# ================== CONFIG ==================
TOKEN = os.environ.get("BOT_TOKEN")
API_KEY = os.environ.get("OPENWEATHER_KEY")
TOMTOM_KEY = os.environ.get("TOMTOM_KEY")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)
db_lock = Lock()

# ================== DATABASE ==================
def get_db_connection():
    conn = sqlite3.connect("subscribers.db", check_same_thread=False)
    return conn

with get_db_connection() as conn:
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS subscribers (user_id INTEGER PRIMARY KEY, language TEXT DEFAULT 'en')")
    conn.commit()

# ================== GLOBALS & DATA ==================
last_rain_state = False

# ================== LIVE FLOOD LOGIC ==================
def get_kolkata_rain_status():
    """Fetches current rain volume for Kolkata."""
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q=Kolkata,IN&appid={API_KEY}&units=metric"
        res = requests.get(url, timeout=5).json()
        rain_1h = res.get("rain", {}).get("1h", 0)
        return rain_1h
    except:
        return 0

def get_area_flood_risk(area_name, lang="en"):
    """
    Assesses flood risk for a specific area based on rain and traffic anomalies.
    Returns a string describing the risk.
    """
    rain_1h = get_kolkata_rain_status()
    traffic_status = check_live_traffic(area_name, lang, return_raw=True)

    risk_level = "Low"
    details = []

    if rain_1h > 5:
        risk_level = "High"
        details.append("Heavy rainfall across Kolkata. Waterlogging likely in low-lying areas.")
    elif rain_1h > 2:
        risk_level = "Moderate"
        details.append("Moderate rainfall. Localized waterlogging possible.")
    else:
        details.append("No significant rainfall currently.")

    if traffic_status and traffic_status.get("curr_speed") and traffic_status.get("free_flow"):
        curr_speed = traffic_status["curr_speed"]
        free_flow = traffic_status["free_flow"]
        if curr_speed < (free_flow * 0.4):
            risk_level = "High" if risk_level == "Moderate" else risk_level # Elevate if already moderate
            details.append(f"Severe traffic congestion ({curr_speed} km/h vs {free_flow} km/h normal) in {area_name}, possibly due to waterlogging.")
        elif curr_speed < (free_flow * 0.8):
            if risk_level == "Low": risk_level = "Moderate"
            details.append(f"Moderate traffic ({curr_speed} km/h vs {free_flow} km/h normal) in {area_name}.")

    if risk_level == "High":
        return f"🔴 <b>High Flood Risk in {area_name}!</b>\n" + "\n• ".join(details) if lang == "en" else f"🔴 <b>{area_name} में बाढ़ का उच्च जोखिम!</b>\n" + "\n• ".join(details)
    elif risk_level == "Moderate":
        return f"🟡 <b>Moderate Flood Risk in {area_name}.</b>\n" + "\n• ".join(details) if lang == "en" else f"🟡 <b>{area_name} में बाढ़ का मध्यम जोखिम।</b>\n" + "\n• ".join(details)
    else:
        return f"🟢 <b>Low Flood Risk in {area_name}.</b>\n" + "\n• ".join(details) if lang == "en" else f"🟢 <b>{area_name} में बाढ़ का कम जोखिम।</b>\n" + "\n• ".join(details)

# ================== HELPERS ==================
def get_user_lang(user_id):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT language FROM subscribers WHERE user_id=?", (user_id,))
        row = c.fetchone()
        return row[0] if row else "en"

def save_user(user_id, lang="en"):
    with db_lock:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO subscribers (user_id, language) VALUES (?, ?)", (user_id, lang))
            conn.commit()

def geocode_area(area_name):
    if not TOMTOM_KEY: return "22.5726,88.3639" # Default to Kolkata central
    try:
        url = f"https://api.tomtom.com/search/2/geocode/{area_name}, Kolkata.json?key={TOMTOM_KEY}&limit=1"
        res = requests.get(url, timeout=5).json()
        if res.get("results"):
            pos = res["results"][0]["position"]
            return f"{pos["lat"]},{pos["lon"]}"
    except: pass
    return "22.5726,88.3639"

# ================== WEATHER & TRAFFIC ==================
def get_weather(lang="en"):
    url = f"https://api.openweathermap.org/data/2.5/weather?q=Kolkata,IN&appid={API_KEY}&units=metric&lang={\'hi\' if lang==\'hi\' else \'en\'}"
    try:
        data = requests.get(url, timeout=10).json()
        desc = data["weather"][0]["description"].capitalize()
        temp = data["main"]["temp"]
        rain = data.get("rain", {}).get("1h", 0)
        
        risk = "🔴 <b>High Flood Risk!</b> Heavy rain detected." if rain > 5 else \
               "🟠 Heavy rain/thunderstorm risk" if "rain" in desc.lower() or "thunder" in desc.lower() else \
               "🟡 Moderate rain possible" if data["clouds"]["all"] > 60 else "✅ Low rain risk"

        return f"🌧️ <b>Kolkata Weather (Live)</b>\n\n🌡️ {temp}°C | ☁️ {desc}\n☔ Rain (1h): {rain}mm\n\n{risk}"
    except: return "Weather fetch error."

def check_live_traffic(area_name, lang="en", return_raw=False):
    if not TOMTOM_KEY: 
        if return_raw: return {}
        return "⚠️ Traffic API key missing."
    coords = geocode_area(area_name)
    url = f"https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json?key={TOMTOM_KEY}&point={coords}"
    try:
        data = requests.get(url, timeout=5).json()["flowSegmentData"]
        curr, free = data["currentSpeed"], data["freeFlowSpeed"]
        if return_raw: return {"curr_speed": curr, "free_flow": free}
        status = "🔴 <b>Heavy Jam!</b>" if curr < (free * 0.4) else "🟡 <b>Moderate Traffic.</b>" if curr < (free * 0.8) else "🟢 <b>Clear Routes.</b>"
        return f"{status} Speed: {curr} km/h (Normal: {free} km/h)"
    except: 
        if return_raw: return {}
        return "Traffic data unavailable."

# ================== HANDLERS ==================
@bot.message_handler(commands=["start"])
def start(message):
    lang = get_user_lang(message.chat.id)
    save_user(message.chat.id, lang)
    text = """🌧️ <b>Welcome to Kolkata Rain & Flood Alert Bot!</b>\n\nI provide real-time updates for Kolkata:\n• <b>Live Weather & Rain</b>\n• <b>Live Traffic Speeds</b>\n• <b>Real-time Waterlogging Alerts</b>\n\nUse buttons below to explore! 👇"""
    bot.send_message(message.chat.id, text, reply_markup=get_keyboard(lang))

@bot.message_handler(commands=["floodzones", "बाढ़ क्षेत्र"])
def flood_cmd(message):
    lang = get_user_lang(message.chat.id)
    text = message.text.strip()
    match = re.search(r'/(?:floodzones|बाढ़ क्षेत्र)\s*(.+)?', text, re.IGNORECASE)
    area = match.group(1).strip() if match and match.group(1) else "Kolkata"
    
    bot.send_message(message.chat.id, get_area_flood_risk(area, lang))

@bot.message_handler(commands=["weather", "मौसम"])
def weather_cmd(message):
    bot.send_message(message.chat.id, get_weather(get_user_lang(message.chat.id)))

@bot.message_handler(commands=["traffic", "ट्रैफिक"])
def traffic_cmd(message):
    lang = get_user_lang(message.chat.id)
    match = re.search(r'/(?:traffic|ट्रैफिक)\s+(.+)', message.text, re.IGNORECASE)
    area = match.group(1).strip() if match else "Kolkata"
    bot.send_message(message.chat.id, f"🚗 <b>Traffic Update: {area}</b>\n{check_live_traffic(area, lang)}")

@bot.message_handler(commands=["getarea"])
def getarea_cmd(message):
    lang = get_user_lang(message.chat.id)
    match = re.search(r'/getarea\s+(.+)', message.text, re.IGNORECASE)
    if not match:
        bot.send_message(message.chat.id, "Use: /getarea <area> (e.g. /getarea Garia)")
        return
    area = match.group(1).strip()
    weather = get_weather(lang)
    traffic = check_live_traffic(area, lang)
    flood_risk = get_area_flood_risk(area, lang)
    bot.send_message(message.chat.id, f"{weather}\n\n📍 <b>{area} Status:</b>\n{traffic}\n\n{flood_risk}")

@bot.message_handler(commands=["subscribe", "सब्सक्राइब"])
def subscribe(message):
    save_user(message.chat.id, get_user_lang(message.chat.id))
    bot.send_message(message.chat.id, "✅ Subscribed to alerts!")

@bot.message_handler(commands=["unsubscribe", "अनसब्सक्राइब"])
def unsubscribe(message):
    with db_lock:
        with get_db_connection() as conn:
            conn.cursor().execute("DELETE FROM subscribers WHERE user_id=?", (message.chat.id,))
            conn.commit()
    bot.send_message(message.chat.id, "❌ Unsubscribed.")

@bot.message_handler(commands=["emergency", "इमरजेंसी"])
def emergency(message):
    text = "🚨 <b>Emergency Helplines</b>\n\nPolice: 100\nAmbulance: 108\nPower: 1912\nTraffic: 1033"
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=["feedback", "फीडबैक"])
def feedback(message):
    try:
        fb = message.text.split(maxsplit=1)[1]
        bot.send_message(ADMIN_ID, f"📝 Feedback: {fb}")
        bot.reply_to(message, "✅ Feedback sent!")
    except:
        bot.reply_to(message, "Use: /feedback Your message")

# Other commands (advice, fact, etc.) mapping to their respective functions...
@bot.message_handler(commands=["advice", "fact", "holidays", "quote", "catfact", "dictionary", "trivia", "joke", "exchange", "horoscope", "crypto", "dog", "cat", "age", "gender"])
def misc_commands(message):
    cmd = message.text.split()[0][1:].lower()
    lang = get_user_lang(message.chat.id)
    if cmd == "advice": bot.send_message(message.chat.id, get_random_advice(lang))
    elif cmd == "fact": bot.send_message(message.chat.id, get_random_number_fact(lang))
    elif cmd == "holidays": bot.send_message(message.chat.id, get_public_holidays(datetime.now().year, lang))
    elif cmd == "quote": bot.send_message(message.chat.id, get_random_quote(lang))
    elif cmd == "catfact": bot.send_message(message.chat.id, get_random_cat_fact(lang))
    elif cmd == "dictionary": 
        word = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "hello"
        bot.send_message(message.chat.id, get_dictionary_definition(word, lang))
    elif cmd == "trivia": bot.send_message(message.chat.id, get_random_trivia(lang))
    elif cmd == "joke": bot.send_message(message.chat.id, get_random_joke(lang))
    elif cmd == "exchange":
        parts = message.text.split()
        base, target = (parts[1], parts[2]) if len(parts) > 2 else ("USD", "INR")
        bot.send_message(message.chat.id, get_exchange_rate(base, target, lang))
    elif cmd == "horoscope":
        sign = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "aries"
        bot.send_message(message.chat.id, get_horoscope(sign, lang))
    elif cmd == "crypto":
        cid = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "90"
        bot.send_message(message.chat.id, get_crypto_price(cid, lang))
    elif cmd == "dog": bot.send_message(message.chat.id, get_random_dog_image(lang))
    elif cmd == "cat": bot.send_message(message.chat.id, get_random_cat_image(lang))
    elif cmd == "age":
        name = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "John"
        bot.send_message(message.chat.id, get_predicted_age(name, lang))
    elif cmd == "gender":
        name = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "Jane"
        bot.send_message(message.chat.id, get_predicted_gender(name, lang))

@bot.message_handler(content_types=["text"])
def handle_text(message):
    txt = message.text.lower()
    if "weather" in txt or "मौसम" in txt: weather_cmd(message)
    elif "flood" in txt or "बाढ़" in txt: flood_cmd(message)
    elif "traffic" in txt or "ट्रैफिक" in txt: traffic_cmd(message)

# ================== SCHEDULER & MONITOR ==================
def rain_monitor():
    global last_rain_state
    while True:
        try:
            rain_1h = get_kolkata_rain_status()
            is_raining_now = rain_1h > 0.5 # Consider light rain as 'raining'

            if is_raining_now and not last_rain_state:
                msg = "🚨 Rain STARTED in Kolkata! Expect waterlogging in low-lying areas."
                for uid, _ in get_subscribers():
                    try: bot.send_message(uid, msg)
                    except: pass
                last_rain_state = True
            elif not is_raining_now and last_rain_state:
                msg = "🌤️ Rain STOPPED. Traffic clearing but watch for residual waterlogging."
                for uid, _ in get_subscribers():
                    try: bot.send_message(uid, msg)
                    except: pass
                last_rain_state = False
        except: pass
        time.sleep(300) # Check every 5 minutes

def start_daily_scheduler():
    while True:
        now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        if now.hour == 7 and now.minute == 0:
            weather = get_weather("en")
            # Provide a general flood risk for Kolkata in daily alert
            kolkata_flood_risk = get_area_flood_risk("Kolkata", "en")
            msg = f"🌅 <b>Good Morning Kolkata!</b>\n\n{weather}\n\n{kolkata_flood_risk}"
            for uid, _ in get_subscribers():
                try: bot.send_message(uid, msg)
                except: pass
            time.sleep(60) # Wait a minute to avoid multiple sends in the same minute
        time.sleep(30)

if __name__ == "__main__":
    Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    Thread(target=start_daily_scheduler, daemon=True).start()
    Thread(target=rain_monitor, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
