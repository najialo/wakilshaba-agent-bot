import asyncio
import base64
import logging
import os
import re

from groq import Groq
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
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise RuntimeError(
        "TELEGRAM_TOKEN أو GROQ_API_KEY غير موجودين في متغيرات البيئة (Environment Variables)"
    )

client = Groq(api_key=GROQ_API_KEY)

TEXT_MODEL = "llama-3.3-70b-versatile"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
AUDIO_MODEL = "whisper-large-v3"

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
- لما حد يسألك عن الذهب أو الفضة، أعطي تحليل فني عام حسب معرفتك، ونبّه إنه الأسعار تقريبية ومش لحظية لأنه ما عندك اتصال مباشر بالإنترنت هلق.
- لو انبعتلك صورة عقار، وصفها بالتفصيل وأعطي رأيك فيها.

مصدرك الأساسي للعقارات - موقع المكتب:
- موقع مكتب "الشهباء العقاري" الرسمي هو: https://alshabaoffice.netlify.app/
"""

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 20  # عدد رسائل المحادثة المحفوظة لكل مستخدم (بدون العد system)

user_histories = {}
user_alerts = {}


def get_history(user_id: int):
    if user_id not in user_histories:
        user_histories[user_id] = [
            {"role": "system", "content": SYSTEM_INSTRUCTION}
        ]
    return user_histories[user_id]


def trim_history(history):
    if len(history) > MAX_HISTORY_MESSAGES + 1:
        history[:] = [history[0]] + history[-MAX_HISTORY_MESSAGES:]


def chat_with_groq(user_id: int, user_content):
    history = get_history(user_id)
    history.append({"role": "user", "content": user_content})
    trim_history(history)

    completion = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=history,
        temperature=0.4,
        max_tokens=2048,
    )
    reply = completion.choices[0].message.content
    history.append({"role": "assistant", "content": reply})
    trim_history(history)
    return reply


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
    user_histories.pop(user_id, None)
    await update.message.reply_text("تمام، مسحت الذاكرة وبلشنا محادثة جديدة.")


async def analyze_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )
    await update.message.reply_text("عم افكر بموقع المكتب...")

    analysis_prompt = f"""
موقع مكتب الشهباء العقاري هو {OFFICE_WEBSITE}. بما إنه ما عندك اتصال مباشر بالإنترنت هلق،
اعطيني نصايح عامة كيف أحسّن عرض العقارات على موقع زي هيك (وصف واضح، صور كتيرة، سعر ونطاق، الحي، معلومات التواصل)
وشو أهم نقاط لازم أراجعها بنفسي على الموقع.
"""
    try:
        reply = chat_with_groq(user_id, analysis_prompt)
    except Exception:
        logger.exception("خطأ بتحليل الموقع")
        reply = "ما قدرت أحلل الموضوع هلق، جرب كمان مرة بعد شوي 🙏"

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
        b64_image = base64.b64encode(bytes(photo_bytes)).decode("utf-8")
        image_data_url = f"data:image/jpeg;base64,{b64_image}"

        completion = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": caption},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                },
            ],
            temperature=0.4,
            max_tokens=1024,
        )
        reply = completion.choices[0].message.content

        history = get_history(user_id)
        history.append({"role": "user", "content": f"[صورة] {caption}"})
        history.append({"role": "assistant", "content": reply})
        trim_history(history)
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

        transcription = client.audio.transcriptions.create(
            file=("voice.ogg", bytes(voice_bytes)),
            model=AUDIO_MODEL,
        )
        text = transcription.text

        reply = chat_with_groq(user_id, text)
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

    try:
        reply = chat_with_groq(user_id, text)
    except Exception:
        logger.exception("خطأ بالرد")
        reply = "صار خطأ تقني بسيط، جرب كمان مرة بعد شوي 🙏"

    await update.message.reply_text(reply)


# ---------- تشغيل البوت ----------


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
