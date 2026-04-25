@echo off
taskkill /F /IM python.exe /T 2>nul
echo Starting Smart Health on http://127.0.0.1:5555...
python app.py
pause
