import os
import logging
from google import genai
from google.genai import types
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ---------- الإعدادات ----------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN مو موجود بمتغيرات البيئة (Environment Variables)")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY مو موجود بمتغيرات البيئة (Environment Variables)")

client = genai.Client(api_key=GEMINI_API_KEY)

PRIMARY_MODEL = "gemini-2.5-pro"
FALLBACK_MODEL = "gemini-2.5-flash"

OFFICE_WEBSITE = "https://alshabaoffice.netlify.app/"

SYSTEM_INSTRUCTION = """
انت وكيل ذكي لمكتب "الشهباء العقاري" بحلب، سوريا. اسمك "وكيل الشهباء".
مهمتك تساعد صاحب المكتب بإدارة أعماله: العقارات، الزباين، السوشيال ميديا.

طريقة فهمك للأسئلة:
- اقرا السؤال منيح قبل ما تجاوب، حتى لو كان مختصر أو فيه أخطاء إملائية أو مو واضح 100%
- لو السؤال ممكن يفهم بأكتر من طريقة، اختار الفهم الأكثر منطقية حسب سياق المحادثة، وما تسأل أسئلة توضيحية إلا لو فعلاً ما فيك تكمل بدونها
- ركز على قصد السائل الحقيقي مو بس الكلمات الحرفية

طريقة ردك:
- احكي بالعامية السورية دايماً، بشكل ودود ومباشر ومختصر (بلا حشو أو مقدمات طويلة)
- لو حد سألك سؤال عن عقار أو زبون وما عندك معلومة كافية، قول هيك بصراحة بدل ما تخترع جواب
- لو الطلب فيه كذا خطوة أو جزء، رتب جوابك بنقاط واضحة
- لو انبعتلك صورة عقار، وصفها بالتفصيل (نوع العقار، حالته، الغرف، الإضاءة) وأعطي رأيك فيها لو حد طلب

مصدرك الأساسي - موقع المكتب:
- موقع مكتب "الشهباء العقاري" الرسمي هو: https://alshabaoffice.netlify.app/ - هاد **المصدر الأساسي** لأي معلومة عن العقارات المعروضة، الأسعار، الخدمات، أو بيانات المكتب
- أي سؤال متعلق بالعقارات المعروضة أو معلومات المكتب، افتح الموقع فعلياً واقرا محتواه الحقيقي بدل ما تخمن أو تعتمد على معلومة قديمة
- لو الموقع تحدّث (عقار جديد، سعر تغير)، اعتمد دايماً على آخر نسخة تشوفها لما تفتحه، مو على أي شي حكيته بمحادثة سابقة

قدرات البحث والتحليل:
- عندك إمكانية تبحث فعلياً بالإنترنت (Google Search) - استخدمها لما حد يسألك عن أسعار عقارات مشابهة بالسوق (تانية عن موقع المكتب)، أو أي معلومة محتاجة بحث فعلي وحديث
- عندك إمكانية تفتح وتقرا أي رابط يبعتلك ياه صاحب المكتب مباشرة (زي رابط منشور، أو مقالة) وتحلل محتواه
- لما تقارن أسعار أو منشورات، وضح مصدر المعلومة (من وين جبتها) واذكر إنها تقديرية إذا ما لقيت مصدر دقيق 100%
- لما حد يسألك ليش منشور معين نجح أو انتشر، حلل أسلوب الكتابة والكلمات المستخدمة واقترح كيف يطبق نفس الأسلوب على منشور جديد
- ما فيك "تتصفح" فيسبوك أو إنستجرام أو أي منصة تواصل بشكل مستمر ولحالك (هاد غير متاح تقنياً وممنوع من قوانين هالمنصات) - بس فيك تحلل أي رابط منشور محدد يبعتلك ياه صاحب المكتب، أو تلاقي منشورات عامة ظاهرة بنتائج البحث
"""

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHAT_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_INSTRUCTION,
    tools=[
        types.Tool(google_search=types.GoogleSearch()),
        types.Tool(url_context=types.UrlContext()),
    ],
    temperature=0.4,
    top_p=0.9,
    max_output_tokens=2048,
)

user_chats = {}


def get_chat_session(user_id: int):
    if user_id not in user_chats:
        user_chats[user_id] = {
            "model": "primary",
            "chat": client.chats.create(model=PRIMARY_MODEL, config=CHAT_CONFIG),
        }
    return user_chats[user_id]


