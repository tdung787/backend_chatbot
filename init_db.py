import logging
from database.db import engine, Base
from database.models import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    try:
        logger.info("🔄 Đang tạo database...")
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database đã được khởi tạo thành công!")
    except Exception as e:
        logger.error(f"❌ Lỗi khi tạo database: {e}")

if __name__ == "__main__":
    init_db()
