# Copyright (c) 2026 Kaustav Ray
# Kolkata Rain & Flood Alert Bot

import telebot
from telebot import types
import requests
import sqlite3
import os
from datetime import datetime, timezone, timedelta
from flask import Flask
from threading import Thread
import time
import re

# ================== CONFIG ==================
TOKEN = os.environ.get("BOT_TOKEN")
API_KEY = os.environ.get("OPENWEATHER_KEY")
TOMTOM_KEY = os.environ.get("TOMTOM_KEY") # Add your TomTom API key here
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

app = Flask(__name__)

@app.route("/ping")
def ping():
    return "pong", 200

@app.route("/")
def index():
    return "🌧️ Kolkata Rain & Flood Alert Bot is running 24/7!"

# ================== DATABASE ==================
conn = sqlite3.connect("subscribers.db", check_same_thread=False)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS subscribers 
             (user_id INTEGER PRIMARY KEY, language TEXT DEFAULT 'en')""")
conn.commit()

# ================== GLOBALS & DATA ==================
last_rain_state = False
last_broadcast_time = None
last_weather_desc = "haze"

FLOOD_ZONES = [
    "Garia", "Jadavpur", "Bansdroni", "Bijoygarh", "Tollygunge",
    "Jodhpur Park", "Kalighat", "Topsia", "Ballygunge", "Alipore",
    "Behala", "Salt Lake", "Rajarhat", "New Town", "EM Bypass",
    "Howrah", "Sonarpur", "Park Street area"
]

TOP_3_FLOOD = ["Garia", "Jadavpur", "Salt Lake"]

# Hardcoded some central coords for major zones to avoid an extra geocode API call
AREA_COORDS = {
    "sonarpur": "22.4394,88.4326",
    "garia": "22.4665,88.3850",
    "jadavpur": "22.4955,88.3643",
    "salt lake": "22.5800,88.4025",
    "new town": "22.5760,88.4735",
    "howrah": "22.5958,88.3260",
    "kolkata": "22.5726,88.3639" # default fallback
}

# ================== KEYBOARD ==================
def get_keyboard(lang="en"):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if lang == "hi":
        markup.add("🌧️ मौसम", "⚠️ अलर्ट", "🌊 बाढ़ क्षेत्र", "💡 टिप्स")
        markup.add("🚗 ट्रैफिक", "📲 सब्सक्राइब", "❌ अनसब्सक्राइब", "🚨 इमरजेंसी")
        markup.add("📝 फीडबैक", "❓ मदद", "💡 सलाह", "🔢 तथ्य", "🗓️ छुट्टियाँ", "💬 उद्धरण", "🐱 बिल्ली तथ्य", "📚 शब्दकोश", "🧠 सामान्य ज्ञान", "😂 चुटकुला", "💱 विनिमय दर", "♈ राशिफल", "💰 क्रिप्टो", "🐶 कुत्ता", "🐱 बिल्ली", "👶 आयु", "🚻 लिंग")
    else:
        markup.add("🌧️ Weather", "⚠️ Alert", "🌊 Flood Zones", "💡 Tips")
        markup.add("🚗 Traffic", "📲 Subscribe", "❌ Unsubscribe", "🚨 Emergency")
        markup.add("📝 Feedback", "❓ Help", "💡 Advice", "🔢 Fact", "🗓️ Holidays", "💬 Quote", "🐱 Cat Fact", "📚 Dictionary", "🧠 Trivia", "😂 Joke", "💱 Exchange Rate", "♈ Horoscope", "💰 Crypto", "🐶 Dog", "🐱 Cat", "👶 Age", "🚻 Gender")
    return markup

# ================== HELPERS ==================
def get_user_lang(user_id):
    c.execute("SELECT language FROM subscribers WHERE user_id=?", (user_id,))
    row = c.fetchone()
    return row[0] if row else "en"

def save_user(user_id, lang="en"):
    c.execute("INSERT OR REPLACE INTO subscribers (user_id, language) VALUES (?, ?)", (user_id, lang))
    conn.commit()

def get_subscribers():
    c.execute("SELECT user_id, language FROM subscribers")
    return c.fetchall()

# ================== APIs ==================

def get_random_advice(lang="en"):
    try:
        response = requests.get("https://api.adviceslip.com/advice", timeout=5)
        if response.status_code == 200:
            data = response.json()
            advice = data["slip"]["advice"]
            return f"💡 <b>Advice:</b> {advice}" if lang == "en" else f"💡 <b>सलाह:</b> {advice}"
    except Exception as e:
        print(f"Advice API error: {e}")
    return "Could not fetch advice right now." if lang == "en" else "अभी सलाह नहीं मिल सकी।"

def get_random_number_fact(lang="en"):
    try:
        response = requests.get("http://numbersapi.com/random/trivia", timeout=5)
        if response.status_code == 200:
            fact = response.text
            return f"🔢 <b>Number Fact:</b> {fact}" if lang == "en" else f"🔢 <b>संख्या तथ्य:</b> {fact}"
    except Exception as e:
        print(f"Numbers API error: {e}")
    return "Could not fetch a number fact right now." if lang == "en" else "अभी संख्या तथ्य नहीं मिल सका।"

def get_public_holidays(year, lang="en"):
    try:
        response = requests.get(f"https://date.nager.at/api/v3/PublicHolidays/{year}/IN", timeout=5)
        if response.status_code == 200:
            holidays = response.json()
            if not holidays:
                return "No public holidays found for this year." if lang == "en" else "इस साल कोई सार्वजनिक अवकाश नहीं मिला।"
            
            holiday_list = []
            for h in holidays:
                date_obj = datetime.strptime(h["date"], "%Y-%m-%d")
                holiday_list.append(f"• {date_obj.strftime('%d %b')} - {h['name']}")
            
            return f"🗓️ <b>Public Holidays {year} (India):</b>\n\n" + "\n".join(holiday_list) if lang == "en" else f"🗓️ <b>सार्वजनिक अवकाश {year} (भारत):</b>\n\n" + "\n".join(holiday_list)
    except Exception as e:
        print(f"Public Holidays API error: {e}")
    return "Could not fetch public holidays right now." if lang == "en" else "अभी सार्वजनिक अवकाश नहीं मिल सका।"

def get_random_quote(lang="en"):
    try:
        response = requests.get("https://zenquotes.io/api/random", timeout=5)
        if response.status_code == 200:
            data = response.json()
            quote = data[0]["q"]
            author = data[0]["a"]
            return f"💬 <b>Quote:</b> {quote} - <i>{author}</i>" if lang == "en" else f"💬 <b>उद्धरण:</b> {quote} - <i>{author}</i>"
    except Exception as e:
        print(f"ZenQuotes API error: {e}")
    return "Could not fetch a quote right now." if lang == "en" else "अभी उद्धरण नहीं मिल सका।"

def get_random_cat_fact(lang="en"):
    try:
        response = requests.get("https://catfact.ninja/fact", timeout=5)
        if response.status_code == 200:
            data = response.json()
            fact = data["fact"]
            return f"🐱 <b>Cat Fact:</b> {fact}" if lang == "en" else f"🐱 <b>बिल्ली तथ्य:</b> {fact}"
    except Exception as e:
        print(f"CatFact API error: {e}")
    return "Could not fetch a cat fact right now." if lang == "en" else "अभी बिल्ली तथ्य नहीं मिल सका।"

def get_dictionary_definition(word, lang="en"):
    try:
        response = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and isinstance(data, list) and len(data) > 0:
                meanings = data[0].get("meanings", [])
                if meanings:
                    definitions = meanings[0].get("definitions", [])
                    if definitions:
                        definition = definitions[0].get("definition")
                        if definition:
                            return f"📚 <b>{word.capitalize()}:</b> {definition}" if lang == "en" else f"📚 <b>{word.capitalize()}:</b> {definition}"
            return f"Definition not found for '{word}'" if lang == "en" else f"'{word}' के लिए परिभाषा नहीं मिली।"
    except Exception as e:
        print(f"Dictionary API error: {e}")
    return "Could not fetch definition right now." if lang == "en" else "अभी परिभाषा नहीं मिल सकी।"

def get_random_trivia(lang="en"):
    try:
        response = requests.get("https://opentdb.com/api.php?amount=1&type=multiple", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data["response_code"] == 0 and data["results"]:
                trivia = data["results"][0]
                question = trivia["question"]
                correct_answer = trivia["correct_answer"]
                return f"🧠 <b>Trivia:</b> {question}\nCorrect Answer: {correct_answer}" if lang == "en" else f"🧠 <b>सामान्य ज्ञान:</b> {question}\nसही उत्तर: {correct_answer}"
    except Exception as e:
        print(f"Trivia API error: {e}")
    return "Could not fetch trivia right now." if lang == "en" else "अभी सामान्य ज्ञान नहीं मिल सका।"

def get_random_joke(lang="en"):
    try:
        response = requests.get("https://official-joke-api.appspot.com/random_joke", timeout=5)
        if response.status_code == 200:
            data = response.json()
            setup = data["setup"]
            punchline = data["punchline"]
            return f"😂 <b>Joke:</b>\n{setup}\n{punchline}" if lang == "en" else f"😂 <b>जोक:</b>\n{setup}\n{punchline}"
    except Exception as e:
        print(f"Joke API error: {e}")
    return "Could not fetch a joke right now." if lang == "en" else "अभी जोक नहीं मिल सका।"

def get_exchange_rate(base_currency, target_currency, lang="en"):
    try:
        response = requests.get(f"https://api.exchangerate-api.com/v4/latest/{base_currency.upper()}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            rates = data.get("rates")
            if rates and target_currency.upper() in rates:
                rate = rates[target_currency.upper()]
                return f"💱 <b>Exchange Rate:</b> 1 {base_currency.upper()} = {rate:.2f} {target_currency.upper()}" if lang == "en" else f"💱 <b>विनिमय दर:</b> 1 {base_currency.upper()} = {rate:.2f} {target_currency.upper()}"
            else:
                return f"Could not find exchange rate for {base_currency.upper()} to {target_currency.upper()}." if lang == "en" else f"{base_currency.upper()} से {target_currency.upper()} के लिए विनिमय दर नहीं मिली।"
    except Exception as e:
        print(f"Exchange Rate API error: {e}")
    return "Could not fetch exchange rate right now." if lang == "en" else "अभी विनिमय दर नहीं मिल सकी।"

def get_horoscope(sign, lang="en"):
    try:
        response = requests.get(f"https://ohmanda.com/api/horoscope/{sign.lower()}/", timeout=5)
        if response.status_code == 200:
            data = response.json()
            horoscope = data["horoscope"]
            return f"♈ <b>{sign.capitalize()} Horoscope:</b> {horoscope}" if lang == "en" else f"♈ <b>{sign.capitalize()} राशिफल:</b> {horoscope}"
    except Exception as e:
        print(f"Horoscope API error: {e}")
    return "Could not fetch horoscope right now." if lang == "en" else "अभी राशिफल नहीं मिल सका।"

def get_crypto_price(crypto_id="90", lang="en"):
    try:
        response = requests.get(f"https://api.coinlore.net/api/ticker/?id={crypto_id}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and data[0]:
                crypto = data[0]
                name = crypto["name"]
                symbol = crypto["symbol"]
                price_usd = float(crypto["price_usd"])
                percent_change_24h = float(crypto["percent_change_24h"])
                return f"💰 <b>{name} ({symbol}) Price:</b> ${price_usd:,.2f} (24h change: {percent_change_24h:+.2f}%) " if lang == "en" else f"💰 <b>{name} ({symbol}) मूल्य:</b> ${price_usd:,.2f} (24 घंटे परिवर्तन: {percent_change_24h:+.2f}%) "
    except Exception as e:
        print(f"Crypto Price API error: {e}")
    return "Could not fetch crypto price right now." if lang == "en" else "अभी क्रिप्टो मूल्य नहीं मिल सका।"

def get_random_dog_image(lang="en"):
    try:
        response = requests.get("https://dog.ceo/api/breeds/image/random", timeout=5)
        if response.status_code == 200:
            data = response.json()
            image_url = data["message"]
            return f"🐶 <b>Random Dog:</b> {image_url}" if lang == "en" else f"🐶 <b>यादृच्छिक कुत्ता:</b> {image_url}"
    except Exception as e:
        print(f"Dog Image API error: {e}")
    return "Could not fetch a dog image right now." if lang == "en" else "अभी कुत्ते की तस्वीर नहीं मिल सकी।"

def get_random_cat_image(lang="en"):
    try:
        response = requests.get("https://api.thecatapi.com/v1/images/search", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and data[0] and data[0]["url"]:
                image_url = data[0]["url"]
                return f"🐱 <b>Random Cat:</b> {image_url}" if lang == "en" else f"🐱 <b>यादृच्छिक बिल्ली:</b> {image_url}"
    except Exception as e:
        print(f"Cat Image API error: {e}")
    return "Could not fetch a cat image right now." if lang == "en" else "अभी बिल्ली की तस्वीर नहीं मिल सकी।"

def get_predicted_age(name, lang="en"):
    try:
        response = requests.get(f"https://api.agify.io/?name={name}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            age = data["age"]
            if age:
                return f"👶 <b>Predicted Age for {name.capitalize()}:</b> {age}" if lang == "en" else f"👶 <b>{name.capitalize()} के लिए अनुमानित आयु:</b> {age}"
            else:
                return f"Could not predict age for {name.capitalize()}." if lang == "en" else f"{name.capitalize()} के लिए आयु का अनुमान नहीं लगा सका।"
    except Exception as e:
        print(f"Agify API error: {e}")
    return "Could not predict age right now." if lang == "en" else "अभी आयु का अनुमान नहीं लगा सका।"

def get_predicted_gender(name, lang="en"):
    try:
        response = requests.get(f"https://api.genderize.io/?name={name}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            gender = data["gender"]
            probability = data["probability"]
            if gender:
                return f"🚻 <b>Predicted Gender for {name.capitalize()}:</b> {gender} (Probability: {probability:.2f})" if lang == "en" else f"🚻 <b>{name.capitalize()} के लिए अनुमानित लिंग:</b> {gender} (संभावना: {probability:.2f})"
            else:
                return f"Could not predict gender for {name.capitalize()}." if lang == "en" else f"{name.capitalize()} के लिए लिंग का अनुमान नहीं लगा सका।"
    except Exception as e:
        print(f"Genderize API error: {e}")
    return "Could not predict gender right now." if lang == "en" else "अभी लिंग का अनुमान नहीं लगा सका।"


def get_weather(lang="en"):
    global last_weather_desc
    url = f"https://api.openweathermap.org/data/2.5/weather?q=Kolkata,IN&appid={API_KEY}&units=metric&lang={'hi' if lang=='hi' else 'en'}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return "Weather service temporary issue."

        data = response.json()
        weather = data["weather"][0]
        desc = weather["description"].capitalize()
        last_weather_desc = desc.lower()

        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        humidity = data["main"]["humidity"]
        wind = data["wind"]["speed"]
        clouds = data["clouds"]["all"]
        visibility = data["visibility"] / 1000
        sunrise = datetime.fromtimestamp(data["sys"]["sunrise"]).strftime("%I:%M %p")
        sunset = datetime.fromtimestamp(data["sys"]["sunset"]).strftime("%I:%M %p")

        risk = "🟠 Heavy rain/thunderstorm risk" if "rain" in desc.lower() or "thunder" in desc.lower() or clouds > 80 else \
               "🟡 Moderate rain/haze possible" if clouds > 60 else "✅ Low rain risk"

        return f"""🌧️ <b>Kolkata Weather (Live)</b>

