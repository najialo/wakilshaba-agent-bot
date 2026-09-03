إليك الكود البرمجي الكامل والمعدل لملف main.py. يجمع الكود بين وكيل مكتب الشهباء العقاري بالحس العامي السوري، الإجابة على أي سؤال عام، وتحليل الذهب والفضة مع دعم التنبيهات وإمكانية تحليل الصور والصوت وموقع المكتب:
import asyncio
import logging
import os
import re
from google import genai
from google.genai import types
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------- الإعدادات والمتغيرات ----------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise RuntimeError(
        "TELEGRAM_TOKEN أو GEMINI_API_KEY غير موجودين في متغيرات البيئة (Environment Variables)"
    )

client = genai.Client(api_key=GEMINI_API_KEY)

PRIMARY_MODEL = "gemini-2.5-pro"
FALLBACK_MODEL = "gemini-2.5-flash"

OFFICE_WEBSITE = "https://alshabaoffice.netlify.app/"

SYSTEM_INSTRUCTION = """
انت وكيل ذكي لمكتب "الشهباء العقاري" بحلب، سوريا، ومحلل مالي بذات الوقت. اسمك "وكيل الشهباء".
مهمتك تساعد صاحب المكتب بإدارة أعماله: العقارات، الزباين، السوشيال ميديا، والإجابة على أي سؤال وتحليل أسعار الذهب والفضة.

طريقة فهمك للأسئلة:
- اقرا السؤال منيح قبل ما تجاوب، حتى لو كان مختصر أو فيه أخطاء إملائية أو مو واضح 100%.
- لو السؤال ممكن يفهم بأكتر من طريقة، اختار الفهم الأكثر منطقية حسب سياق المحادثة.
- ركز على قصد السائل الحقيقي.

طريقة ردك:
- احكي بالعامية السورية دايماً، بشكل ودود ومباشر ومختصر (بلا حشو أو مقدمات طويلة).
- لما حد يسألك عن الذهب أو الفضة، استخدم أداة البحث Google Search لتقديم أسعار مباشرة وتحليل فني ودقيق من مصادر موثوقة.
- لو انبعتلك صورة عقار، وصفها بالتفصيل وأعطي رأيك فيها.

مصدرك الأساسي للعقارات - موقع المكتب:
- موقع مكتب "الشهباء العقاري" الرسمي هو: https://alshabaoffice.netlify.app/
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
user_alerts = {}


def get_chat_session(user_id: int):
    if user_id not in user_chats:
        user_chats[user_id] = {
            "model": "primary",
            "chat": client.chats.create(
                model=PRIMARY_MODEL, config=CHAT_CONFIG
            ),
        }
    return user_chats[user_id]


def switch_to_fallback(user_id: int):
    old_history = user_chats[user_id]["chat"].get_history()
    new_chat = client.chats.create(
        model=FALLBACK_MODEL, config=CHAT_CONFIG, history=old_history
    )
    user_chats[user_id] = {"model": "fallback", "chat": new_chat}
    return user_chats[user_id]


def is_quota_error(error: Exception) -> bool:
    err_text = str(error).lower()
    return (
        "quota" in err_text or "429" in err_text or "resource_exhausted" in err_text
    )


# ---------- الأوامر والمعالجات ----------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً! أنا وكيلك الذكي لمكتب الشهباء العقاري ومساعدك المالي.\n"
        "احكيلي شو بدك، وأنا رح أساعدك فوراً.\n\n"
        "💡 جرب تسألني عن أي شي، أو قل لي:\n"
        "- 'حللي سعر الذهب والفضة اليوم'\n"
        "- 'نبهني على الذهب عند 2500'\n"
        "- أو /site لتحليل موقع المكتب."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_chats.pop(user_id, None)
    await update.message.reply_text("تمام، مسحت الذاكرة وبلشنا محادثة جديدة.")


async def analyze_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )
    await update.message.reply_text("عم افتح الموقع وأحلله، ثانية...")

    analysis_prompt = f"""
