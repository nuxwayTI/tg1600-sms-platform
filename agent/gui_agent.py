import json
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox
import requests

from tg1600 import TG1600Client

CONFIG_FILE = "config.json"


def default_config():
    return {
        "server_url": "https://TU-SERVICIO.onrender.com",
        "api_key": "",
        "agent_id": "tg1600-001",
        "tg_host": "192.168.20.31",
        "tg_port": 5038,
        "tg_user": "apiuser",
        "tg_pass": "apipass",
        "poll_seconds": 5
    }


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return default_config()

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("TG1600 SMS Agent")
        self.root.geometry("650x560")

        self.running = False
        self.thread = None
        self.cfg = load_config()

        self.entries = {}

        fields = [
            ("server_url", "URL Render"),
            ("api_key", "API Key"),
            ("agent_id", "Agent ID"),
            ("tg_host", "IP TG1600"),
            ("tg_port", "Puerto TG1600"),
            ("tg_user", "Usuario TG1600"),
            ("tg_pass", "Password TG1600"),
            ("poll_seconds", "Poll segundos")
        ]

        row = 0

        for key, label in fields:
            tk.Label(root, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=6)

            entry = tk.Entry(root, width=55, show="*" if key in ["api_key", "tg_pass"] else "")
            entry.insert(0, str(self.cfg.get(key, "")))
            entry.grid(row=row, column=1, padx=10, pady=6)

            self.entries[key] = entry
            row += 1

        self.status = tk.Label(root, text="Estado: detenido", fg="red")
        self.status.grid(row=row, column=0, columnspan=2, pady=10)

        row += 1

        tk.Button(root, text="Guardar configuración", command=self.save).grid(row=row, column=0, pady=10)
        tk.Button(root, text="Conectar y ejecutar", command=self.start).grid(row=row, column=1, pady=10)

        row += 1

        self.log = tk.Text(root, height=18, width=78)
        self.log.grid(row=row, column=0, columnspan=2, padx=10, pady=10)

    def write_log(self, text):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)

    def save(self):
        cfg = {}

        for key, entry in self.entries.items():
            value = entry.get().strip()

            if key in ["tg_port", "poll_seconds"]:
                value = int(value)

            cfg[key] = value

        save_config(cfg)
        self.cfg = cfg

        messagebox.showinfo("OK", "Configuración guardada")

    def start(self):
        self.save()

        if self.running:
            messagebox.showinfo("Info", "El agente ya está corriendo")
            return

        self.running = True
        self.status.config(text="Estado: conectado / ejecutando", fg="green")

        self.thread = threading.Thread(target=self.run_agent, daemon=True)
        self.thread.start()

    def run_agent(self):
        cfg = self.cfg

        try:
            self.write_log("Conectando al TG1600...")

            tg = TG1600Client(
                host=cfg["tg_host"],
                port=cfg["tg_port"],
                username=cfg["tg_user"],
                password=cfg["tg_pass"]
            )

            tg.connect()
            self.write_log("TG1600 conectado correctamente.")

            server_url = cfg["server_url"].rstrip("/")
            api_key = cfg["api_key"]
            agent_id = cfg["agent_id"]
            poll_seconds = cfg["poll_seconds"]

            while self.running:
                response = requests.get(
                    f"{server_url}/agent/poll",
                    params={
                        "agent_id": agent_id,
                        "agent_key": api_key
                    },
                    timeout=30
                )

                response.raise_for_status()
                job = response.json().get("job")

                if job:
                    self.write_log(
                        f"Enviando SMS ID {job['id']} a {job['phone']} por chip {job['chip']}"
                    )

                    result = tg.send_sms(
                        chip=job["chip"],
                        to_number=job["phone"],
                        message=job["text"],
                        message_id=job["id"]
                    )

                    requests.post(
                        f"{server_url}/agent/result",
                        params={"agent_key": api_key},
                        json={
                            "id": job["id"],
                            "success": result["success"],
                            "raw": result["raw"]
                        },
                        timeout=30
                    )

                    self.write_log(f"Resultado SMS {job['id']}: {result['success']}")

                time.sleep(poll_seconds)

        except Exception as e:
            self.running = False
            self.status.config(text="Estado: error", fg="red")
            self.write_log("ERROR: " + str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
