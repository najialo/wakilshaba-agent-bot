import os
import re
import logging
from google import genai
from google.genai import types
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------- الإعدادات ----------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise RuntimeError("يرجى التأكد من ضبط TELEGRAM_TOKEN و GEMINI_API_KEY في متغيرات البيئة.")

client = genai.Client(api_key=GEMINI_API_KEY)

PRIMARY_MODEL = "gemini-2.5-pro"
FALLBACK_MODEL = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = """
انت مساعد ذكي ووكيل لمكتب "الشهباء العقاري" بحلب ومحلل مالي بنفس الوقت.
مهمتك:
1. تجاوب على أي سؤال عام أو عقاري أو تحليلي بدقة وسلاسة بالعامية السورية الودودة والمباشرة.
2. لما حد يسألك عن الذهب أو الفضة، استخدم أداة بحث Google لتقديم أسعار مباشرة وتحليل فني ودقيق للسوق من مصادر موثوقة.
3. ركز على قصد السائل الحقيقي واشرك ذكائك الكامل بالرد مثل أي نموذج ذكاء اصطناعي متطور.
"""

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHAT_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_INSTRUCTION,
    tools=[types.Tool(google_search=types.GoogleSearch())],
    temperature=0.4,
    top_p=0.9,
    max_output_tokens=2048,
)

user_chats = {}
# قاموس لتخزين تنبيهات المستخدمين {user_id: [{"asset": "gold", "price": 2500}, ...]}
user_alerts = {}

def get_chat_session(user_id: int):
    if user_id not in user_chats:
        user_chats[user_id] = {
            "model": "primary",
            "chat": client.chats.create(model=PRIMARY_MODEL, config=CHAT_CONFIG),
        }
    return user_chats[user_id]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً بك! أنا جاهز للإجابة على أي سؤال، تحليل أسعار الذهب والفضة، وإدارة أعمالك.\n\n"
        "💡 يمكنك كتابة أفكارك أو أسئلتك مباشرة، أو قول مثلًا:\n"
        "- 'حللي سعر الذهب اليوم'\n"
        "- 'نبهني على الذهب عند 2500'"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # 1. التحقق إذا كانت الرسالة طلب ضبط تنبيه سعر (مثل: نبهني على الذهب 2500)
    alert_match = re.search(r"نبهني\s+على\s+(الذهب|الفضة|ذهب|فضة)\s+(?:عند\s+)?(\d+)", text, re.IGNORECASE)
    if alert_match:
        asset_raw = alert_match.group(1)
        price = float(alert_match.group(2))
        asset = "الذهب" if "ذهب" in asset_raw else "الفضة"

        if user_id not in user_alerts:
            user_alerts[user_id] = []
        user_alerts[user_id].append({"asset": asset, "price": price})

        await update.message.reply_text(f"تمام! تم تسجيل التنبيه. سأنبهك أول ما يصل سعر {asset} إلى {price}$.")
        return

    # 2. الإجابة على أي سؤال عام أو تحليل الأسعار عبر Gemini
    session = get_chat_session(user_id)
    try:
        response = session["chat"].send_message(text)
        reply = response.text
    except Exception:
        logger.exception("خطأ في الرد")
        reply = "صار خطأ تقني بسيط، جرب تبعت السؤال مرة ثانية 🙏"

    await update.message.reply_text(reply)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("البوت شغال...")
    app.run_polling()

if __name__ == "__main__":
    main()
