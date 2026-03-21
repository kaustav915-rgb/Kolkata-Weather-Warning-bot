import telebot
from telebot import types
import requests
import sqlite3
import os
from datetime import datetime, timezone, timedelta
from flask import Flask
from threading import Thread
import time

# ================== CONFIG ==================
TOKEN = os.environ.get("BOT_TOKEN")
API_KEY = os.environ.get("OPENWEATHER_KEY")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# Flask for UptimeRobot ping (keeps Render free tier awake)
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

# ================== GLOBALS FOR PROACTIVE FEATURES ==================
last_rain_state = False
last_broadcast_time = None
last_weather_desc = "haze"  # initial

# ================== UPDATED FLOOD ZONES (2025-2026) ==================
FLOOD_ZONES = [
    "Garia", "Jadavpur", "Bansdroni", "Bijoygarh", "Tollygunge",
    "Jodhpur Park", "Kalighat", "Topsia", "Ballygunge", "Alipore",
    "Behala", "Salt Lake", "Rajarhat", "New Town", "EM Bypass",
    "Howrah", "Sonarpur", "Park Street area"
]

TOP_3_FLOOD = ["Garia", "Jadavpur", "Salt Lake"]  # Most critical today

# ================== KEYBOARD (expanded) ==================
def get_keyboard(lang="en"):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if lang == "hi":
        markup.add("🌧️ मौसम", "⚠️ अलर्ट", "🌊 बाढ़ क्षेत्र", "💡 टिप्स")
        markup.add("📲 सब्सक्राइब", "❌ अनसब्सक्राइब", "🚨 इमरजेंसी", "📝 फीडबैक")
        markup.add("❓ मदद")
    else:
        markup.add("🌧️ Weather", "⚠️ Alert", "🌊 Flood Zones", "💡 Tips")
        markup.add("📲 Subscribe", "❌ Unsubscribe", "🚨 Emergency", "📝 Feedback")
        markup.add("❓ Help")
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

# ================== WEATHER FETCH (same as before - current endpoint) ==================
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
        last_weather_desc = desc.lower()  # for proactive

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
    except:
        return "Weather fetch error. Try again."

# ================== DAILY MORNING ALERT (7:00 AM IST) ==================
def send_daily_alert():
    global last_broadcast_time
    subscribers = get_subscribers()
    if not subscribers:
        return

    weather_en = get_weather("en")
    weather_hi = get_weather("hi")
    top3 = ", ".join(TOP_3_FLOOD)

    traffic_tip = "🚗 Traffic: Avoid EM Bypass & low areas during rain. Use Metro/Uber."
    power_tip = "🔌 Power cut risk high today — charge phones & use 1912 (WBSEDCL)."

    for user_id, lang in subscribers:
        try:
            msg = f"""🌅 <b>Good Morning Kolkata!</b>

{weather_en if lang == 'en' else weather_hi}

🚨 <b>Today's Top Flood Zones to AVOID:</b>
• {top3}

{traffic_tip}
{power_tip}

Stay safe! Stay subscribed. 🌧️"""
            bot.send_message(user_id, msg)
        except:
            pass
    last_broadcast_time = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %I:%M %p")

# ================== RAIN START/STOP PROACTIVE PUSH ==================
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
            # Quick current check
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
        time.sleep(600)  # every 10 minutes

# ================== HANDLERS (same structure + new ones) ==================
@bot.message_handler(commands=["start"])
def start(message):
    lang = get_user_lang(message.chat.id)
    save_user(message.chat.id, lang)
    text = "🌧️ <b>Welcome to Kolkata Rain & Flood Alert Bot!</b>\n\nLive weather + proactive rain alerts + daily 7 AM summary.\nUse buttons 👇" if lang == "en" else "🌧️ <b>स्वागत है!</b>\n\nलाइव मौसम + बारिश अलर्ट + सुबह 7 बजे डेली समरी। बटन इस्तेमाल करें 👇"
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
        bot.reply_to(message, "Use: /feedback Your suggestion here (e.g. add more areas)")

@bot.message_handler(commands=["help", "मदद"])
def help_cmd(message):
    bot.send_message(message.chat.id, "Use buttons or type commands. Daily alert at 7 AM + instant rain push enabled!")

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
    bot.send_message(message.chat.id, f"<b>Bot Stats</b>\n\nSubscribers: {total}\nLast broadcast: {last}\nRain monitoring: Active\nDaily alerts: Active")

# ================== TEXT HANDLER ==================
@bot.message_handler(content_types=["text"])
def handle_text(message):
    lang = get_user_lang(message.chat.id)
    txt = message.text.lower()
    if "weather" in txt or "मौसम" in txt: weather_cmd(message)
    elif "alert" in txt or "अलर्ट" in txt: alert_cmd(message)
    elif "flood" in txt or "बाढ़" in txt: flood_cmd(message)
    elif "tips" in txt or "टिप्स" in txt: tips_cmd(message)
    elif "subscribe" in txt or "सब्सक्राइब" in txt: subscribe(message)
    elif "unsubscribe" in txt or "अनसब्सक्राइब" in txt: unsubscribe(message)
    elif "emergency" in txt or "इमरजेंसी" in txt: emergency(message)
    elif "feedback" in txt or "फीडबैक" in txt: feedback(message)
    elif "help" in txt or "मदद" in txt: help_cmd(message)

# ================== SCHEDULER THREADS ==================
def start_daily_scheduler():
    print("Daily 7 AM scheduler started...")
    while True:
        now = datetime.now(timezone(timedelta(hours=5, minutes=30)))  # IST
        if now.hour == 7 and now.minute == 0:
            send_daily_alert()
            time.sleep(120)  # prevent double trigger
        time.sleep(30)

# ================== RUN EVERYTHING ==================
def run_bot():
    print("Telegram bot polling started...")
    bot.infinity_polling()

if __name__ == "__main__":
    # Start all background services
    Thread(target=run_bot, daemon=True).start()
    Thread(target=start_daily_scheduler, daemon=True).start()
    Thread(target=rain_monitor, daemon=True).start()
    
    print("Flask web server for UptimeRobot started...")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
