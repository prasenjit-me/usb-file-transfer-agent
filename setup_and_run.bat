@echo off
echo ===================================
echo  USB File Transfer Agent - Setup
echo ===================================

echo Installing dependencies...
python -m pip install -r requirements.txt

echo.
echo Setup complete! Launching app...
echo.
python main.py

pause
