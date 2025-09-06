import os, logging, asyncio, sqlite3
from datetime import datetime, timezone
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, ContextTypes
from src.rss_collect import fetch_rss_batch
from src.score import Scorer, load_rules

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
DB_PATH = "bot.db"
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN env var")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS sources(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL, url TEXT NOT NULL, created_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS config(
        key TEXT PRIMARY KEY, val TEXT)""")
    return conn

def set_config(key, val):
    conn = db()
    conn.execute("INSERT INTO config(key,val) VALUES(?,?) "
                 "ON CONFLICT(key) DO UPDATE SET val=excluded.val", (key, val))
    conn.commit(); conn.close()

def get_config(key, default=None):
    conn = db(); cur = conn.execute("SELECT val FROM config WHERE key=?", (key,))
    row = cur.fetchone(); conn.close()
    return row[0] if row else default

def is_owner(uid: int) -> bool:
    return OWNER_ID != 0 and uid == OWNER_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ALU Alpha Bot — MVP\n/ping /setout /addrss /listrss /delrss /scan")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

async def setout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return await update.message.reply_text("Только владелец.")
    if not context.args: return await update.message.reply_text("Использование: /setout <chat_id>")
    set_config("out_chat", context.args[0])
    await update.message.reply_text(f"Вывод: {context.args[0]}")

async def addrss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return await update.message.reply_text("Только владелец.")
    if not context.args: return await update.message.reply_text("Использование: /addrss <url>")
    url = context.args[0].strip()
    conn = db()
    conn.execute("INSERT INTO sources(type,url,created_at) VALUES(?,?,?)",
                 ("rss", url, datetime.now(timezone.utc).isoformat()))
    conn.commit(); conn.close()
    await update.message.reply_text(f"Добавлен RSS: {url}")

async def listrss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db(); cur = conn.execute("SELECT id,url FROM sources WHERE type='rss' ORDER BY id")
    rows = cur.fetchall(); conn.close()
    if not rows: return await update.message.reply_text("Нет RSS. /addrss <url>")
    await update.message.reply_text("RSS:\n" + "\n".join([f"{r[0]}. {r[1]}" for r in rows]))

async def delrss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return await update.message.reply_text("Только владелец.")
    if not context.args: return await update.message.reply_text("Использование: /delrss <id>")
    rid = int(context.args[0]); conn = db()
    conn.execute("DELETE FROM sources WHERE id=?", (rid,))
    conn.commit(); conn.close()
    await update.message.reply_text(f"Удалён #{rid}")

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return await update.message.reply_text("Только владелец.")
    out_chat = get_config("out_chat")
    if not out_chat: return await update.message.reply_text("Сначала /setout <chat_id>")

    rules = load_rules("rules.yaml"); scorer = Scorer(rules.get("weights", {}))
    threshold = float(rules.get("threshold", 3.0)); top_n = int(rules.get("top_n", 5))

    conn = db(); cur = conn.execute("SELECT url FROM sources WHERE type='rss'")
    rss_list = [r[0] for r in cur.fetchall()]; conn.close()
    if not rss_list: return await update.message.reply_text("Добавь /addrss <url> и повтори.")

    await update.message.reply_text(f"Сканирую {len(rss_list)} RSS...")
    items = await fetch_rss_batch(rss_list, timeout=12, lookback_hours=48)
    for it in items:
        title = it.get("title",""); summary = it.get("summary","")
        it["score"], it["reasons"] = scorer.score(f"{title}\n{summary}")
    items = [it for it in items if it["score"] >= threshold]
    items.sort(key=lambda x: x["score"], reverse=True); items = items[:top_n]
    if not items:
        return await context.bot.send_message(chat_id=out_chat, text="Нет проходов порога — подкрути rules.yaml.")
    for it in items:
        msg = f"🔥 *{it['title']}*\n{it.get('link','')}\n_score: {it['score']:.2f} | reasons: {', '.join(it['reasons'])}_"
        await context.bot.send_message(chat_id=out_chat, text=msg, parse_mode=constants.ParseMode.MARKDOWN)

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("setout", setout))
    app.add_handler(CommandHandler("addrss", addrss))
    app.add_handler(CommandHandler("listrss", listrss))
    app.add_handler(CommandHandler("delrss", delrss))
    app.add_handler(CommandHandler("scan", scan))
    await app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
