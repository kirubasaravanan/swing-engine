import os
import sys

# DEBUG: Write immediately
with open("angel_connect.log", "w", encoding="utf-8") as f:
    f.write("Using Python: " + sys.executable + "\n")

try:
    from dotenv import load_dotenv
    import pyotp
    import time
    # Lazy Import SmartApi later
except Exception as e:
    with open("angel_connect.log", "a") as f: f.write(f"Import Error: {e}\n")

# Load Environment Variables from .env
load_dotenv()

class AngelOneManager:
    def __init__(self):
        self.api_key = os.getenv("ANGEL_API_KEY")
        self.client_id = os.getenv("ANGEL_CLIENT_ID")
        self.password = os.getenv("ANGEL_PIN")
        self.totp_key = os.getenv("ANGEL_TOTP_KEY")
        self.smart_api = None
        self.auth_token = None

    def login(self):
        try:
            with open("angel_connect.log", "a") as log:
                log.write(f"Connecting to Angel One (Client: {self.client_id})...\n")
            
            # Lazy Import
            try:
                from SmartApi import SmartConnect
            except Exception as ie:
                return False, f"SmartApi Library Missing: {ie}"

            # 1. Initialize Object
            self.smart_api = SmartConnect(api_key=self.api_key)
            
            # 2. Generate TOTP
            try:
                totp = pyotp.TOTP(self.totp_key).now()
            except Exception as e:
                return False, f"TOTP Generation Failed: {e}"
            
            # 3. Authenticate
            data = self.smart_api.generateSession(self.client_id, self.password, totp)
            
            if data['status'] and data['message'] == 'SUCCESS':
                self.auth_token = data['data']['jwtToken']
                return True, "Login Success"
            else:
                return False, f"Login Failed: {data['message']} (Code: {data['errorcode']})"
                
        except Exception as e:
            return False, f"Connection Error: {str(e)}"

    def get_profile(self):
        if not self.auth_token: return None
        return self.smart_api.getProfile(self.auth_token)

if __name__ == "__main__":
    with open("angel_connect.log", "a") as f:
        f.write("Starting Main Logic...\n")
        try:
            manager = AngelOneManager()
            success, msg = manager.login()
            f.write(f"Result: {msg}\n")
            if success:
                f.write("Profile:\n")
                f.write(str(manager.get_profile()) + "\n")
        except Exception as e:
            f.write(f"CRITICAL MAIN ERROR: {e}\n")