🌡️ {temp}°C (feels {feels_like}°C)
☁️ {desc}
💧 Humidity: {humidity}%
💨 Wind: {wind} m/s
🌫️ Visibility: {visibility:.1f} km
☁️ Clouds: {clouds}%

🌅 Sunrise: {sunrise}   🌇 Sunset: {sunset}

{risk}"""
    except Exception as e:
        print(f"Weather fetch error: {e}")
        return "Weather fetch error. Try again."

def check_live_traffic(area_name, lang="en"):
    if not TOMTOM_KEY:
        return "⚠️ Live traffic API key missing."
        
    search_key = area_name.lower() if area_name else "kolkata"
    coords = AREA_COORDS.get(search_key, AREA_COORDS["kolkata"])
    
    # Hits the TomTom Flow Segment Data API to get current road speed vs freeflow
    url = f"https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json?key={TOMTOM_KEY}&point={coords}"
    
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()["flowSegmentData"]
            curr_speed = data["currentSpeed"]
            free_flow = data["freeFlowSpeed"]
            
            # Simple logic to determine how bad the jam is
            if curr_speed < (free_flow * 0.4):
                return f"🔴 <b>Heavy Traffic/Jam!</b> Current speed is sluggish at {curr_speed} km/h (Normally {free_flow} km/h)." if lang == "en" else f"🔴 <b>भारी जाम!</b> वर्तमान गति {curr_speed} km/h (सामान्य {free_flow} km/h)."
            elif curr_speed < (free_flow * 0.8):
                return f"🟡 <b>Moderate Traffic.</b> Moving at {curr_speed} km/h." if lang == "en" else f"🟡 <b>मध्यम ट्रैफिक।</b> गति: {curr_speed} km/h."
            else:
                return f"🟢 <b>Clear Routes.</b> Traffic flowing well at {curr_speed} km/h." if lang == "en" else f"🟢 <b>रास्ता साफ़ है।</b> गति: {curr_speed} km/h."
    except Exception as e:
        print(f"TomTom error: {e}")
        pass
        
    return "Could not fetch live traffic right now." if lang == "en" else "लाइव ट्रैफिक नहीं मिल सका।"

# ================== AREA SUMMARY ==================
def get_area_summary(area, lang="en"):
    weather = get_weather(lang)
    area_clean = area.strip().title()
    
    is_flood_prone = any(zone.lower() in area_clean.lower() for zone in FLOOD_ZONES)

    if "sonarpur" in area_clean.lower():
        status = """🌊 <b>Sonarpur Area Summary</b>

