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
        "server_url": "https://tg1600-sms-platform.onrender.com",
        "api_key": "",
        "agent_id": "tg1600-001",
        "tg_host": "192.168.20.31",
        "tg_port": 5038,
        "tg_user": "apiuser",
        "tg_pass": "apipass",
        "poll_seconds": 1.0
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
        self.root.title("Nuxway SMS Agent")
        self.root.geometry("820x680")
        self.root.configure(bg="#0b1020")

        self.running = False
        self.thread = None
        self.cfg = load_config()
        self.entries = {}
        self.logo_img = None

        header = tk.Frame(root, bg="#0b1020")
        header.pack(fill="x", padx=18, pady=16)

        # Logo reducido
        if os.path.exists("logo.png"):
            try:
                raw_logo = tk.PhotoImage(file="logo.png")
                self.logo_img = raw_logo.subsample(8, 8)
                logo_box = tk.Frame(header, bg="#ffffff", padx=8, pady=8)
                logo_box.pack(side="left", padx=(0, 18))
                tk.Label(logo_box, image=self.logo_img, bg="#ffffff").pack()
            except Exception:
                pass

        title_box = tk.Frame(header, bg="#0b1020")
        title_box.pack(side="left")

        tk.Label(
            title_box,
            text="NUXWAY SMS",
            font=("Arial", 24, "bold"),
            fg="#f8fafc",
            bg="#0b1020"
        ).pack(anchor="w")

        tk.Label(
            title_box,
            text="TG Series Local Agent",
            font=("Arial", 12),
            fg="#cbd5e1",
            bg="#0b1020"
        ).pack(anchor="w")

        form = tk.Frame(root, bg="#111827", padx=16, pady=16)
        form.pack(fill="x", padx=18, pady=10)

        fields = [
            ("server_url", "URL Render"),
            ("api_key", "API Key"),
            ("agent_id", "Agent ID"),
            ("tg_host", "IP TG"),
            ("tg_port", "Puerto TG"),
            ("tg_user", "Usuario TG"),
            ("tg_pass", "Password TG"),
            ("poll_seconds", "Poll segundos")
        ]

        for row, (key, label) in enumerate(fields):
            tk.Label(form, text=label, fg="#e5e7eb", bg="#111827").grid(row=row, column=0, sticky="w", pady=5)

            entry = tk.Entry(
                form,
                width=72,
                show="*" if key in ["api_key", "tg_pass"] else "",
                bg="#0c1220",
                fg="#f8fafc",
                insertbackground="#f8fafc"
            )

            entry.insert(0, str(self.cfg.get(key, "")))
            entry.grid(row=row, column=1, padx=10, pady=5)

            self.entries[key] = entry

        self.status = tk.Label(root, text="Estado: detenido", fg="#ef4444", bg="#0b1020", font=("Arial", 12, "bold"))
        self.status.pack(pady=8)

        buttons = tk.Frame(root, bg="#0b1020")
        buttons.pack(pady=8)

        tk.Button(buttons, text="Guardar configuración", command=self.save, bg="#f59e0b", fg="#111827").pack(side="left", padx=8)
        tk.Button(buttons, text="Conectar y ejecutar", command=self.start, bg="#2563eb", fg="white").pack(side="left", padx=8)

        self.log = tk.Text(root, height=20, width=105, bg="#030712", fg="#e5e7eb", insertbackground="#f8fafc")
        self.log.pack(padx=18, pady=12)

    def write_log(self, text):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)

    def save(self):
        cfg = {}

        for key, entry in self.entries.items():
            value = entry.get().strip()

            if key == "tg_port":
                value = int(value)

            if key == "poll_seconds":
                value = float(value)

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
        self.status.config(text="Estado: conectado / ejecutando", fg="#22c55e")

        self.thread = threading.Thread(target=self.run_agent, daemon=True)
        self.thread.start()

    def run_agent(self):
        cfg = self.cfg

        try:
            self.write_log("Conectando al TG...")

            tg = TG1600Client(
                host=cfg["tg_host"],
                port=cfg["tg_port"],
                username=cfg["tg_user"],
                password=cfg["tg_pass"]
            )

            tg.connect()
            self.write_log("TG conectado correctamente.")

            server_url = cfg["server_url"].rstrip("/")
            api_key = cfg["api_key"]
            agent_id = cfg["agent_id"]
            poll_seconds = float(cfg["poll_seconds"])

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

                    self.write_log(
                        f"Chip web {result['requested_chip']} -> puerto TG {result['real_chip']}"
                    )

                    self.write_log(f"Resultado SMS {job['id']}: {result['success']}")

                    requests.post(
                        f"{server_url}/agent/result",
                        params={"agent_key": api_key},
                        json={
                            "id": job["id"],
                            "success": result["success"],
                            "raw": (
                                f"Chip web: {result['requested_chip']} | "
                                f"Puerto TG: {result['real_chip']}\n\n"
                                f"{result['raw']}"
                            )
                        },
                        timeout=30
                    )

                time.sleep(poll_seconds)

        except Exception as e:
            self.running = False
            self.status.config(text="Estado: error", fg="#ef4444")
            self.write_log("ERROR: " + str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