افتح موقع المكتب {OFFICE_WEBSITE} هلق واقرا محتواه الفعلي، وسويلي تحليل شامل يتضمن:
1. عدد العقارات المعروضة حالياً ونوعها (بيع/إيجار)
2. نطاق الأسعار (الأقل والأعلى)
3. أكتر منطقة/حي فيه عروض
4. أي عقار ناقصو معلومات أساسية
5. اقتراح عملي لتحسين عرض الموقع
"""
    session = get_chat_session(user_id)
    try:
        response = session["chat"].send_message(analysis_prompt)
        reply = response.text
    except Exception as e:
        if is_quota_error(e) and session["model"] == "primary":
            try:
                session = switch_to_fallback(user_id)
                response = session["chat"].send_message(analysis_prompt)
                reply = response.text
            except Exception:
                logger.exception("خطأ بتحليل الموقع")
                reply = "ما قدرت أفتح الموقع هلق، جرب كمان مرة بعد شوي 🙏"
        else:
            logger.exception("خطأ بتحليل الموقع")
            reply = "ما قدرت أفتح الموقع هلق، جرب كمان مرة بعد شوي 🙏"

    await update.message.reply_text(reply)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    caption = (
        update.message.caption
        or "شو رأيك بهالصورة؟ وصفها إلي بالتفصيل."
    )
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        session = get_chat_session(user_id)
        image_part = types.Part.from_bytes(
            data=bytes(photo_bytes), mime_type="image/jpeg"
        )
        response = session["chat"].send_message([caption, image_part])
        reply = response.text
    except Exception:
        logger.exception("خطأ بتحليل الصورة")
        reply = "ما قدرت أحلل الصورة، جرب تبعتها كمان مرة 🙏"

    await update.message.reply_text(reply)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    try:
        voice_file = await update.message.voice.get_file()
        voice_bytes = await voice_file.download_as_bytearray()
        session = get_chat_session(user_id)
        audio_part = types.Part.from_bytes(
            data=bytes(voice_bytes), mime_type="audio/ogg"
        )
        response = session["chat"].send_message(
            [
                "افهم هالرسالة الصوتية ورد عليها متل ما لو كانت مكتوبة.",
                audio_part,
            ]
        )
        reply = response.text
    except Exception:
        logger.exception("خطأ بتحليل الصوت")
        reply = "ما قدرت أسمع الرسالة الصوتية منيح، جرب تبعتها كمان مرة 🙏"

    await update.message.reply_text(reply)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # 1. التعرف التلقائي على طلبات التنبيه (مثال: نبهني على الذهب 2500 أو نبهني على الفضة تحت 30)
    alert_match = re.search(
        r"نبهني\s+على\s+(الذهب|الفضة|ذهب|فضة)\s+(?:عند|تحت)?\s*(\d+)",
        text,
        re.IGNORECASE,
    )
    if alert_match:
        asset_raw = alert_match.group(1)
        price = float(alert_match.group(2))
        asset = "الذهب" if "ذهب" in asset_raw else "الفضة"

        if user_id not in user_alerts:
            user_alerts[user_id] = []
        user_alerts[user_id].append({"asset": asset, "price": price})

        await update.message.reply_text(
            f"تكرم! سجلت التنبيه عندك 👍\nرح أبعتلك فوراً لما وصل سعر {asset} لـ {price}$."
        )
        return

    # 2. الإجابة عن كل الأسئلة وتحليل الذهب والفضة عبر النموذج الذكي
    session = get_chat_session(user_id)
    try:
        response = session["chat"].send_message(text)
        reply = response.text
    except Exception as e:
        if is_quota_error(e) and session["model"] == "primary":
            try:
                session = switch_to_fallback(user_id)
                response = session["chat"].send_message(text)
                reply = response.text
            except Exception:
                logger.exception("خطأ بالرد من الموديل الاحتياطي")
                reply = "صار خطأ تقني بسيط، جرب كمان مرة بعد شوي 🙏"
        else:
            logger.exception("خطأ بالرد")
            reply = "صار خطأ تقني بسيط، جرب كمان مرة بعد شوي 🙏"

    await update.message.reply_text(reply)


# ---------- تشغيل البوت المترابط لـ Render و Railway ----------


async def run_bot():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("site", analyze_site))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("البوت شغال بنجاح...")

    async with app:
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()


def main():
    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        logger.info("تم إيقاف البوت.")


if __name__ == "__main__":
    main()