Sonarpur (South 24 Parganas) is highly flood-prone.
- Frequently waterlogged after moderate rain (Garia Bali, Rajpur, Subhashgram).
- Roads like Station Road often jam.
- Risk: High during thunderstorms — avoid low-lying parts.
- Power: 1912 for WBSEDCL complaints.""" if lang == "en" else """🌊 <b>सोनारपुर क्षेत्र सारांश</b>

सोनारपुर जलभराव के लिए जाना जाता है।
- मध्यम बारिश के बाद जलभराव (गड़िया बाली, राजपुर)।
- स्टेशन रोड पर जाम लग सकता है।
- जोखिम: भारी बारिश में निचले हिस्सों से बचें।
- पावर: 1912 कॉल करें।"""
    elif is_flood_prone:
        status = f"""🌊 <b>{area_clean} Area Summary</b>

⚠️ {area_clean} is a known flood-prone zone in Kolkata.
- Prone to quick waterlogging during heavy spells.
- Commute might be affected today based on current weather.
- General risk: {weather.splitlines()[-1]}""" if lang == "en" else f"""🌊 <b>{area_clean} क्षेत्र सारांश</b>

⚠️ {area_clean} जलभराव वाले इलाकों में से एक है।
- भारी बारिश में जल्दी पानी भर सकता है।
- सामान्य जोखिम: {weather.splitlines()[-1]}"""
    else:
        status = f"""📍 <b>{area_clean} Area Summary</b>

