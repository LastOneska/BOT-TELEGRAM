import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from math import isfinite

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from config import (
    ALERT_SCHEDULE,
    CATEGORIES,
    CITY,
    PICKUP_FEE,
    PRICE_PER_KM,
    RP_PER_KM_MAX,
    RP_PER_KM_MIN,
)
from database import Database, DuplicateOrderError
from prediction import (
    format_category_schedule,
    is_peak_time,
    next_peak_label,
    score_hotspot,
)
from pricing import (
    assess_offer,
    format_price_table,
    format_rupiah,
    suggest_price,
    validate_price_rates,
)
from services.hotspots import HotspotService, HotspotServiceError
from services.weather import WeatherUnavailable, get_current_weather

logger = logging.getLogger(__name__)


def _database(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["database"]


def _hotspot_directions_url(latitude: float, longitude: float) -> str:
    if (
        not isfinite(latitude)
        or not isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        raise ValueError("Koordinat lokasi tidak valid.")
    return f"https://maps.apple.com/?daddr={latitude:.6f},{longitude:.6f}&dirflg=d"


def _hotspot_keyboard(areas: list[dict[str, object]]) -> InlineKeyboardMarkup:
    rows = []
    for index, area in enumerate(areas, start=1):
        try:
            latitude = float(area["latitude"])
            longitude = float(area["longitude"])
            url = _hotspot_directions_url(latitude, longitude)
        except (KeyError, TypeError, ValueError):
            logger.warning("Melewati tautan rute untuk titik ramai ke-%s: koordinat tidak valid", index)
            continue
        name = str(area.get("name", "Titik ramai")).strip() or "Titik ramai"
        rows.append(
            [
                InlineKeyboardButton(
                    f"🧭 Rute {index}: {name[:40]}",
                    url=url,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("👍 Akurat", callback_data="feedback:up"),
            InlineKeyboardButton("👎 Kurang akurat", callback_data="feedback:down"),
        ]
    )
    return InlineKeyboardMarkup(rows)


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
        "  (tautan rute memakai lokasi asli perangkat)\n"
        "• /jam — jadwal puncak berdasarkan jenis lokasi\n"
        "• /alert on atau /alert off — atur pengingat\n"
        "• /tawar <km> — hitung rentang saran tarif\n"
        "• /harga — lihat tabel saran harga total jemput + antar\n"
        "• /cekorder <km_total> <tawaran> — bandingkan tawaran dengan patokan\n"
        "• /catat <km> <harga> <waktu_diterima> [id_order]\n"
        "  — simpan order yang selesai\n"
        "• /rekap — lihat pendapatan hari ini\n"
        "• /setkm <min> <maks> atau /resetharga — atur patokan harga\n"
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
        "• /harga\n"
        "• /cekorder 6.5 15000\n"
        "• /catat 4.5 20000 14:13\n"
        "• /catat 4.5 20000 2026-11-02T14:13 ORDER-123\n"
        "• /setkm 1950 2500\n"
        "• /alert on\n"
        "• /rekap\n\n"
        "Gunakan titik untuk desimal jarak, masukkan harga sebagai angka "
        "rupiah tanpa pemisah, dan waktu diterima dalam WIB (HH:MM untuk hari "
        "ini atau YYYY-MM-DDTHH:MM). Jarak untuk /harga adalah total jemput "
        "+ antar."
    )


async def cekorder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _ensure_user(update, context)
    if len(context.args) != 2:
        await update.effective_message.reply_text(
            "Format: /cekorder <total_jarak_km> <tawaran_rupiah>, "
            "contoh /cekorder 6.5 15000. Total jarak mencakup jemput + antar."
        )
        return
    try:
        distance_km = float(context.args[0].replace(",", "."))
        offered_price = int(context.args[1])
        if not isfinite(distance_km) or not 0 < distance_km <= 300:
            raise ValueError
        if not 1_000 <= offered_price <= 10_000_000:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text(
            "Jarak total harus lebih dari 0 dan maksimal 300 km; tawaran harus "
            "Rp1.000–Rp10.000.000. Gunakan angka rupiah tanpa pemisah."
        )
        return

    min_per_km, max_per_km = _database(context).get_price_range(
        user_id,
        RP_PER_KM_MIN,
        RP_PER_KM_MAX,
    )
    assessment = assess_offer(
        distance_km,
        offered_price,
        min_per_km,
        max_per_km,
    )
    await update.effective_message.reply_text(
        f"Evaluasi tawaran (total {distance_km:g} km)\n"
        f"• Tawaran: {format_rupiah(offered_price)} "
        f"({format_rupiah(round(assessment.price_per_km))}/km)\n"
        f"• Acuan harga (dibulatkan): {format_rupiah(assessment.minimum_price)}–"
        f"{format_rupiah(assessment.maximum_price)}\n"
        f"• Status per km: {assessment.status}\n\n"
        "Ini hanya pembanding berdasarkan patokan Anda, bukan keputusan "
        "otomatis. Periksa biaya dan kondisi order; keputusan tetap Anda "
        "lakukan manual di inDrive."
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

    keyboard = _hotspot_keyboard(ranked)
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
    if len(context.args) not in {3, 4}:
        await update.effective_message.reply_text(
            "Format: /catat <jarak_km> <harga_rupiah> <waktu_diterima> "
            "[id_order]. Contoh: /catat 4.5 20000 14:13 ORDER-123"
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

    try:
        accepted_at = _parse_accepted_at(
            context.args[2],
            datetime.now(CITY.timezone),
        )
    except ValueError as error:
        await update.effective_message.reply_text(str(error))
        return

    order_id = context.args[3].strip() if len(context.args) == 4 else None
    if order_id is not None and (not order_id.strip() or len(order_id) > 100):
        await update.effective_message.reply_text(
            "ID order harus berisi 1–100 karakter tanpa spasi kosong."
        )
        return
    try:
        _database(context).add_order(
            user_id,
            distance_km,
            price,
            accepted_at=accepted_at,
            order_id=order_id,
        )
    except DuplicateOrderError:
        await update.effective_message.reply_text(
            "ID order tersebut sudah tercatat; data tidak ditambahkan lagi."
        )
        return
    await update.effective_message.reply_text(
        f"Order tersimpan: {distance_km:g} km, {format_rupiah(price)}."
    )


def _parse_accepted_at(value: str, now_local: datetime) -> datetime:
    try:
        accepted_at = datetime.strptime(value, "%H:%M").replace(
            year=now_local.year,
            month=now_local.month,
            day=now_local.day,
            tzinfo=CITY.timezone,
        )
    except ValueError:
        try:
            accepted_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(
                "Waktu diterima harus HH:MM (hari ini) atau "
                "YYYY-MM-DDTHH:MM, dalam WIB."
            ) from error
        if accepted_at.tzinfo is None:
            accepted_at = accepted_at.replace(tzinfo=CITY.timezone)
        else:
            accepted_at = accepted_at.astimezone(CITY.timezone)

    if accepted_at > now_local:
        raise ValueError("Waktu diterima tidak boleh berada di masa depan.")
    return accepted_at


async def harga(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _ensure_user(update, context)
    min_per_km, max_per_km = _database(context).get_price_range(
        user_id,
        RP_PER_KM_MIN,
        RP_PER_KM_MAX,
    )
    sent_message = await update.effective_message.reply_text(
        format_price_table(min_per_km, max_per_km)
    )
    try:
        await context.bot.pin_chat_message(
            chat_id=update.effective_chat.id,
            message_id=sent_message.message_id,
            disable_notification=True,
        )
    except TelegramError:
        logger.exception("Gagal menyematkan tabel harga untuk pengguna %s", user_id)
        await update.effective_message.reply_text(
            "Tabel harga sudah dikirim, tetapi Telegram tidak mengizinkan bot "
            "menyematkannya di chat ini."
        )


async def setkm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _ensure_user(update, context)
    if len(context.args) != 2:
        await update.effective_message.reply_text(
            "Format: /setkm <minimal_rupiah_per_km> <maksimal_rupiah_per_km>, "
            "contoh /setkm 1950 2500."
        )
        return
    try:
        min_per_km, max_per_km = map(int, context.args)
        validate_price_rates(min_per_km, max_per_km)
    except ValueError:
        await update.effective_message.reply_text(
            "Format harus berupa dua bilangan bulat positif dan nilai minimal "
            "tidak boleh melebihi maksimal. Contoh: /setkm 1950 2500."
        )
        return

    _database(context).set_price_range(user_id, min_per_km, max_per_km)
    await update.effective_message.reply_text(
        "Patokan harga diperbarui: "
        f"{format_rupiah(min_per_km)}–{format_rupiah(max_per_km)}/km. "
        "Gunakan /harga untuk melihat tabel."
    )


async def resetharga(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _ensure_user(update, context)
    _database(context).reset_price_range(user_id)
    await update.effective_message.reply_text(
        "Patokan harga dikembalikan ke default "
        f"{format_rupiah(RP_PER_KM_MIN)}–"
        f"{format_rupiah(RP_PER_KM_MAX)}/km."
    )


async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = _ensure_user(update, context)
    now = datetime.now(CITY.timezone)
    start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    orders = _database(context).get_orders(user_id, start_local, end_local)
    min_per_km, max_per_km = _database(context).get_price_range(
        user_id,
        RP_PER_KM_MIN,
        RP_PER_KM_MAX,
    )
    await update.effective_message.reply_text(
        _build_recap_message(orders, now, min_per_km, max_per_km)
    )


def _stored_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(CITY.timezone)


def _build_recap_message(
    orders: list[dict[str, object]],
    now: datetime,
    min_per_km: int,
    max_per_km: int,
) -> str:
    total_income = sum(int(order["price"]) for order in orders)
    total_distance = sum(float(order["distance_km"]) for order in orders)
    by_hour: dict[int, tuple[int, int]] = {}
    for order in orders:
        completed_at = _stored_datetime(str(order["completed_at"]))
        income, count = by_hour.get(completed_at.hour, (0, 0))
        by_hour[completed_at.hour] = income + int(order["price"]), count + 1

    if by_hour:
        best_hour, (best_income, _) = max(
            by_hour.items(),
            key=lambda item: (item[1][0], item[1][1], -item[0]),
        )
        best_hour_text = (
            f"{best_hour:02d}.00–{(best_hour + 1) % 24:02d}.00 "
            f"({format_rupiah(best_income)})"
        )
    else:
        best_hour_text = "-"

    accepted_times = [
        _stored_datetime(str(order["accepted_at"]))
        for order in orders
        if order["accepted_at"] is not None
    ]
    if orders and len(accepted_times) == len(orders):
        started_at = min(accepted_times)
        finished_at = max(
            _stored_datetime(str(order["completed_at"])) for order in orders
        )
        duration_seconds = int((finished_at - started_at).total_seconds())
        if duration_seconds > 0:
            duration_minutes = duration_seconds // 60
            duration_hours, remaining_minutes = divmod(duration_minutes, 60)
            duration_text = f"{duration_hours} j {remaining_minutes:02d} m"
            income_per_hour = int(
                total_income / (duration_seconds / 3600) / 100 + 0.5
            ) * 100
            income_per_hour_text = format_rupiah(income_per_hour)
        else:
            duration_text = "tidak tersedia (durasi tidak valid)"
            income_per_hour_text = "-"
    elif orders:
        duration_text = "tidak tersedia (waktu diterima belum tercatat)"
        income_per_hour_text = "-"
    else:
        duration_text = "-"
        income_per_hour_text = "-"

    if total_distance > 0:
        income_per_km = total_income / total_distance
        if income_per_km < min_per_km:
            status = "di bawah rentang"
        elif income_per_km > max_per_km:
            status = "di atas rentang"
        else:
            status = "dalam rentang"
        income_per_km_text = (
            f"{format_rupiah(round(income_per_km))} "
            f"(patokan {format_rupiah(min_per_km)}–"
            f"{format_rupiah(max_per_km)}, {status})"
        )
    else:
        income_per_km_text = (
            f"- (patokan {format_rupiah(min_per_km)}–"
            f"{format_rupiah(max_per_km)}, belum ada jarak tercatat)"
        )

    return (
        f"Rekap hari ini ({now:%d-%m-%Y} WIB)\n"
        f"• Order: {len(orders)}\n"
        f"• Pendapatan: {format_rupiah(total_income)}\n"
        f"• Jarak tercatat: {total_distance:g} km\n"
        f"• Durasi narik: {duration_text}\n"
        f"• Pendapatan/jam: {income_per_hour_text}\n"
        f"• Pendapatan/km: {income_per_km_text}\n"
        f"• Jam terbaik: {best_hour_text}"
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
    application.add_handler(CommandHandler("harga", harga))
    application.add_handler(CommandHandler("cekorder", cekorder))
    application.add_handler(CommandHandler("setkm", setkm))
    application.add_handler(CommandHandler("resetharga", resetharga))
    application.add_handler(CommandHandler("catat", catat))
    application.add_handler(CommandHandler("rekap", rekap))
    application.add_handler(CallbackQueryHandler(feedback, pattern=r"^feedback:"))
    application.add_error_handler(error_handler)
    return application
