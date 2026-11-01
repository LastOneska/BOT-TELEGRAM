import asyncio
import logging
from datetime import datetime, time, timedelta
from math import isfinite

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from config import ALERT_SCHEDULE, CATEGORIES, CITY, PICKUP_FEE, PRICE_PER_KM
from database import Database
from prediction import (
    format_category_schedule,
    is_peak_time,
    next_peak_label,
    score_hotspot,
)
from pricing import format_rupiah, suggest_price
from services.hotspots import HotspotService, HotspotServiceError
from services.weather import WeatherUnavailable, get_current_weather

logger = logging.getLogger(__name__)


def _database(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["database"]


def _ensure_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user is None:
        raise RuntimeError("Telegram update does not contain a user.")
    user = update.effective_user
    _database(context).ensure_user(user.id, user.username)
    return user.id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ensure_user(update, context)
    await update.effective_message.reply_text(
        "Halo! Saya asisten informasi untuk driver ojol di Bandung.\n\n"
        "• /ramai — prediksi 5 area yang berpotensi ramai\n"
        "• /jam — jadwal puncak berdasarkan jenis lokasi\n"
        "• /alert on atau /alert off — atur pengingat\n"
        "• /tawar <km> — hitung rentang saran tarif\n"
        "• /catat <km> <harga> — simpan order yang selesai\n"
        "• /rekap — lihat pendapatan hari ini\n"
        "• /help — panduan singkat\n\n"
        "Prediksi bersifat perkiraan, bukan data order real-time. "
        "Bot tidak mengakses aplikasi ojol; penerimaan order dan penawaran "
        "tetap dilakukan manual oleh Anda."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ensure_user(update, context)
    await update.effective_message.reply_text(
        "Contoh penggunaan:\n"
        "• /tawar 4.5\n"
        "• /catat 4.5 20000\n"
        "• /alert on\n"
        "• /rekap\n\n"
        "Gunakan titik untuk desimal jarak dan masukkan harga sebagai angka "
        "rupiah tanpa pemisah. Tarif dasar dapat disesuaikan di config.py."
    )


async def ramai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ensure_user(update, context)
    try:
        result = await asyncio.to_thread(
            context.application.bot_data["hotspot_service"].get_areas
        )
    except HotspotServiceError as error:
        await update.effective_message.reply_text(str(error))
        return

    weather_notice = ""
    try:
        weather = await asyncio.to_thread(get_current_weather)
        is_raining = weather.is_raining
    except WeatherUnavailable:
        is_raining = False
        weather_notice = "\nCuaca tidak tersedia; faktor cuaca tidak dihitung."

    now = datetime.now(CITY.timezone)
    ranked = sorted(
        result.areas,
        key=lambda area: score_hotspot(area, now, is_raining),
        reverse=True,
    )[:5]
    lines = [
        f"Prediksi area berpotensi ramai — {CITY.name}",
        f"Pembaruan: {now:%d-%m %H:%M} WIB",
        "",
    ]
    for index, area in enumerate(ranked, start=1):
        category = CATEGORIES[area["category"]]
        peak = next_peak_label(area["category"], now)
        lines.append(f"{index}. {area['name']} ({category.label}) — {peak}")
    lines.extend(
        ["", "Ini prediksi berdasarkan lokasi dan pola jam, bukan order real-time."]
    )
    if result.is_stale:
        lines.append("Data lokasi memakai cache lama karena OpenStreetMap belum merespons.")
    if weather_notice:
        lines.append(weather_notice.strip())

    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("👍 Akurat", callback_data="feedback:up"),
            InlineKeyboardButton("👎 Kurang akurat", callback_data="feedback:down"),
        ]]
    )
    await update.effective_message.reply_text(
        "\n".join(lines),
        reply_markup=keyboard,
    )


async def jam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ensure_user(update, context)
    await update.effective_message.reply_text(
        f"Perkiraan jam puncak di {CITY.name}:\n\n"
        f"{format_category_schedule()}\n\n"
        "Jadwal adalah pola umum dan dapat berbeda menurut hari atau kondisi lokal."
    )


async def alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _ensure_user(update, context)
    if len(context.args) != 1 or context.args[0].lower() not in {"on", "off"}:
        await update.effective_message.reply_text(
            "Gunakan /alert on untuk mengaktifkan atau /alert off untuk mematikan."
        )
        return

    enabled = context.args[0].lower() == "on"
    _database(context).set_alerts(user_id, enabled)
    if enabled:
        await update.effective_message.reply_text(
            "Alert aktif. Saya akan mengirim pengingat sekitar 30 menit sebelum "
            "perkiraan jam puncak di Bandung."
        )
    else:
        await update.effective_message.reply_text("Alert sudah dimatikan.")


