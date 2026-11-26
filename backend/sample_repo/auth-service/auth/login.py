"""Login endpoint."""
import logging

log = logging.getLogger("auth.login")

def login(username: str, password: str, client_ip: str, users) -> bool:
    user = users.get(username)
    if user is None or not user.check_password(password):
        log.warning("Login failed for user %s from %s", username, client_ip)
        return False
    log.info("Login succeeded for user %s from %s", username, client_ip)
    return True
