import sys
print("Python executable:", sys.executable)
print("Python version:", sys.version)
print("\nTrying to import packages...")

try:
    import fastapi
    print("✓ fastapi imported successfully")
except Exception as e:
    print("✗ fastapi import failed:", e)

try:
    import uvicorn
    print("✓ uvicorn imported successfully")
except Exception as e:
    print("✗ uvicorn import failed:", e)

try:
    import pandas
    print("✓ pandas imported successfully")
except Exception as e:
    print("✗ pandas import failed:", e)

print("\nAll done!")


