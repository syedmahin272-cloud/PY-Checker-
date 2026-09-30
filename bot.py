import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import requests
import re
import json
import os
import time

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

# --- DATABASE HANDLING (JSON) ---
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
    if user_id == ADMIN_ID:
        return True
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

def get_user_setting(user_id):
    # Default is 'text', can be 'file'
    return settings_db.get(str(user_id), "text")

def set_user_setting(user_id, format_type):
    settings_db[str(user_id)] = format_type
    save_json(SETTINGS_FILE, settings_db)

# --- BOT MENU ---
def get_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("👤 Profile"), KeyboardButton("💸 Send Points"))
    markup.add(KeyboardButton("⚙️ Output Settings"))
    return markup

# --- CHECKER LOGIC ---
def process_batch(numbers):
    sanitized = [num if num.startswith("+") else "+" + num for num in numbers]
    payload = {
        "auth": CHECKER_AUTH,
        "api_key": CHECKER_API_KEY,
        "phone_numbers": sanitized
    }
    
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
                for num in sanitized: results[num] = "⚠️ API Error"
        else:
            for num in sanitized: results[num] = "⚠ Connection Error"
    except Exception:
        for num in sanitized: results[num] = "⚠️ Timeout/Error"
        
    return results

def bulk_check(numbers):
    all_results = {}
    for i in range(0, len(numbers), 10):
        chunk = numbers[i:i+10]
        chunk_result = process_batch(chunk)
        all_results.update(chunk_result)
        
    # Sort results: "✅ Fresh" numbers go to the top
    sorted_results = dict(sorted(all_results.items(), key=lambda item: 0 if "✅ Fresh" in item[1] else 1))
    return sorted_results

def extract_numbers(text):
    raw_numbers = re.findall(r'\+?\d{7,15}', text)
    seen = set()
    return [x for x in raw_numbers if not (x in seen or seen.add(x))]

