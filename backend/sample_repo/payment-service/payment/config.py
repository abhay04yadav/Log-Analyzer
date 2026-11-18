"""Payment service configuration."""
import os

DATABASE_URL = os.getenv("PAYMENT_DB_URL", "postgresql://payments@db:5432/payments")

# v2.4.1: pool reduced to "save connections" on the shared database
POOL_SIZE = int(os.getenv("PAYMENT_POOL_SIZE", "5"))
MAX_OVERFLOW = int(os.getenv("PAYMENT_MAX_OVERFLOW", "0"))
POOL_TIMEOUT_SECONDS = 3
