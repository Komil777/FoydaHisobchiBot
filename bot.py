import os
import sqlite3
import csv
import io
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DB_PATH = os.getenv("BOT_DB_PATH", "foydabot.db")

MENU = [
    ["💰 Баланс", "📊 Ҳисобот"],
    ["➕ Даромад", "➖ Харажат"],
    ["📤 CSV экспорт", "🧾 Қўлланма"]
]

def connect():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
        amount REAL NOT NULL CHECK(amount > 0),
        category TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )""")
    con.commit()
    return con

def fmt(n):
    return f"{n:,.0f}".replace(",", " ")

def add_tx(user_id, kind, amount, category, note):
    con = connect()
    con.execute(
        "INSERT INTO transactions(user_id,kind,amount,category,note,created_at) VALUES(?,?,?,?,?,?)",
        (user_id, kind, amount, category, note, datetime.now().isoformat(timespec="seconds"))
    )
    con.commit()
    con.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Ассалому алайкум! Мен — ФойдаБот 📈\n\n"
        "Даромад ва харажатларни тартибга солиш, пул оқимини тушуниш ва тежашга ёрдам бераман.\n"
        "Бу версияда тўлов қабул қилиш йўқ — аввал фойдалилигини текширамиз.",
        reply_markup=ReplyKeyboardMarkup(MENU, resize_keyboard=True)
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Қандай фойдаланилади:\n"
        "/income 150000 Маош\n"
        "/expense 25000 Озиқ-овқат\n"
        "/balance — умумий қолдиқ\n"
        "/report — сўнгги операциялар\n"
        "/export — CSV файлни юклаб олиш\n\n"
        "Ёки менюдан ➕ Даромад / ➖ Харажатни танланг.\n"
        "Сумма сўмда киритилади. Масалан: /expense 35000 Такси"
    )

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str):
    if not context.args:
        example = "/income 150000 Маош" if kind == "income" else "/expense 25000 Озиқ-овқат"
        await update.message.reply_text(f"Формат: {example}")
        return
    try:
        amount = float(context.args[0].replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Сумма мусбат сон бўлиши керак. Масалан: /income 150000 Маош")
        return
    note = " ".join(context.args[1:]).strip()
    category = note.split(" ")[0] if note else ("Даромад" if kind == "income" else "Бошқа")
    add_tx(update.effective_user.id, kind, amount, category, note or category)
    label = "Даромад" if kind == "income" else "Харажат"
    await update.message.reply_text(f"✅ {label} сақланди: {fmt(amount)} сўм\nИзоҳ: {note or category}")

async def income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_command(update, context, "income")

async def expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_command(update, context, "expense")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    rows = con.execute("SELECT kind, COALESCE(SUM(amount),0) FROM transactions WHERE user_id=? GROUP BY kind",
                       (update.effective_user.id,)).fetchall()
    con.close()
    totals = dict(rows)
    inc, exp = totals.get("income", 0), totals.get("expense", 0)
    await update.message.reply_text(
        f"💰 Пул оқими\n\nКирим: {fmt(inc)} сўм\nЧиқим: {fmt(exp)} сўм\n"
        f"Қолдиқ: {fmt(inc-exp)} сўм"
    )

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    rows = con.execute(
        "SELECT kind,amount,category,note,created_at FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 10",
        (update.effective_user.id,)).fetchall()
    con.close()
    if not rows:
        await update.message.reply_text("Ҳали операция йўқ. /income ёки /expense билан бошланг.")
        return
    lines = ["📊 Сўнгги 10 та операция:"]
    for kind, amount, category, note, created in rows:
        sign = "+" if kind == "income" else "−"
        lines.append(f"{sign} {fmt(amount)} сўм | {category} | {note} | {created[:16].replace('T',' ')}")
    await update.message.reply_text("\n".join(lines))

async def export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    rows = con.execute(
        "SELECT created_at,kind,amount,category,note FROM transactions WHERE user_id=? ORDER BY id",
        (update.effective_user.id,)).fetchall()
    con.close()
    if not rows:
        await update.message.reply_text("Экспорт учун маълумот йўқ.")
        return
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Сана", "Тури", "Сумма", "Категория", "Изоҳ"])
    for row in rows:
        writer.writerow(row)
    data = io.BytesIO(out.getvalue().encode("utf-8-sig"))
    data.name = "foydabot_hisobot.csv"
    await update.message.reply_document(document=data, caption="📤 Кирим-чиқим ҳисоботингиз")

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text == "💰 Баланс":
        await balance(update, context)
    elif text == "📊 Ҳисобот":
        await report(update, context)
    elif text == "➕ Даромад":
        await update.message.reply_text("Даромад қўшиш: /income 150000 Маош")
    elif text == "➖ Харажат":
        await update.message.reply_text("Харажат қўшиш: /expense 25000 Озиқ-овқат")
    elif text == "📤 CSV экспорт":
        await export_csv(update, context)
    elif text == "🧾 Қўлланма":
        await help_cmd(update, context)
    else:
        await update.message.reply_text("Менюдан танланг ёки /help буйруғини юборинг.")

def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ўрнатилмаган. README.md ни ўқинг.")
    connect().close()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("income", income))
    app.add_handler(CommandHandler("expense", expense))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("export", export_csv))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    print("ФойдаБот ишлаяпти...")
    app.run_polling()

if __name__ == "__main__":
    main()
