from app.database import init_db
from app.logging_config import configure_logging
from app.worker import process_one_pending_task


def main() -> None:
    configure_logging()
    init_db()
    processed = 0
    while process_one_pending_task():
        processed += 1
    print(f"Processed {processed} queued task(s)")


if __name__ == "__main__":
    main()

