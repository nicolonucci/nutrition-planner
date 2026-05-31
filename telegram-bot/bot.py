#!/usr/bin/env python3
"""
Bot Telegram per la pianificazione settimanale di Nicolò.
Flusso: lunedì → domenica, domande con inline keyboard, salva JSON.
"""

import os
import json
import logging
import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Costanti stato conversazione ──────────────────────────────────────────────
(
    TIPO_GIORNATA,
    ORARIO,
    SCENARIO_DIFFICILE,
    ALTRA_ATTIVITA,
    ORARIO_ALTRA,
    PREFERENZE,
    CONFERMA,
) = range(7)

GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]

# ── Percorso dati (Railway: usa variabile d'ambiente DATA_DIR, altrimenti locale) ─
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))

# ── Ricettario (da ricettario.html — solo le ricette disponibili) ─────────────
RICETTE = {
    "colazioni": [
        "Yogurt greco + banana + noci + miele (~370 kcal, P:22g)",
        "Toast GF avocado + salmone affumicato (~420 kcal, P:28g)",
        "Philadelphia GF + salmone + pane GF + pomodoro (~390 kcal, P:26g)",
        "Smoothie fragola + banana + yogurt greco (~360 kcal, P:20g)",
        "Uova strapazzate + pane GF + arancia (~420 kcal, P:28g)",
        "Yogurt greco + frutti di bosco + semi di chia (~320 kcal, P:20g)",
    ],
    "pre_workout": [
        "Banana + caffè (~110 kcal)",
        "Yogurt greco 150g + banana (~280 kcal, P:18g)",
        "4 datteri + 15g mandorle (~200 kcal)",
        "3 datteri + 10g noci (~165 kcal)",
    ],
    "post_workout": [
        "2 uova sode + banana (~220 kcal, P:14g)",
        "Banana + 30g frutta secca (~250 kcal, P:6g)",
    ],
    "pranzi": [
        "Pad Thai GF con gamberetti (~580 kcal, P:42g)",
        "Riso basmati con pollo & curcuma (~560 kcal, P:45g)",
        "Piadina GF con pollo, pomodori & rucola (~520 kcal, P:40g)",
        "Pasta di riso al tonno & pomodoro (~550 kcal, P:38g)",
        "Spaghetti di soia con salmone & piselli (~530 kcal, P:40g)",
        "Bowl riso venere, tonno & pomodorini (~490 kcal, P:38g)",
        "Piadina GF con salmone, pomodori & rucola (~500 kcal, P:38g)",
    ],
    "cene": [
        "Pollo alla piastra + zucchine grigliate (~380 kcal, P:48g)",
        "Salmone al forno + carote & piselli (~420 kcal, P:42g)",
        "Bistecca di manzo + insalata di pomodori (~450 kcal, P:50g)",
        "Frittata zucchine & carote al forno (~360 kcal, P:30g)",
        "Merluzzo al vapore + piselli & carote (~320 kcal, P:38g)",
        "Pollo al limone + zucchine grigliate (~370 kcal, P:46g)",
        "Salmone in padella + piselli & pomodorini (~400 kcal, P:40g)",
    ],
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_week_id(date: datetime.date) -> str:
    return f"{date.year}-W{date.isocalendar()[1]:02d}"

def monday_of_week(date: datetime.date) -> datetime.date:
    return date - datetime.timedelta(days=date.weekday())

def init_session(context: ContextTypes.DEFAULT_TYPE):
    """Inizializza la sessione di pianificazione."""
    today = datetime.date.today()
    monday = monday_of_week(today)
    week_id = get_week_id(today)
    context.user_data.update({
        "week_id": week_id,
        "monday": monday,
        "current_day": 0,       # 0 = lunedì, 6 = domenica
        "giorni": [],           # lista di dict per ogni giorno
        "current_giorno": {},   # giorno in compilazione
    })

def kb(buttons: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """Crea InlineKeyboardMarkup da lista di righe [(label, callback_data)]."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=data) for label, data in row]
        for row in buttons
    ])

def giorno_corrente(context) -> str:
    idx = context.user_data["current_day"]
    monday = context.user_data["monday"]
    data = monday + datetime.timedelta(days=idx)
    return f"{GIORNI[idx]} {data.strftime('%d/%m')}"

# ── Assegna pasti automaticamente in base al tipo di giornata ────────────────

def assegna_pasti(tipo: str, orario: str, note: str = "") -> dict:
    import random

    def pick(categoria):
        return random.choice(RICETTE[categoria])

    pasti = {
        "colazione": pick("colazioni"),
        "pranzo": pick("pranzi"),
        "cena": pick("cene"),
    }

    if tipo in ("Palestra", "Nuoto"):
        pasti["pre_workout"] = pick("pre_workout")
        pasti["post_workout"] = pick("post_workout")

    return pasti

# ── Comando /start e /pianifica ───────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Ciao Nicolò! Usa /pianifica per pianificare la settimana."
    )

async def pianifica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_session(context)
    return await chiedi_tipo_giornata(update, context)

async def chiedi_tipo_giornata(update: Update, context: ContextTypes.DEFAULT_TYPE):
    giorno = giorno_corrente(context)
    testo = f"📅 *{giorno}* — Che tipo di giornata sarà?"
    tastiera = kb([
        [("🏋️ Palestra", "tipo_palestra"), ("🏊 Nuoto", "tipo_nuoto")],
        [("😴 Riposo", "tipo_riposo")],
        [("⚠️ Difficile da rispettare", "tipo_difficile")],
        [("🏃 Altra attività", "tipo_altra")],
    ])
    if update.callback_query:
        await update.callback_query.edit_message_text(testo, reply_markup=tastiera, parse_mode="Markdown")
    else:
        await update.message.reply_text(testo, reply_markup=tastiera, parse_mode="Markdown")
    return TIPO_GIORNATA

# ── Handler tipo giornata ─────────────────────────────────────────────────────

async def handle_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tipo_map = {
        "tipo_palestra": "Palestra",
        "tipo_nuoto": "Nuoto",
        "tipo_riposo": "Riposo",
        "tipo_difficile": "Difficile",
        "tipo_altra": "Altra attività",
    }
    tipo = tipo_map[query.data]
    context.user_data["current_giorno"]["tipo"] = tipo

    if tipo in ("Palestra", "Nuoto"):
        return await chiedi_orario(update, context)
    elif tipo == "Riposo":
        return await salva_giorno(update, context, orario="", note="")
    elif tipo == "Difficile":
        return await chiedi_scenario_difficile(update, context)
    else:
        await query.edit_message_text(
            f"🏃 *{giorno_corrente(context)}* — Che attività hai in programma?\n\n"
            "Rispondi in chat (es: corsa, calcetto, yoga...)",
            parse_mode="Markdown"
        )
        return ALTRA_ATTIVITA

# ── Handler orario ────────────────────────────────────────────────────────────

async def chiedi_orario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    giorno = giorno_corrente(context)
    testo = f"📅 *{giorno}* — A che ora ti alleni?"
    tastiera = kb([
        [("☀️ Mattina (9:00–12:00)", "orario_mattina")],
        [("🌆 Pomeriggio (16:00–19:00)", "orario_pomeriggio")],
    ])
    await update.callback_query.edit_message_text(testo, reply_markup=tastiera, parse_mode="Markdown")
    return ORARIO

async def handle_orario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    orario = "Mattina" if query.data == "orario_mattina" else "Pomeriggio"
    return await salva_giorno(update, context, orario=orario)

# ── Handler scenario difficile ────────────────────────────────────────────────

async def chiedi_scenario_difficile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    giorno = giorno_corrente(context)
    testo = f"⚠️ *{giorno}* — Cosa rende difficile questa giornata?"
    tastiera = kb([
        [("🍽️ Cena fuori", "sc_cena"), ("✈️ Viaggio", "sc_viaggio")],
        [("🎉 Evento sociale", "sc_evento"), ("💼 Poco tempo", "sc_tempo")],
    ])
    await update.callback_query.edit_message_text(testo, reply_markup=tastiera, parse_mode="Markdown")
    return SCENARIO_DIFFICILE

CONSIGLI_DIFFICILE = {
    "sc_cena": "🍽️ *Cena fuori:* punta a proteina magra + verdure. Colazione e pranzo normali.",
    "sc_viaggio": "✈️ *Viaggio:* porta snack proteici (uova sode, frutta secca). Pasti semplici fuori.",
    "sc_evento": "🎉 *Evento:* colazione e pranzo leggeri, goditi la cena senza esagerare con l'alcol.",
    "sc_tempo": "💼 *Poco tempo:* uova, frutta secca, piadina veloce. Rimanda l'allenamento se serve.",
}

async def handle_scenario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    consiglio = CONSIGLI_DIFFICILE.get(query.data, "")
    context.user_data["current_giorno"]["note"] = query.data.replace("sc_", "")
    return await salva_giorno(update, context, orario="", note=consiglio)

# ── Handler altra attività ────────────────────────────────────────────────────

async def handle_altra_attivita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    attivita = update.message.text
    context.user_data["current_giorno"]["note"] = attivita
    testo = f"🏃 *{giorno_corrente(context)} — {attivita}*\nA che ora?"
    tastiera = kb([
        [("☀️ Mattina", "orario_altra_mattina"), ("🌆 Pomeriggio / Sera", "orario_altra_pomeriggio")],
    ])
    await update.message.reply_text(testo, reply_markup=tastiera, parse_mode="Markdown")
    return ORARIO_ALTRA

async def handle_orario_altra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    orario = "Mattina" if "mattina" in query.data else "Pomeriggio"
    return await salva_giorno(update, context, orario=orario)

# ── Salva giorno e avanza ─────────────────────────────────────────────────────

async def salva_giorno(update: Update, context: ContextTypes.DEFAULT_TYPE, orario: str, note: str = ""):
    cg = context.user_data["current_giorno"]
    tipo = cg.get("tipo", "Riposo")
    idx = context.user_data["current_day"]
    monday = context.user_data["monday"]
    data = monday + datetime.timedelta(days=idx)

    pasti = assegna_pasti(tipo, orario)

    giorno_dict = {
        "giorno": GIORNI[idx],
        "data": data.isoformat(),
        "allenamento": {"tipo": tipo, "orario": orario, "note": cg.get("note", note)},
        "pasti": pasti,
    }
    context.user_data["giorni"].append(giorno_dict)
    context.user_data["current_giorno"] = {}
    context.user_data["current_day"] += 1

    # Conferma giorno
    emoji_tipo = {"Palestra": "🏋️", "Nuoto": "🏊", "Riposo": "😴", "Difficile": "⚠️"}.get(tipo, "🏃")
    msg = f"✅ *{GIORNI[idx]} {data.strftime('%d/%m')}* — {emoji_tipo} {tipo}"
    if orario:
        msg += f" ({orario})"
    if note:
        msg += f"\n_{note}_"

    if context.user_data["current_day"] < 7:
        # Prossimo giorno
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode="Markdown")
        else:
            await update.effective_message.reply_text(msg, parse_mode="Markdown")
        # Simula update per il prossimo giorno
        return await chiedi_tipo_giornata_msg(update, context)
    else:
        # Tutti i 7 giorni completati → preferenze
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode="Markdown")
        else:
            await update.effective_message.reply_text(msg, parse_mode="Markdown")
        return await chiedi_preferenze(update, context)

async def chiedi_tipo_giornata_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    giorno = giorno_corrente(context)
    testo = f"📅 *{giorno}* — Che tipo di giornata sarà?"
    tastiera = kb([
        [("🏋️ Palestra", "tipo_palestra"), ("🏊 Nuoto", "tipo_nuoto")],
        [("😴 Riposo", "tipo_riposo")],
        [("⚠️ Difficile da rispettare", "tipo_difficile")],
        [("🏃 Altra attività", "tipo_altra")],
    ])
    await update.effective_message.reply_text(testo, reply_markup=tastiera, parse_mode="Markdown")
    return TIPO_GIORNATA

# ── Preferenze finali ─────────────────────────────────────────────────────────

async def chiedi_preferenze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testo = "🎯 Vuoi qualcosa di particolare questa settimana?"
    tastiera = kb([
        [("✅ Nessuna preferenza, vai tu", "pref_nessuna")],
        [("🚫 Alimenti da evitare", "pref_evitare")],
        [("🎯 Obiettivo calorico diverso", "pref_calorico")],
    ])
    await update.effective_message.reply_text(testo, reply_markup=tastiera, parse_mode="Markdown")
    return PREFERENZE

async def handle_preferenze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await mostra_riepilogo(update, context)

# ── Riepilogo e conferma ──────────────────────────────────────────────────────

async def mostra_riepilogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    giorni = context.user_data["giorni"]
    week_id = context.user_data["week_id"]
    righe = [f"📋 *Riepilogo settimana {week_id}*\n"]
    emoji_tipo = {"Palestra": "🏋️", "Nuoto": "🏊", "Riposo": "😴", "Difficile": "⚠️"}
    for g in giorni:
        e = emoji_tipo.get(g["allenamento"]["tipo"], "🏃")
        orario = f" ({g['allenamento']['orario']})" if g["allenamento"]["orario"] else ""
        righe.append(f"{e} *{g['giorno']}*{orario}: {g['allenamento']['tipo']}")
    testo = "\n".join(righe)
    tastiera = kb([
        [("✅ Confermo", "conf_si"), ("✏️ Modifica", "conf_modifica")],
        [("❌ Ricomincia", "conf_no")],
    ])
    await update.effective_message.reply_text(testo, reply_markup=tastiera, parse_mode="Markdown")
    return CONFERMA

async def handle_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "conf_no":
        await query.edit_message_text("❌ Pianificazione annullata. Usa /pianifica per ricominciare.")
        return ConversationHandler.END

    if query.data == "conf_modifica":
        await query.edit_message_text(
            "✏️ Modifica non ancora disponibile. Usa /pianifica per ricominciare dall'inizio."
        )
        return ConversationHandler.END

    # Salva JSON
    week_id = context.user_data["week_id"]
    menu_data = {
        "settimana": week_id,
        "giorni": context.user_data["giorni"],
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    menus_dir = DATA_DIR / "menus"
    menus_dir.mkdir(exist_ok=True)

    menu_path = menus_dir / f"{week_id}.json"
    with open(menu_path, "w", encoding="utf-8") as f:
        json.dump(menu_data, f, ensure_ascii=False, indent=2)

    # Aggiorna settimane.json
    settimane_path = DATA_DIR / "settimane.json"
    settimane = []
    if settimane_path.exists():
        with open(settimane_path, encoding="utf-8") as f:
            settimane = json.load(f)

    monday = context.user_data["monday"]
    sunday = monday + datetime.timedelta(days=6)
    entry = {
        "id": week_id,
        "confermato": True,
        "dal": monday.isoformat(),
        "al": sunday.isoformat(),
    }
    settimane = [s for s in settimane if s["id"] != week_id]
    settimane.append(entry)
    with open(settimane_path, "w", encoding="utf-8") as f:
        json.dump(settimane, f, ensure_ascii=False, indent=2)

    await query.edit_message_text(
        f"✅ *Menù {week_id} salvato!*\n\nBuona settimana 💪",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ── Annulla ───────────────────────────────────────────────────────────────────

async def annulla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Pianificazione annullata.")
    return ConversationHandler.END

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("pianifica", pianifica)],
        states={
            TIPO_GIORNATA: [CallbackQueryHandler(handle_tipo, pattern="^tipo_")],
            ORARIO: [CallbackQueryHandler(handle_orario, pattern="^orario_(?!altra)")],
            SCENARIO_DIFFICILE: [CallbackQueryHandler(handle_scenario, pattern="^sc_")],
            ALTRA_ATTIVITA: [
                # risposta testuale con l'attività
                __import__("telegram.ext", fromlist=["MessageHandler"]).MessageHandler(
                    __import__("telegram.ext", fromlist=["filters"]).filters.TEXT & ~__import__("telegram.ext", fromlist=["filters"]).filters.COMMAND,
                    handle_altra_attivita
                )
            ],
            ORARIO_ALTRA: [CallbackQueryHandler(handle_orario_altra, pattern="^orario_altra_")],
            PREFERENZE: [CallbackQueryHandler(handle_preferenze, pattern="^pref_")],
            CONFERMA: [CallbackQueryHandler(handle_conferma, pattern="^conf_")],
        },
        fallbacks=[CommandHandler("annulla", annulla)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    logger.info("Bot avviato in polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