Currently tracking general Kolkata conditions for {area_clean}.
- Watch for localized waterlogging if it starts raining.
- General risk: {weather.splitlines()[-1]}""" if lang == "en" else f"""📍 <b>{area_clean} क्षेत्र सारांश</b>

{area_clean} के लिए सामान्य कोलकाता का मौसम लागू है।
- अगर बारिश हो तो लोकल जलभराव का ध्यान रखें।
- सामान्य जोखिम: {weather.splitlines()[-1]}"""

    return f"{weather}\n\n{status}"

# ================== TRAFFIC ==================
def get_traffic_update(area=None, lang="en"):
    weather = get_weather(lang)
    ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    today_date = ist_now.strftime("%d %b %Y")
    
    # Grab the real time data from TomTom
    live_status = check_live_traffic(area, lang)

    general = f"""🚗 <b>Kolkata Traffic Update</b>

• Date: {today_date}
• Weather Impact: Expect slow movement in low-lying zones if raining.
• Tips: Metro/Uber recommended during heavy showers. Helpline: 1033.""" if lang == "en" else f"""🚗 <b>कोलकाता ट्रैफिक अपडेट</b>

• आज ({today_date}): सामान्य शहर ट्रैफिक।
• बारिश प्रभाव: बारिश में निचले इलाकों में धीमा ट्रैफिक।
• टिप्स: जलभराव वाली सड़कों से बचें, मेट्रो का उपयोग करें। हेल्पलाइन: 1033।"""

    if area:
        area_clean = area.strip().title()
        specific = f"📍 <b>Live data for {area_clean}:</b>\n{live_status}" if lang == "en" else f"📍 <b>{area_clean} लाइव डेटा:</b>\n{live_status}"
        return f"{weather}\n\n{general}\n\n{specific}"
    else:
        live = f"📍 <b>Live central data:</b>\n{live_status}" if lang == "en" else f"📍 <b>केंद्रीय लाइव डेटा:</b>\n{live_status}"
        return f"{weather}\n\n{general}\n\n{live}"

# ================== DAILY MORNING ALERT ==================
def send_daily_alert():
    global last_broadcast_time
    subscribers = get_subscribers()
    if not subscribers:
        return

    weather_en = get_weather("en")
    weather_hi = get_weather("hi")
    top3 = ", ".join(TOP_3_FLOOD)

    traffic_tip = "🚗 Traffic: Avoid EM Bypass & low areas during rain. Use Metro/Uber."
    power_tip = "🔌 Power cut risk high today — charge phones & use 1912 (WBSEDCL/CESC)."

    for user_id, lang in subscribers:
        try:
            msg = f"""🌅 <b>Good Morning Kolkata!</b>

