import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import requests
import re
import json
import os
import time
import threading
from datetime import date
from flask import Flask

# --- CONFIGURATION ---
BOT_TOKEN = "8931620940:AAFGzqvOeRQ_Ois4oC8G28UQD6t5txsYx2U"
ADMIN_ID = 7266067201
ADMIN_USERNAME = "@syedmahinislam"

CHECKER_URL = "http://api.agbots.site:8080/check/"
CHECKER_AUTH = "user8354"
CHECKER_API_KEY = "SIGUzg7Xf7euGs8B"

DB_FILE = "points.json"
SETTINGS_FILE = "settings.json"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

user_buffers = {} # Smart Batching er jonno buffer

# --- DATABASE HANDLING ---
def load_json(file_name):
    if os.path.exists(file_name):
        try:
            with open(file_name, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_json(file_name, data):
    with open(file_name, "w") as f:
        json.dump(data, f, indent=4)

db = load_json(DB_FILE)
settings_db = load_json(SETTINGS_FILE)

def get_points(user_id):
    if user_id == ADMIN_ID:
        return float('inf') 
    return db.get(str(user_id), 0)

def deduct_points(user_id, amount):
    if user_id == ADMIN_ID: return True
    current = get_points(user_id)
    if current >= amount:
        db[str(user_id)] = current - amount
        save_json(DB_FILE, db)
        return True
    return False

def add_points(user_id, amount):
    current = db.get(str(user_id), 0)
    db[str(user_id)] = current + amount
    save_json(DB_FILE, db)

def get_user_settings(user_id):
    user_data = settings_db.get(str(user_id), {})
    if isinstance(user_data, str): 
        user_data = {"format": user_data}
    if "format" not in user_data: user_data["format"] = "text"
    if "last_bonus" not in user_data: user_data["last_bonus"] = ""
    return user_data

def save_user_settings(user_id, data):
    settings_db[str(user_id)] = data
    save_json(SETTINGS_FILE, settings_db)

# --- BOT MENU ---
def get_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("👤 Profile"), KeyboardButton("💸 Send Points"))
    markup.add(KeyboardButton("🎁 Daily Bonus"), KeyboardButton("⚙️ Output Settings"))
    return markup

# --- CHECKER LOGIC ---
def process_batch(numbers):
    sanitized = [num if num.startswith("+") else "+" + num for num in numbers]
    payload = {"auth": CHECKER_AUTH, "api_key": CHECKER_API_KEY, "phone_numbers": sanitized}
    results = {}
    try:
        response = requests.get(CHECKER_URL, json=payload, timeout=60)
        if response.status_code == 200:
            data = response.json()
            if str(data.get("status")) == "200":
                result_obj = data.get("result_obj", {})
                for num in sanitized:
                    raw_status = result_obj.get(num) or result_obj.get(num.replace("+", ""))
                    if not raw_status:
                        results[num] = "⚠️ Check Failed"
                        continue
                    status_str = str(raw_status).lower().strip()
                    if any(s in status_str for s in ["unoccupied", "phone_number_unoccupied", "unregistered", "not_registered", "not_occupied", "free", "fresh", "available", "ready", "allow", "ok", "valid", "clean", "false", "0", "no_account", "does_not_exist"]):
                        results[num] = "✅ Fresh"
                    elif any(s in status_str for s in ["flood", "locked", "lock", "wait", "restricted", "2fa", "password", "has_password"]):
                        results[num] = "🔒 Locked"
                    elif any(s in status_str for s in ["banned", "ban", "blocked"]) and "not_" not in status_str:
                        results[num] = "🚫 Banned"
                    elif any(s in status_str for s in ["occupied", "phone_number_occupied", "registered", "taken", "used", "true", "1"]):
                        results[num] = "❌ Registered"
                    else:
                        results[num] = "⚠️ Check Failed"
            else:
                for num in sanitized: results[num] = "⚠ API Error"
        else:
            for num in sanitized: results[num] = "⚠ Connection Error"
    except:
        for num in sanitized: results[num] = "⚠️ Timeout/Error"
    return results

def bulk_check(numbers):
    all_results = {}
    for i in range(0, len(numbers), 10):
        chunk = numbers[i:i+10]
        all_results.update(process_batch(chunk))
    # Sort: Fresh at top
    return dict(sorted(all_results.items(), key=lambda item: 0 if "✅" in item[1] else 1))

def extract_numbers(text):
    return re.findall(r'\+?\d{7,15}', text)

# --- ADMIN COMMANDS ---
@bot.message_handler(commands=['stats'])
def stats_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    total_users = len(db)
    total_points = sum([v for k, v in db.items() if str(k) != str(ADMIN_ID)])
    bot.send_message(message.chat.id, f"📊 **Admin Stats**\n\n👥 Total Users: {total_users}\n💰 Points in Market: {total_points}", parse_mode="Markdown")

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    msg_text = message.text.replace('/broadcast ', '', 1)
    if msg_text == '/broadcast':
        bot.send_message(message.chat.id, "Usage: `/broadcast <message>`", parse_mode="Markdown")
        return
    bot.send_message(message.chat.id, "📢 Broadcasting message...")
    success, failed = 0, 0
    for uid in db.keys():
        try:
            bot.send_message(uid, f"📢 **Announcement:**\n\n{msg_text}", parse_mode="Markdown")
            success += 1
            time.sleep(0.05)
        except:
            failed += 1
    bot.send_message(message.chat.id, f"✅ Broadcast Complete!\nSent: {success} | Failed: {failed}")