def switch_to_fallback(user_id: int):
    old_history = user_chats[user_id]["chat"].get_history()
    new_chat = client.chats.create(model=FALLBACK_MODEL, config=CHAT_CONFIG, history=old_history)
    user_chats[user_id] = {"model": "fallback", "chat": new_chat}
    return user_chats[user_id]


def is_quota_error(error: Exception) -> bool:
    err_text = str(error).lower()
    return "quota" in err_text or "429" in err_text or "resource_exhausted" in err_text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً! أنا وكيلك الذكي لمكتب الشهباء العقاري.\n"
        "احكيلي شو بدك، وأنا رح أساعدك.\n\n"
        "جرب /site لتحليل شامل فوري لموقع المكتب."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_chats.pop(user_id, None)
    await update.message.reply_text("تمام، مسحت الذاكرة وبلشنا محادثة جديدة.")


async def analyze_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    await update.message.reply_text("عم افتح الموقع وأحلله، ثانية...")

    analysis_prompt = f"""
افتح موقع المكتب {OFFICE_WEBSITE} هلق واقرا محتواه الفعلي، وسويلي تحليل شامل يتضمن:

1. عدد العقارات المعروضة حالياً ونوعها (بيع/إيجار)
2. نطاق الأسعار (الأقل والأعلى) ولو في تفاوت كبير وضحه
3. أكتر منطقة/حي فيه عروض
4. أي عقار ناقصو معلومات أساسية (صور، سعر، وصف) لو لاحظت هيك
5. اقتراح عملي واحد أو اثنين لتحسين عرض الموقع أو زيادة فرص البيع

رتب جوابك بنقاط واضحة ومختصرة.
"""

    try:
        session = get_chat_session(user_id)
        response = session["chat"].send_message(analysis_prompt)
        reply = response.text
    except Exception as e:
        if is_quota_error(e) and session["model"] == "primary":
            try:
                session = switch_to_fallback(user_id)
                response = session["chat"].send_message(analysis_prompt)
                reply = response.text
            except Exception:
                logger.exception("خطأ بتحليل الموقع من الموديل الاحتياطي")
                reply = "ما قدرت أفتح الموقع هلق، جرب كمان مرة بعد شوي 🙏"
        else:
            logger.exception("خطأ بتحليل الموقع")
            reply = "ما قدرت أفتح الموقع هلق، جرب كمان مرة بعد شوي 🙏"

    await update.message.reply_text(reply)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    caption = update.message.caption or "شو رأيك بهالصورة؟ وصفها إلي بالتفصيل."

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()

        session = get_chat_session(user_id)
        image_part = types.Part.from_bytes(data=bytes(photo_bytes), mime_type="image/jpeg")

        response = session["chat"].send_message([caption, image_part])
        reply = response.text
    except Exception:
        logger.exception("خطأ بتحليل الصورة")
        reply = "ما قدرت أحلل الصورة، جرب تبعتها كمان مرة 🙏"

    await update.message.reply_text(reply)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        voice_file = await update.message.voice.get_file()
        voice_bytes = await voice_file.download_as_bytearray()

        session = get_chat_session(user_id)
        audio_part = types.Part.from_bytes(data=bytes(voice_bytes), mime_type="audio/ogg")

        response = session["chat"].send_message(
            ["افهم هالرسالة الصوتية ورد عليها متل ما لو كانت مكتوبة.", audio_part]
        )
        reply = response.text
    except Exception:
        logger.exception("خطأ بتحليل الرسالة الصوتية")
        reply = "ما قدرت أسمع الرسالة الصوتية منيح، جرب تبعتها كمان مرة أو اكتب سؤالك 🙏"

    await update.message.reply_text(reply)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    session = get_chat_session(user_id)

    try:
        response = session["chat"].send_message(text)
        reply = response.text
    except Exception as e:
        if is_quota_error(e) and session["model"] == "primary":
            logger.warning("انتهت حصة %s، جاري التحول لـ %s", PRIMARY_MODEL, FALLBACK_MODEL)
            try:
                session = switch_to_fallback(user_id)
                response = session["chat"].send_message(text)
                reply = response.text
            except Exception:
                logger.exception("خطأ بالرد من الموديل الاحتياطي كمان")
                reply = "صار خطأ تقني بسيط، جرب كمان مرة بعد شوي 🙏"
        else:
            logger.exception("خطأ بالرد من Gemini")
            reply = "صار خطأ تقني بسيط، جرب كمان مرة بعد شوي 🙏"

    await update.message.reply_text(reply)


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("site", analyze_site))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("البوت شغال بطريقة Polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