{weather_en if lang == 'en' else weather_hi}

🚨 <b>Top Flood Zones to Watch:</b>
• {top3}

{traffic_tip}
{power_tip}

Stay safe! 🌧️"""
            bot.send_message(user_id, msg)
        except:
            pass
    last_broadcast_time = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %I:%M %p")

# ================== RAIN MONITOR ==================
def send_rain_notification(is_start: bool):
    subscribers = get_subscribers()
    msg_en = "🚨 Rain has just STARTED in Kolkata! Roads flooding fast. Stay indoors if possible." if is_start else \
             "🌤️ Rain has STOPPED. Traffic clearing but watch for waterlogging."
    msg_hi = "🚨 कोलकाता में बारिश शुरू हो गई! सड़कें जल्दी भरेंगी। घर में रहें।" if is_start else \
             "🌤️ बारिश रुक गई। ट्रैफिक सुधर रहा है लेकिन जलभराव का ध्यान रखें।"
    for user_id, lang in subscribers:
        try:
            bot.send_message(user_id, msg_en if lang == "en" else msg_hi)
        except:
            pass

def rain_monitor():
    global last_rain_state
    while True:
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?q=Kolkata,IN&appid={API_KEY}&units=metric"
            data = requests.get(url, timeout=8).json()
            desc = data["weather"][0]["description"].lower()
            is_raining_now = any(word in desc for word in ["rain", "shower", "thunder", "drizzle"])

            if is_raining_now and not last_rain_state:
                send_rain_notification(True)
                last_rain_state = True
            elif not is_raining_now and last_rain_state:
                send_rain_notification(False)
                last_rain_state = False
        except:
            pass
        time.sleep(600)

# ================== HANDLERS ==================
@bot.message_handler(commands=["start"])
def start(message):
    lang = get_user_lang(message.chat.id)
    save_user(message.chat.id, lang)
    text = "🌧️ <b>Welcome to Kolkata Rain & Flood Alert Bot!</b>\n\nLive weather + alerts + /getarea <name> + /traffic <name>\nUse buttons 👇" if lang == "en" else "🌧️ <b>स्वागत है!</b>\n\nलाइव मौसम + अलर्ट + /getarea <name> + /traffic <name>\nबटन इस्तेमाल करें 👇"
    bot.send_message(message.chat.id, text, reply_markup=get_keyboard(lang))

@bot.message_handler(commands=["weather", "मौसम"])
def weather_cmd(message):
    lang = get_user_lang(message.chat.id)
    bot.send_message(message.chat.id, get_weather(lang))

@bot.message_handler(commands=["alert", "अलर्ट"])
def alert_cmd(message):
    lang = get_user_lang(message.chat.id)
    w = get_weather(lang)
    extra = "⚠️ Rain started or expected — avoid Garia/Jadavpur/Salt Lake. Power & traffic risk high!" if "High" in w or "Moderate" in w else "✅ Normal conditions."
    bot.send_message(message.chat.id, f"<b>Current Rain Alert</b>\n\n{extra}\n\n{w}")

@bot.message_handler(commands=["floodzones", "बाढ़ क्षेत्र"])
def flood_cmd(message):
    lang = get_user_lang(message.chat.id)
    zones = "\n• ".join(FLOOD_ZONES)
    text = f"<b>🚨 Flood-Prone Areas</b>\n\n• {zones}" if lang == "en" else f"<b>🚨 बाढ़ क्षेत्र</b>\n\n• {zones}"
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=["tips", "टिप्स"])
def tips_cmd(message):
    lang = get_user_lang(message.chat.id)
    text = "💡 Charge phone, avoid low areas, use metro in rain, call 1912 for power." if lang=="en" else "💡 फोन चार्ज रखें, निचले इलाके से बचें, बारिश में मेट्रो यूज करें, पावर के लिए 1912 कॉल करें।"
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=["traffic", "ट्रैफिक"])
def traffic_cmd(message):
    lang = get_user_lang(message.chat.id)
    text = message.text.strip()
    match = re.search(r'/(?:traffic|ट्रैफिक)\s+(.+)', text, re.IGNORECASE)
    area = match.group(1).strip() if match else None
    update = get_traffic_update(area, lang)
    bot.send_message(message.chat.id, update)

@bot.message_handler(commands=["getarea"])
def getarea_cmd(message):
    lang = get_user_lang(message.chat.id)
    text = message.text.strip()
    match = re.search(r'/getarea\s+(.+)', text, re.IGNORECASE)
    if not match:
        bot.send_message(message.chat.id, "Use: /getarea <area>  (e.g. /getarea Garia)")
        return
    area = match.group(1).strip()
    summary = get_area_summary(area, lang)
    bot.send_message(message.chat.id, summary)

@bot.message_handler(commands=["subscribe", "सब्सक्राइब"])
def subscribe(message):
    lang = get_user_lang(message.chat.id)
    save_user(message.chat.id, lang)
    bot.send_message(message.chat.id, "✅ Subscribed! Daily 7 AM + rain alerts enabled." if lang=="en" else "✅ सब्सक्राइब! रोज सुबह 7 बजे + बारिश अलर्ट चालू।")

@bot.message_handler(commands=["unsubscribe", "अनसब्सक्राइब"])
def unsubscribe(message):
    c.execute("DELETE FROM subscribers WHERE user_id=?", (message.chat.id,))
    conn.commit()
    bot.send_message(message.chat.id, "❌ Unsubscribed." if get_user_lang(message.chat.id)=="en" else "❌ अनसब्सक्राइब।")

@bot.message_handler(commands=["emergency", "इमरजेंसी"])
def emergency(message):
    lang = get_user_lang(message.chat.id)
    text = """🚨 <b>Emergency Helplines (Kolkata)</b>

