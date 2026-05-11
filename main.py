import os
import sys
import tkinter as tk
from tkinter import simpledialog

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GROQ_API_KEY", "").strip()

if not API_KEY:
    root = tk.Tk()
    root.withdraw()
    API_KEY = simpledialog.askstring(
        "Grok API Key",
        "Enter your Grok API Key:",
        show="*",
    )
    root.destroy()

if not API_KEY:
    print("No API key provided. Exiting.")
    sys.exit(1)

from gui import USBAgentApp  # noqa: E402

app = USBAgentApp(API_KEY)
app.mainloop()
