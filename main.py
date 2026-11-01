import logging
import os
from pathlib import Path

from bot import create_application
from config import DATABASE_PATH
from database import Database
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN belum diatur. Salin .env.example menjadi .env "
            "dan isi token bot Telegram Anda."
        )

    database_path = Path(os.getenv("DATABASE_PATH", DATABASE_PATH))
    database = Database(database_path)
    application = create_application(token, database)
    application.run_polling()


if __name__ == "__main__":
    main()