@bot.message_handler(commands=['addpoint'])
def addpoint_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) != 3: return
    try:
        target_id, amount = int(args[1]), int(args[2])
        add_points(target_id, amount)
        bot.send_message(message.chat.id, f"✅ Added {amount} points to `{target_id}`.", parse_mode="Markdown")
        try: bot.send_message(target_id, f"🎉 Admin {ADMIN_USERNAME} added {amount} points to your account!", parse_mode="Markdown")
        except: pass
    except: pass

# --- MENU HANDLERS ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    pts = get_points(message.from_user.id)
    pts_text = "Unlimited (Admin)" if pts == float('inf') else f"{pts}"
    text = f"🚀 **Telegram Number Checker**\n\n👤 ID: `{message.from_user.id}`\n💰 Balance: **{pts_text}**\n\n📝 **How to use:**\nSend me numbers directly or upload a `.txt` file.\n*(Cost: 1 Point per check)*\n\n👨‍💻 Admin: {ADMIN_USERNAME}"
    if str(message.from_user.id) not in db: add_points(message.from_user.id, 0)
    bot.send_message(message.chat.id, text, reply_markup=get_main_menu(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "👤 Profile")
def profile_handler(message):
    pts = get_points(message.from_user.id)
    pts_text = "Unlimited" if pts == float('inf') else f"{pts}"
    output_format = get_user_settings(message.from_user.id)["format"]
    fmt_str = "Text Message" if output_format == "text" else ".txt File"
    bot.send_message(message.chat.id, f"👤 **Profile**\n\n🆔 ID: `{message.from_user.id}`\n💰 Balance: **{pts_text}**\n⚙️ Output: **{fmt_str}**", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🎁 Daily Bonus")
def daily_bonus_handler(message):
    user_id = message.from_user.id
    settings = get_user_settings(user_id)
    today = str(date.today())
    if settings["last_bonus"] == today:
        bot.send_message(message.chat.id, "⚠️ Tumi ajker bonus already niyecho. Agamikal abar try koro!")
    else:
        settings["last_bonus"] = today
        save_user_settings(user_id, settings)
        add_points(user_id, 5)
        bot.send_message(message.chat.id, "🎉 **Success!**\nTumi ajker 5ti FREE check point peyecho!", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "⚙️ Output Settings")
def settings_handler(message):
    current = get_user_settings(message.from_user.id)["format"]
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text=f"{'✅ ' if current == 'text' else ''}Text Message", callback_data="setfmt_text"), 
               InlineKeyboardButton(text=f"{'✅ ' if current == 'file' else ''}.txt File", callback_data="setfmt_file"))
    bot.send_message(message.chat.id, "Select output format:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("setfmt_"))
def callback_format(call):
    new_fmt = call.data.split("_")[1]
    settings = get_user_settings(call.from_user.id)
    settings["format"] = new_fmt
    save_user_settings(call.from_user.id, settings)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text=f"{'✅ ' if new_fmt == 'text' else ''}Text Message", callback_data="setfmt_text"),
               InlineKeyboardButton(text=f"{'✅ ' if new_fmt == 'file' else ''}.txt File", callback_data="setfmt_file"))
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "💸 Send Points")
def sendpoints_handler(message):
    msg = bot.send_message(message.chat.id, "Target User ID and Amount separated by space.\nExample: `123456789 50`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda m: process_send_points(m))

def process_send_points(message):
    try:
        args, user_id = message.text.split(), message.from_user.id
        if len(args) != 2: return bot.send_message(message.chat.id, "⚠️ Invalid format.")
        target_id, amount = int(args[0]), int(args[1])
        if amount <= 0: return bot.send_message(message.chat.id, "Amount must be > 0.")
        if deduct_points(user_id, amount):
            add_points(target_id, amount)
            bot.send_message(message.chat.id, f"✅ Sent {amount} points to `{target_id}`.", parse_mode="Markdown")
            try: bot.send_message(target_id, f"💸 Received {amount} points from ID `{user_id}`!", parse_mode="Markdown")
            except: pass
        else: bot.send_message(message.chat.id, "❌ Not enough balance.")
    except: bot.send_message(message.chat.id, "⚠️ Error: Invalid numbers.")

# --- CHECKING HANDLERS & SMART BATCHING ---
def send_results(chat_id, user_id, results, loading_msg_id=None):
    pref = get_user_settings(user_id)["format"]
    
    total = len(results)
    fresh_count = sum(1 for status in results.values() if "✅" in status)
    bad_count = total - fresh_count
    
    # Ultra-Minimal Professional Formatting
    output_text = "**System Report**\n"
    output_text += "━━━━━━━━━━━━━━━━━━━━\n"
    output_text += f"Total: {total}  |  Fresh: {fresh_count}  |  Bad: {bad_count}\n\n"
    
    prev_was_fresh = None
    for num, status in results.items(): 
        if "✅" in status: indicator = "✅"
        elif "🚫" in status: indicator = "🚫"
        elif "🔒" in status: indicator = "🔒"
        else: indicator = "❌"
        
        is_fresh = (indicator == "✅")
        if prev_was_fresh is True and not is_fresh:
            output_text += "\n"
            
        output_text += f"`{num}`  {indicator}\n"
        prev_was_fresh = is_fresh
        
    output_text += "\n━━━━━━━━━━━━━━━━━━━━\n"
    pts = get_points(user_id)
    pts_text = "Unlimited" if pts == float('inf') else f"{pts}"
    output_text += f"Balance: {pts_text}"
    
    if loading_msg_id:
        try: bot.delete_message(chat_id, loading_msg_id)
        except: pass

    if pref == "file" or len(output_text) > 4000:
        fname = f"result_{user_id}_{int(time.time())}.txt"
        with open(fname, "w", encoding="utf-8") as f:
            f.write("SYSTEM REPORT\n")
            f.write("--------------------------\n")
            f.write(f"Total: {total} | Fresh: {fresh_count} | Bad: {bad_count}\n\n")
            
            file_prev_fresh = None
            for num, status in results.items():
                is_fresh = ("✅" in status)
                if file_prev_fresh is True and not is_fresh:
                    f.write("\n")
                if "✅" in status: c_status = "[FRESH]"
                elif "🚫" in status: c_status = "[BANNED]"
                elif "🔒" in status: c_status = "[LOCKED]"
                else: c_status = "[REG]"
                f.write(f"{num}  {c_status}\n")
                file_prev_fresh = is_fresh
                
        with open(fname, "rb") as f:
            bot.send_document(chat_id, f, caption=f"**Report Generated**\nTotal: {total} | Fresh: {fresh_count}\nBalance: {pts_text}", parse_mode="Markdown")
        os.remove(fname)
    else:
        bot.send_message(chat_id, output_text, parse_mode="Markdown")

def process_user_buffer(user_id, chat_id):
    data = user_buffers.pop(user_id, None)
    if not data or not data['numbers']: return
    
    seen = set()
    unique_numbers = [x for x in data['numbers'] if not (x in seen or seen.add(x))]
    total_needed = len(unique_numbers)
    
    if not deduct_points(user_id, total_needed):
        bot.send_message(chat_id, f"❌ Not enough balance!\nNeed {total_needed}, have {get_points(user_id)}.")
        return
        
    msg = bot.send_message(chat_id, f"🔍 Processing {total_needed} items...")
    results = bulk_check(unique_numbers)
    send_results(chat_id, user_id, results, msg.message_id)

@bot.message_handler(content_types=['text'])
def handle_text_numbers(message):
    if message.text.startswith('/') or message.text in ["👤 Profile", "💸 Send Points", "⚙️ Output Settings", "🎁 Daily Bonus"]: return
    numbers = extract_numbers(message.text)
    if not numbers: return
    
    user_id = message.from_user.id
    if user_id in user_buffers:
        user_buffers[user_id]['timer'].cancel()
        user_buffers[user_id]['numbers'].extend(numbers)
    else:
        user_buffers[user_id] = {'numbers': numbers}
        
    timer = threading.Timer(2.0, process_user_buffer, args=[user_id, message.chat.id])
    user_buffers[user_id]['timer'] = timer
    timer.start()

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    if not message.document.file_name.endswith('.txt'): return bot.send_message(message.chat.id, "⚠️ Only `.txt` files allowed.")
    try:
        content = bot.download_file(bot.get_file(message.document.file_id).file_path).decode('utf-8')
        numbers = list(dict.fromkeys(extract_numbers(content)))
        if not numbers: return bot.send_message(message.chat.id, "⚠️ No valid numbers found.")
        
        user_id, total_needed = message.from_user.id, len(numbers)
        if not deduct_points(user_id, total_needed):
            return bot.send_message(message.chat.id, f"❌ Not enough balance!\nNeed {total_needed}, have {get_points(user_id)}.")
            
        msg = bot.send_message(message.chat.id, f"📁 Processing {total_needed} items...")
        send_results(message.chat.id, user_id, bulk_check(numbers), msg.message_id)
    except:
        bot.send_message(message.chat.id, "⚠️ File processing error.")

# --- RENDER WEB SERVER ---
@app.route('/')
def index(): return "Checker Bot is Alive on Render!"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# --- START BOT ---
if __name__ == "__main__":
    print("Starting Web Server for Render...")
    threading.Thread(target=run_server, daemon=True).start()
    
    print("Starting Telegram Bot Polling...")
    bot.infinity_polling(skip_pending=True)