Police: 100
Ambulance: 108 / 102
Fire: 101
Power (WBSEDCL): 1912
Women Helpline: 1091
Traffic Police: 1033

Save these now!""" if lang=="en" else """🚨 <b>इमरजेंसी हेल्पलाइन</b>

पुलिस: 100
एम्बुलेंस: 108 / 102
फायर: 101
बिजली (WBSEDCL): 1912
महिला हेल्पलाइन: 1091
ट्रैफिक: 1033

अभी सेव करें!"""
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=["feedback", "फीडबैक"])
def feedback(message):
    try:
        fb = message.text.split(maxsplit=1)[1]
        bot.send_message(ADMIN_ID, f"📝 Feedback from {message.chat.id} ({get_user_lang(message.chat.id)}):\n\n{fb}")
        bot.reply_to(message, "✅ Feedback sent to admin. Thank you! 🌟")
    except:
        bot.reply_to(message, "Use: /feedback Your suggestion here")

@bot.message_handler(commands=["advice", "सलाह"])
def advice_cmd(message):
    lang = get_user_lang(message.chat.id)
    bot.send_message(message.chat.id, get_random_advice(lang))

@bot.message_handler(commands=["fact", "तथ्य"])
def fact_cmd(message):
    lang = get_user_lang(message.chat.id)
    bot.send_message(message.chat.id, get_random_number_fact(lang))

@bot.message_handler(commands=["holidays", "छुट्टियाँ"])
def holidays_cmd(message):
    lang = get_user_lang(message.chat.id)
    current_year = datetime.now().year
    bot.send_message(message.chat.id, get_public_holidays(current_year, lang))

@bot.message_handler(commands=["quote", "उद्धरण"])
def quote_cmd(message):
    lang = get_user_lang(message.chat.id)
    bot.send_message(message.chat.id, get_random_quote(lang))

@bot.message_handler(commands=["catfact", "बिल्ली_तथ्य"])
def catfact_cmd(message):
    lang = get_user_lang(message.chat.id)
    bot.send_message(message.chat.id, get_random_cat_fact(lang))

@bot.message_handler(commands=["dictionary", "शब्दकोश"])
def dictionary_cmd(message):
    lang = get_user_lang(message.chat.id)
    text = message.text.strip()
    match = re.search(r'/(?:dictionary|शब्दकोश)\s+(.+)', text, re.IGNORECASE)
    if not match:
        bot.send_message(message.chat.id, "Use: /dictionary <word> (e.g. /dictionary hello)" if lang == "en" else "उपयोग करें: /शब्दकोश <शब्द> (उदाहरण: /शब्दकोश नमस्ते)")
        return
    word = match.group(1).strip()
    bot.send_message(message.chat.id, get_dictionary_definition(word, lang))

@bot.message_handler(commands=["trivia", "सामान्य_ज्ञान"])
def trivia_cmd(message):
    lang = get_user_lang(message.chat.id)
    bot.send_message(message.chat.id, get_random_trivia(lang))

@bot.message_handler(commands=["joke", "चुटकुला"])
def joke_cmd(message):
    lang = get_user_lang(message.chat.id)
    bot.send_message(message.chat.id, get_random_joke(lang))

@bot.message_handler(commands=["exchange", "विनिमय_दर"])
def exchange_cmd(message):
    lang = get_user_lang(message.chat.id)
    text = message.text.strip()
    match = re.search(r'/(?:exchange|विनिमय_दर)\s+([a-zA-Z]{3})\s+([a-zA-Z]{3})', text, re.IGNORECASE)
    if not match:
        bot.send_message(message.chat.id, "Use: /exchange <base_currency> <target_currency> (e.g. /exchange USD INR)" if lang == "en" else "उपयोग करें: /विनिमय_दर <आधार_मुद्रा> <लक्ष्य_मुद्रा> (उदाहरण: /विनिमय_दर USD INR)")
        return
    base_currency = match.group(1).strip()
    target_currency = match.group(2).strip()
    bot.send_message(message.chat.id, get_exchange_rate(base_currency, target_currency, lang))

@bot.message_handler(commands=["horoscope", "राशिफल"])
def horoscope_cmd(message):
    lang = get_user_lang(message.chat.id)
    text = message.text.strip()
    match = re.search(r'/(?:horoscope|राशिफल)\s+(.+)', text, re.IGNORECASE)
    if not match:
        bot.send_message(message.chat.id, "Use: /horoscope <zodiac_sign> (e.g. /horoscope aries)" if lang == "en" else "उपयोग करें: /राशिफल <राशि> (उदाहरण: /राशिफल मेष)")
        return
    sign = match.group(1).strip()
    bot.send_message(message.chat.id, get_horoscope(sign, lang))

@bot.message_handler(commands=["crypto", "क्रिप्टो"])
def crypto_cmd(message):
    lang = get_user_lang(message.chat.id)
    text = message.text.strip()
    match = re.search(r'/(?:crypto|क्रिप्टो)\s+(.+)', text, re.IGNORECASE)
    crypto_id = match.group(1).strip() if match else "90" # Default to Bitcoin
    bot.send_message(message.chat.id, get_crypto_price(crypto_id, lang))

@bot.message_handler(commands=["dog", "कुत्ता"])
def dog_cmd(message):
    lang = get_user_lang(message.chat.id)
    bot.send_message(message.chat.id, get_random_dog_image(lang))

@bot.message_handler(commands=["cat", "बिल्ली"])
def cat_image_cmd(message):
    lang = get_user_lang(message.chat.id)
    bot.send_message(message.chat.id, get_random_cat_image(lang))

@bot.message_handler(commands=["age", "आयु"])
def age_cmd(message):
    lang = get_user_lang(message.chat.id)
    text = message.text.strip()
    match = re.search(r'/(?:age|आयु)\s+(.+)', text, re.IGNORECASE)
    if not match:
        bot.send_message(message.chat.id, "Use: /age <name> (e.g. /age John)" if lang == "en" else "उपयोग करें: /आयु <नाम> (उदाहरण: /आयु जॉन)")
        return
    name = match.group(1).strip()
    bot.send_message(message.chat.id, get_predicted_age(name, lang))

@bot.message_handler(commands=["gender", "लिंग"])
def gender_cmd(message):
    lang = get_user_lang(message.chat.id)
    text = message.text.strip()
    match = re.search(r'/(?:gender|लिंग)\s+(.+)', text, re.IGNORECASE)
    if not match:
        bot.send_message(message.chat.id, "Use: /gender <name> (e.g. /gender Jane)" if lang == "en" else "उपयोग करें: /लिंग <नाम> (उदाहरण: /लिंग जेन)")
        return
    name = match.group(1).strip()
    bot.send_message(message.chat.id, get_predicted_gender(name, lang))

@bot.message_handler(commands=["help", "मदद"])
def help_cmd(message):
    bot.send_message(message.chat.id, "Use buttons or commands like /getarea Garia, /traffic Salt Lake, /weather etc. Daily alert at 7 AM + instant rain push enabled!")

@bot.message_handler(commands=["hindi"])
def set_hindi(message):
    save_user(message.chat.id, "hi")
    bot.send_message(message.chat.id, "✅ Hindi mode activated!", reply_markup=get_keyboard("hi"))

@bot.message_handler(commands=["english"])
def set_english(message):
    save_user(message.chat.id, "en")
    bot.send_message(message.chat.id, "✅ English mode activated.", reply_markup=get_keyboard("en"))

@bot.message_handler(commands=["broadcast"])
def broadcast(message):
    global last_broadcast_time
    if message.chat.id != ADMIN_ID:
        return
    try:
        text = message.text.split(maxsplit=1)[1]
        for uid, _ in get_subscribers():
            try:
                bot.send_message(uid, f"📢 <b>Broadcast:</b>\n\n{text}")
            except:
                pass
        last_broadcast_time = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %I:%M %p")
        bot.reply_to(message, "Broadcast sent!")
    except:
        bot.reply_to(message, "Use: /broadcast Message")

@bot.message_handler(commands=["stats"])
def stats(message):
    if message.chat.id != ADMIN_ID:
        return
    total = len(get_subscribers())
    last = last_broadcast_time or "Never"
    bot.send_message(message.chat.id, f"<b>Bot Stats</b>\n\nSubscribers: {total}\nLast broadcast: {last}\nRain monitoring: Active\nDaily alerts: Active\nArea commands: /getarea & /traffic supported")

# ================== TEXT HANDLER ==================
@bot.message_handler(content_types=["text"])
def handle_text(message):
    lang = get_user_lang(message.chat.id)
    txt = message.text.lower()
    if "weather" in txt or "मौसम" in txt: weather_cmd(message)
    elif "alert" in txt or "अलर्ट" in txt: alert_cmd(message)
    elif "flood" in txt or "बाढ़" in txt: flood_cmd(message)
    elif "tips" in txt or "टिप्स" in txt: tips_cmd(message)
    elif "traffic" in txt or "ट्रैफिक" in txt: traffic_cmd(message)
    elif "subscribe" in txt or "सब्सक्राइब" in txt: subscribe(message)
    elif "unsubscribe" in txt or "अनसब्सक्राइब" in txt: unsubscribe(message)
    elif "emergency" in txt or "इमरजेंसी" in txt: emergency(message)
    elif "feedback" in txt or "फीडबैक" in txt: feedback(message)
    elif "advice" in txt or "सलाह" in txt: advice_cmd(message)
    elif "fact" in txt or "तथ्य" in txt: fact_cmd(message)
    elif "holidays" in txt or "छुट्टियाँ" in txt: holidays_cmd(message)
    elif "quote" in txt or "उद्धरण" in txt: quote_cmd(message)
    elif "cat fact" in txt or "बिल्ली तथ्य" in txt: catfact_cmd(message)
    elif "dictionary" in txt or "शब्दकोश" in txt: dictionary_cmd(message)
    elif "trivia" in txt or "सामान्य ज्ञान" in txt: trivia_cmd(message)
    elif "joke" in txt or "चुटकुला" in txt: joke_cmd(message)
    elif "exchange" in txt or "विनिमय दर" in txt: exchange_cmd(message)
    elif "horoscope" in txt or "राशिफल" in txt: horoscope_cmd(message)
    elif "crypto" in txt or "क्रिप्टो" in txt: crypto_cmd(message)
    elif "dog" in txt or "कुत्ता" in txt: dog_cmd(message)
    elif "cat" in txt or "बिल्ली" in txt: cat_image_cmd(message)
    elif "age" in txt or "आयु" in txt: age_cmd(message)
    elif "gender" in txt or "लिंग" in txt: gender_cmd(message)
    elif "help" in txt or "मदद" in txt: help_cmd(message)

# ================== SCHEDULER THREADS ==================
def start_daily_scheduler():
    print("Daily 7 AM scheduler started...")
    while True:
        now = datetime.now(timezone(timedelta(hours=5, minutes=30)))  # IST
        if now.hour == 7 and now.minute == 0:
            send_daily_alert()
            time.sleep(120)
        time.sleep(30)

# ================== RUN ==================
def run_bot():
    print("Telegram bot polling started...")
    bot.infinity_polling()

if __name__ == "__main__":
    Thread(target=run_bot, daemon=True).start()
    Thread(target=start_daily_scheduler, daemon=True).start()
    Thread(target=rain_monitor, daemon=True).start()
    
    print("Flask web server started...")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