async def tawar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _ensure_user(update, context)
    if len(context.args) != 1:
        await update.effective_message.reply_text("Format: /tawar <jarak_km>, contoh /tawar 4.5")
        return

    try:
        distance_km = float(context.args[0].replace(",", "."))
        if not isfinite(distance_km) or not 0 < distance_km <= 300:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text(
            "Jarak harus berupa angka lebih dari 0 dan maksimal 300 km."
        )
        return

    weather_notice = ""
    try:
        weather = await asyncio.to_thread(get_current_weather)
        is_raining = weather.is_raining
    except WeatherUnavailable:
        is_raining = False
        weather_notice = "\nData cuaca tidak tersedia; pengali hujan tidak digunakan."

    now = datetime.now(CITY.timezone)
    suggestion = suggest_price(
        distance_km,
        is_peak=is_peak_time(now),
        is_raining=is_raining,
    )
    conditions = []
    if suggestion.is_peak:
        conditions.append("jam puncak")
    if suggestion.is_raining:
        conditions.append("hujan")
    condition_text = ", ".join(conditions) if conditions else "kondisi normal"
    await update.effective_message.reply_text(
        f"Perkiraan saran untuk {distance_km:g} km: "
        f"{format_rupiah(suggestion.low)}–{format_rupiah(suggestion.high)}\n"
        f"Kondisi: {condition_text}.\n"
        f"Perhitungan memakai tarif dasar {format_rupiah(PRICE_PER_KM)}/km dan "
        f"biaya jemput {format_rupiah(PICKUP_FEE)}. Sesuaikan dengan biaya "
        "dan situasi "
        f"order Anda; keputusan penawaran tetap manual."
        f"{weather_notice}"
    )


async def catat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _ensure_user(update, context)
    if len(context.args) != 2:
        await update.effective_message.reply_text(
            "Format: /catat <jarak_km> <harga_rupiah>, contoh /catat 4.5 20000"
        )
        return
    try:
        distance_km = float(context.args[0].replace(",", "."))
        price = int(context.args[1])
        if not isfinite(distance_km) or not 0 < distance_km <= 300:
            raise ValueError
        if not 1_000 <= price <= 10_000_000:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text(
            "Jarak harus 0–300 km dan harga harus Rp1.000–Rp10.000.000."
        )
        return

    _database(context).add_order(user_id, distance_km, price)
    await update.effective_message.reply_text(
        f"Order tersimpan: {distance_km:g} km, {format_rupiah(price)}."
    )


async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _ensure_user(update, context)
    now = datetime.now(CITY.timezone)
    start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    orders = _database(context).get_orders(user_id, start_local, end_local)
    if not orders:
        await update.effective_message.reply_text(
            "Belum ada order tercatat hari ini. Gunakan /catat setelah order selesai."
        )
        return

    total_income = sum(int(order["price"]) for order in orders)
    total_distance = sum(float(order["distance_km"]) for order in orders)
    by_hour: dict[int, int] = {}
    for order in orders:
        created_at = datetime.fromisoformat(order["created_at"]).astimezone(CITY.timezone)
        by_hour[created_at.hour] = by_hour.get(created_at.hour, 0) + int(order["price"])
    best_hour, best_income = max(by_hour.items(), key=lambda item: item[1])
    await update.effective_message.reply_text(
        f"Rekap hari ini ({now:%d-%m-%Y} WIB)\n"
        f"• Order: {len(orders)}\n"
        f"• Pendapatan: {format_rupiah(total_income)}\n"
        f"• Jarak tercatat: {total_distance:g} km\n"
        f"• Jam terbaik: {best_hour:02d}.00–{(best_hour + 1) % 24:02d}.00 "
        f"({format_rupiah(best_income)})"
    )


async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.from_user is None or query.message is None:
        return
    vote = query.data.partition(":")[2]
    if vote not in {"up", "down"}:
        await query.answer("Umpan balik tidak dikenali.", show_alert=True)
        return

    database: Database = context.application.bot_data["database"]
    database.ensure_user(query.from_user.id, query.from_user.username)
    saved = database.save_feedback(
        query.from_user.id,
        query.message.message_id,
        vote,
    )
    await query.answer(
        "Terima kasih atas masukannya." if saved else "Umpan balik ini sudah tercatat."
    )


async def send_peak_alert(context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.job is None or context.job.data is None:
        return
    category_keys = context.job.data
    category_names = ", ".join(CATEGORIES[key].label.lower() for key in category_keys)
    database: Database = context.application.bot_data["database"]
    for user_id in database.get_alert_users():
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"Pengingat: sekitar 30 menit lagi diperkirakan memasuki "
                    f"jam puncak untuk {category_names} di {CITY.name}. "
                    "Cek kondisi sekitar dan aplikasi Anda secara langsung."
                ),
            )
        except TelegramError:
            logger.exception("Gagal mengirim alert kepada pengguna %s", user_id)


async def post_init(application: Application) -> None:
    job_queue = application.job_queue
    if job_queue is None:
        raise RuntimeError(
            "JobQueue tidak tersedia. Instal dependensi python-telegram-bot[job-queue]."
        )
    for hour, minute, category_keys in ALERT_SCHEDULE:
        job_queue.run_daily(
            send_peak_alert,
            time=time(hour, minute, tzinfo=CITY.timezone),
            name=f"peak-alert-{hour:02d}-{minute:02d}",
            data=category_keys,
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(
        "Terjadi error saat memproses update",
        exc_info=context.error,
    )


def create_application(token: str, database: Database) -> Application:
    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )
    application.bot_data["database"] = database
    application.bot_data["hotspot_service"] = HotspotService(database)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ramai", ramai))
    application.add_handler(CommandHandler("jam", jam))
    application.add_handler(CommandHandler("alert", alert))
    application.add_handler(CommandHandler("tawar", tawar))
    application.add_handler(CommandHandler("catat", catat))
    application.add_handler(CommandHandler("rekap", rekap))
    application.add_handler(CallbackQueryHandler(feedback, pattern=r"^feedback:"))
    application.add_error_handler(error_handler)
    return application