# --- ADMIN COMMANDS ---
@bot.message_handler(commands=['addpoint'])
def addpoint_cmd(message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) != 3:
        bot.send_message(message.chat.id, "Usage: `/addpoint <user_id> <amount>`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        amount = int(args[2])
        add_points(target_id, amount)
        bot.send_message(message.chat.id, f"✅ Added {amount} points to user `{target_id}`.", parse_mode="Markdown")
        try:
            bot.send_message(target_id, f"🎉 Admin {ADMIN_USERNAME} added {amount} points to your account!", parse_mode="Markdown")
        except:
            pass
    except:
        bot.send_message(message.chat.id, "⚠️ Invalid format.")

# --- MENU HANDLERS ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    pts = get_points(message.from_user.id)
    pts_text = "Unlimited (Admin)" if pts == float('inf') else f"{pts}"
    
    text = f"🚀 **Premium Telegram Number Checker**\n\n"
    text += f"👤 Your ID: `{message.from_user.id}`\n"
    text += f"💰 Your Points: **{pts_text}**\n\n"
    text += "📝 **How to use:**\n"
    text += "Just send me numbers directly or upload a `.txt` file!\n"
    text += "*(Cost: 1 Point per number)*\n\n"
    text += f"👨‍💻 Admin: {ADMIN_USERNAME}"
    
    bot.send_message(message.chat.id, text, reply_markup=get_main_menu(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "👤 Profile")
def profile_handler(message):
    pts = get_points(message.from_user.id)
    pts_text = "Unlimited 👑" if pts == float('inf') else f"{pts}"
    
    output_format = get_user_setting(message.from_user.id)
    fmt_str = "Text Message 📄" if output_format == "text" else ".txt File 📁"
    
    text = f"👤 **User Profile**\n\n"
    text += f"🆔 ID: `{message.from_user.id}`\n"
    text += f"💰 Balance: **{pts_text} Points**\n"
    text += f"⚙️ Output Format: **{fmt_str}**"
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "⚙️ Output Settings")
def settings_handler(message):
    current = get_user_setting(message.from_user.id)
    
    markup = InlineKeyboardMarkup()
    btn_text = InlineKeyboardButton(text=f"{'✅ ' if current == 'text' else ''}Text Message", callback_data="setfmt_text")
    btn_file = InlineKeyboardButton(text=f"{'✅ ' if current == 'file' else ''}.txt File", callback_data="setfmt_file")
    markup.add(btn_text, btn_file)
    
    bot.send_message(message.chat.id, "Select how you want to receive your checker results:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("setfmt_"))
def callback_format(call):
    new_fmt = call.data.split("_")[1]
    set_user_setting(call.from_user.id, new_fmt)
    bot.answer_callback_query(call.id, f"Output format updated to {new_fmt.upper()}", show_alert=True)
    
    markup = InlineKeyboardMarkup()
    btn_text = InlineKeyboardButton(text=f"{'✅ ' if new_fmt == 'text' else ''}Text Message", callback_data="setfmt_text")
    btn_file = InlineKeyboardButton(text=f"{'✅ ' if new_fmt == 'file' else ''}.txt File", callback_data="setfmt_file")
    markup.add(btn_text, btn_file)
    
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "💸 Send Points")
def sendpoints_handler(message):
    msg = bot.send_message(message.chat.id, "Please send the Target User ID and Amount separated by space.\nExample: `123456789 50`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_send_points)

def process_send_points(message):
    try:
        args = message.text.split()
        if len(args) != 2:
            bot.send_message(message.chat.id, "⚠️ Invalid format. Transfer cancelled.")
            return
            
        target_id = int(args[0])
        amount = int(args[1])
        user_id = message.from_user.id
        
        if amount <= 0:
            bot.send_message(message.chat.id, "Amount must be greater than 0.")
            return
            
        if deduct_points(user_id, amount):
            add_points(target_id, amount)
            bot.send_message(message.chat.id, f"✅ Successfully sent {amount} points to `{target_id}`.", parse_mode="Markdown")
            try:
                bot.send_message(target_id, f"💸 You received {amount} points from ID `{user_id}`!", parse_mode="Markdown")
            except:
                pass
        else:
            bot.send_message(message.chat.id, "❌ Not enough points in your balance.")
    except:
        bot.send_message(message.chat.id, "⚠️ Error: ID and amount must be numbers.")

# --- CHECKING HANDLERS ---
def send_results(chat_id, user_id, results, total_needed):
    pref = get_user_setting(user_id)
    
    output_text = "📊 **Checker Results:**\n\n"
    for num, status in results.items():
        output_text += f"`{num}` ➔ {status}\n"
    output_text += f"\n💰 Points remaining: {get_points(user_id)}"
    
    # If file pref is chosen OR text is too long for Telegram (limit 4096)
    if pref == "file" or len(output_text) > 4000:
        result_filename = f"result_{user_id}_{int(time.time())}.txt"
        with open(result_filename, "w", encoding="utf-8") as f:
            f.write("--- Premium Checker Results ---\n")
            f.write("Fresh numbers are listed at the top!\n\n")
            for num, status in results.items():
                clean_status = status.replace("✅", "[FRESH]").replace("❌", "[REGISTERED]").replace("🔒", "[LOCKED]").replace("🚫", "[BANNED]").replace("⚠️", "[ERROR]")
                f.write(f"{num} - {clean_status}\n")
                
        with open(result_filename, "rb") as f:
            bot.send_document(chat_id, f, caption=f"✅ Checking complete!\n💰 Points remaining: {get_points(user_id)}")
        os.remove(result_filename)
    else:
        bot.send_message(chat_id, output_text, parse_mode="Markdown")

@bot.message_handler(content_types=['text'])
def handle_text_numbers(message):
    if message.text.startswith('/'): return
    if message.text in ["👤 Profile", "💸 Send Points", "⚙️ Output Settings"]: return
    
    numbers = extract_numbers(message.text)
    if not numbers:
        bot.send_message(message.chat.id, "⚠️ No valid phone numbers found.")
        return
        
    user_id = message.from_user.id
    total_needed = len(numbers)
    
    if not deduct_points(user_id, total_needed):
        bot.send_message(message.chat.id, f"❌ Not enough points!\nYou need {total_needed} points, but you have {get_points(user_id)}.")
        return
        
    msg = bot.send_message(message.chat.id, f"🔍 Checking {total_needed} numbers... Please wait ⏳")
    results = bulk_check(numbers)
    
    bot.delete_message(message.chat.id, msg.message_id)
    send_results(message.chat.id, user_id, results, total_needed)

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    if not message.document.file_name.endswith('.txt'):
        bot.send_message(message.chat.id, "⚠️ Please upload a `.txt` file only.")
        return
        
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        content = downloaded_file.decode('utf-8')
        
        numbers = extract_numbers(content)
        if not numbers:
            bot.send_message(message.chat.id, "⚠️ No valid numbers found in the file.")
            return
            
        user_id = message.from_user.id
        total_needed = len(numbers)
        
        if not deduct_points(user_id, total_needed):
            bot.send_message(message.chat.id, f"❌ Not enough points!\nFile contains {total_needed} numbers, but you have {get_points(user_id)} points.")
            return
            
        msg = bot.send_message(message.chat.id, f"📁 Processing {total_needed} numbers from file... ⏳")
        results = bulk_check(numbers)
        
        bot.delete_message(message.chat.id, msg.message_id)
        send_results(message.chat.id, user_id, results, total_needed)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Error processing file: {str(e)}")

# --- START BOT ---
print("Checker Bot is running...")
bot.infinity_polling(skip_pending=True)
