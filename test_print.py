import sys
print("Python is working")
print(sys.executable)
import logzero
print("Logzero imported")
try:
    from SmartApi import SmartConnect
    print("SmartConnect imported")
except Exception as e:
    print(f"SmartConnect import failed: {e}")
