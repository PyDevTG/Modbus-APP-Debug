"""
Cliente Modbus TCP com interface gráfica (CustomTkinter)
Inspirado no QModMaster.

Dependências:
    pip install customtkinter pyModbusTCP
"""

import queue
import threading
import time
from datetime import datetime
from tkinter import ttk

import customtkinter as ctk
from pyModbusTCP.client import ModbusClient

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# código da função -> (rótulo, é escrita?, é bit?)
FUNCTIONS = {
    "01 - Read Coils": (1, False, True),
    "02 - Read Discrete Inputs": (2, False, True),
    "03 - Read Holding Registers": (3, False, False),
    "04 - Read Input Registers": (4, False, False),
    "05 - Write Single Coil": (5, True, True),
    "06 - Write Single Register": (6, True, False),
    "15 - Write Multiple Coils": (15, True, True),
    "16 - Write Multiple Registers": (16, True, False),
}
DEFAULT_FUNC = "03 - Read Holding Registers"


def parse_int(text: str) -> int:
    """Aceita decimal, 0x hexadecimal e 0b binário."""
    return int(text.strip(), 0)


def parse_bool(text: str) -> bool:
    t = text.strip().lower()
    if t in ("1", "true", "on", "sim", "t"):
        return True
    if t in ("0", "false", "off", "nao", "não", "f"):
        return False
    raise ValueError(f"Valor booleano inválido: '{text}'")


def split_values(text: str):
    return [v for v in text.replace(";", ",").replace(" ", ",").split(",") if v.strip()]


class ModbusApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Modbus TCP Client")
        self.geometry("1180x760")
        self.minsize(1000, 640)

        self.client: ModbusClient | None = None
        self.lock = threading.Lock()
        self.q: queue.Queue = queue.Queue()
        self.connected = False
        self.stop_evt = threading.Event()
        self.cyclic_running = False
        self._cyc_lock = threading.Lock()
        self._cyc_params = None
        self._cyc_interval = 1.0
        self._last_err = None
        self._row_ids: list[str] = []
        self._row_sig = None

        self._build_ui()
        self._style_tree()
        self._on_function_change(DEFAULT_FUNC)
        self._set_connected(False)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._process_queue)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ---------- Rodapé ----------
        ctk.CTkLabel(self, text="Desenvolvido por Thiago dos Santos Alves, 2026",
                     text_color="gray60", font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, columnspan=2, pady=(0, 8))

        # ---------- Sidebar (conexão) ----------
        side = ctk.CTkFrame(self, width=270, corner_radius=0)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)

        ctk.CTkLabel(side, text="Modbus TCP", font=ctk.CTkFont(size=24, weight="bold")).pack(
            padx=20, pady=(24, 0), anchor="w"
        )
        ctk.CTkLabel(side, text="Cliente / Master", text_color="gray60").pack(padx=20, anchor="w")

        conn = ctk.CTkFrame(side)
        conn.pack(fill="x", padx=16, pady=(24, 8))
        ctk.CTkLabel(conn, text="CONEXÃO", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="gray60").pack(anchor="w", padx=12, pady=(10, 4))

        self.ent_ip = self._labeled_entry(conn, "Endereço IP", "192.168.0.10")
        self.ent_port = self._labeled_entry(conn, "Porta", "502")
        self.ent_unit = self._labeled_entry(conn, "Unit ID (Slave)", "1")
        self.ent_timeout = self._labeled_entry(conn, "Timeout (s)", "2.0")

        self.btn_connect = ctk.CTkButton(conn, text="Conectar", height=38,
                                         font=ctk.CTkFont(weight="bold"),
                                         command=self._toggle_connection)
        self.btn_connect.pack(fill="x", padx=12, pady=(14, 8))

        self.lbl_status = ctk.CTkLabel(conn, text="● Desconectado", text_color="#e74c3c",
                                       font=ctk.CTkFont(weight="bold"))
        self.lbl_status.pack(pady=(0, 12))

        ctk.CTkLabel(side, text="Tema").pack(side="bottom", pady=(0, 16))
        self.opt_theme = ctk.CTkOptionMenu(side, values=["Dark", "Light", "System"],
                                           command=self._change_theme)
        self.opt_theme.pack(side="bottom", padx=16, pady=(0, 4), fill="x")

        # ---------- Área principal ----------
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=(0, 16), pady=16)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=3)
        main.grid_rowconfigure(4, weight=1)

        # Configuração da requisição
        cfg = ctk.CTkFrame(main)
        cfg.grid(row=0, column=0, sticky="ew")
        for i in range(4):
            cfg.grid_columnconfigure(i, weight=1)

        ctk.CTkLabel(cfg, text="REQUISIÇÃO", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="gray60").grid(row=0, column=0, sticky="w", padx=14, pady=(10, 0))

        self._cfg_label(cfg, "Função", 1, 0)
        self.opt_func = ctk.CTkOptionMenu(cfg, values=list(FUNCTIONS.keys()),
                                          command=self._on_function_change)
        self.opt_func.set(DEFAULT_FUNC)
        self.opt_func.grid(row=2, column=0, sticky="ew", padx=(14, 6), pady=(0, 10))

        self._cfg_label(cfg, "Endereço inicial", 1, 1)
        self.ent_addr = ctk.CTkEntry(cfg)
        self.ent_addr.insert(0, "0")
        self.ent_addr.grid(row=2, column=1, sticky="ew", padx=6, pady=(0, 10))

        self._cfg_label(cfg, "Quantidade", 1, 2)
        self.ent_qty = ctk.CTkEntry(cfg)
        self.ent_qty.insert(0, "10")
        self.ent_qty.grid(row=2, column=2, sticky="ew", padx=6, pady=(0, 10))

        self._cfg_label(cfg, "Intervalo do monitoramento (ms)", 1, 3)
        self.ent_rate = ctk.CTkEntry(cfg)
        self.ent_rate.insert(0, "1000")
        self.ent_rate.grid(row=2, column=3, sticky="ew", padx=(6, 14), pady=(0, 10))

        self._cfg_label(cfg, "Valores a escrever (separe por vírgula; aceita 0x1F, 0b101; um único valor é repetido na quantidade)", 3, 0)
        self.ent_values = ctk.CTkEntry(cfg, placeholder_text="ex.: 100, 200, 0x1F")
        self.ent_values.grid(row=4, column=0, columnspan=4, sticky="ew", padx=14, pady=(0, 12))

        # Botões de ação
        bar = ctk.CTkFrame(main, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", pady=10)
        self.btn_once = ctk.CTkButton(bar, text="Ler", width=150, height=38,
                                      font=ctk.CTkFont(weight="bold"), command=self._run_once)
        self.btn_once.pack(side="left")
        self.btn_cyclic = ctk.CTkButton(bar, text="⟳  Iniciar monitoramento", width=210, height=38,
                                        fg_color="#2e8b57", hover_color="#246b44",
                                        font=ctk.CTkFont(weight="bold"), command=self._toggle_cyclic)
        self.btn_cyclic.pack(side="left", padx=10)
        for e in (self.ent_addr, self.ent_qty, self.ent_rate):
            e.bind("<KeyRelease>", self._on_live_edit)
        ctk.CTkLabel(bar, text="Dica: dê duplo clique numa linha para escrever naquele endereço",
                     text_color="gray60").pack(side="right")

        # Tabela
        tbl_frame = ctk.CTkFrame(main)
        tbl_frame.grid(row=2, column=0, sticky="nsew")
        tbl_frame.grid_columnconfigure(0, weight=1)
        tbl_frame.grid_rowconfigure(0, weight=1)

        cols = ("addr", "dec", "signed", "hex", "bin", "time")
        self.tree = ttk.Treeview(tbl_frame, columns=cols, show="headings",
                                 style="Modbus.Treeview", selectmode="browse")
        heads = {"addr": ("Endereço", 90), "dec": ("Decimal", 100), "signed": ("Com sinal", 100),
                 "hex": ("Hex", 90), "bin": ("Binário", 230), "time": ("Atualizado", 110)}
        for c, (t, w) in heads.items():
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center", stretch=(c == "bin"))
        sb = ctk.CTkScrollbar(tbl_frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        sb.grid(row=0, column=1, sticky="ns", pady=6, padx=(0, 4))
        self.tree.bind("<Double-1>", self._on_row_double_click)

        # Log
        log_head = ctk.CTkFrame(main, fg_color="transparent")
        log_head.grid(row=3, column=0, sticky="ew", pady=(10, 2))
        ctk.CTkLabel(log_head, text="LOG", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="gray60").pack(side="left")
        ctk.CTkButton(log_head, text="Limpar", width=70, height=24, fg_color="gray40",
                      command=self._clear_log).pack(side="right")

        self.log = ctk.CTkTextbox(main, height=140, font=ctk.CTkFont(family="Consolas", size=12))
        self.log.grid(row=4, column=0, sticky="nsew")
        self.log.configure(state="disabled")

    def _labeled_entry(self, parent, label, default):
        ctk.CTkLabel(parent, text=label, anchor="w").pack(fill="x", padx=14, pady=(6, 0))
        e = ctk.CTkEntry(parent)
        e.insert(0, default)
        e.pack(fill="x", padx=12, pady=(0, 2))
        return e

    @staticmethod
    def _cfg_label(parent, text, row, col):
        ctk.CTkLabel(parent, text=text, anchor="w", text_color="gray70").grid(
            row=row, column=col, columnspan=4 if col == 0 and row == 3 else 1,
            sticky="w", padx=14 if col == 0 else 6, pady=(4, 0))

    # ---------------------------------------------------------------- Tema
    def _change_theme(self, mode):
        ctk.set_appearance_mode(mode)
        self.after(100, self._style_tree)

    def _style_tree(self):
        dark = ctk.get_appearance_mode() == "Dark"
        bg = "#2b2b2b" if dark else "#f5f5f5"
        alt = "#323232" if dark else "#e9e9e9"
        fg = "#e6e6e6" if dark else "#1a1a1a"
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Modbus.Treeview", background=bg, fieldbackground=bg, foreground=fg,
                        rowheight=26, borderwidth=0, font=("Consolas", 11))
        style.configure("Modbus.Treeview.Heading", background="#1f538d", foreground="white",
                        relief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Modbus.Treeview", background=[("selected", "#1f6aa5")],
                  foreground=[("selected", "white")])
        style.map("Modbus.Treeview.Heading", background=[("active", "#144870")])
        self.tree.tag_configure("odd", background=alt)
        self.tree.tag_configure("even", background=bg)

    # ------------------------------------------------------------ Log
    def _log(self, msg, level="INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{ts}] {level:<5} {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    # ------------------------------------------------- Estado dos controles
    def _set_connected(self, connected: bool):
        self.connected = connected
        if connected:
            self.lbl_status.configure(text="● Conectado", text_color="#2ecc71")
            self.btn_connect.configure(text="Desconectar", fg_color="#c0392b", hover_color="#992d22")
        else:
            self.lbl_status.configure(text="● Desconectado", text_color="#e74c3c")
            self.btn_connect.configure(text="Conectar", fg_color=("#3a7ebf", "#1f538d"),
                                       hover_color=("#325882", "#14375e"))
        state = "disabled" if connected else "normal"
        for e in (self.ent_ip, self.ent_port, self.ent_unit, self.ent_timeout):
            e.configure(state=state)
        self.btn_once.configure(state="normal" if connected else "disabled")
        self._refresh_cyclic_btn()

    def _refresh_cyclic_btn(self):
        """Monitoramento só faz sentido para funções de leitura."""
        _, is_write, _ = FUNCTIONS[self.opt_func.get()]
        ok = self.cyclic_running or (self.connected and not is_write)
        self.btn_cyclic.configure(state="normal" if ok else "disabled")

    def _on_function_change(self, name):
        fc, is_write, _ = FUNCTIONS[name]
        self.btn_once.configure(text="Escrever" if is_write else "Ler")
        self.ent_values.configure(state="normal" if is_write else "disabled")
        # quantidade só fica travada nas escritas simples (05 e 06)
        self.ent_qty.configure(state="disabled" if fc in (5, 6) else "normal")
        self._refresh_cyclic_btn()

    # ---------------------------------------------------------- Conexão
    def _toggle_connection(self):
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        try:
            host = self.ent_ip.get().strip()
            port = int(self.ent_port.get())
            unit = int(self.ent_unit.get())
            timeout = float(self.ent_timeout.get().replace(",", "."))
            if not host:
                raise ValueError("IP vazio")
        except ValueError as e:
            self._log(f"Parâmetros de conexão inválidos: {e}", "ERRO")
            return

        self.btn_connect.configure(state="disabled", text="Conectando...")
        self._log(f"Conectando a {host}:{port} (unit {unit})...")

        def worker():
            try:
                c = ModbusClient(host=host, port=port, unit_id=unit, timeout=timeout,
                                 auto_open=False, auto_close=False)
                ok = bool(c.open())
                self.q.put(("connect_result", ok, c, host, port))
            except Exception as ex:  # noqa: BLE001
                self.q.put(("connect_result", False, None, host, port, str(ex)))

        threading.Thread(target=worker, daemon=True).start()

    def _disconnect(self):
        self._stop_cyclic()
        with self.lock:
            if self.client:
                try:
                    self.client.close()
                except Exception:  # noqa: BLE001
                    pass
        self._set_connected(False)
        self._log("Desconectado.")

    # ------------------------------------------------------ Requisições
    def _read_params(self, quiet=False):
        """Lê e valida os campos da UI (executar sempre na thread da UI)."""
        name = self.opt_func.get()
        fc, is_write, is_bit = FUNCTIONS[name]
        try:
            addr = parse_int(self.ent_addr.get())
            if not 0 <= addr <= 65535:
                raise ValueError("endereço fora de 0..65535")

            if is_write:
                raw = split_values(self.ent_values.get())
                if not raw:
                    raise ValueError("informe ao menos um valor para escrever")
                if is_bit:
                    vals = [parse_bool(v) for v in raw]
                else:
                    vals = [parse_int(v) & 0xFFFF for v in raw]   # aceita negativos
                if fc in (5, 6):
                    vals = vals[:1]
                else:
                    qty = int(self.ent_qty.get())
                    max_q = 1968 if is_bit else 123
                    if not 1 <= qty <= max_q:
                        raise ValueError(f"quantidade deve ficar entre 1 e {max_q}")
                    n = len(vals)
                    if n == 1 and qty > 1:
                        vals = vals * qty                      # valor único é repetido
                    elif n < qty:
                        vals = vals + [False if is_bit else 0] * (qty - n)
                        self._log(f"{n} valor(es) informado(s): completado com 0 até {qty}.", "AVISO")
                    elif n > qty:
                        vals = vals[:qty]
                        self._log(f"{n} valores informados: usando só os {qty} primeiros.", "AVISO")
                qty = len(vals)
            else:
                qty = int(self.ent_qty.get())
                if qty < 1:
                    raise ValueError("quantidade deve ser >= 1")
                vals = None
        except ValueError as e:
            if not quiet:
                self._log(f"Parâmetro inválido: {e}", "ERRO")
            return None
        return {"fc": fc, "addr": addr, "qty": qty, "vals": vals, "is_bit": is_bit}

    def _is_open(self):
        v = self.client.is_open
        return v() if callable(v) else bool(v)

    def _last_error(self):
        c = self.client
        for attr in ("last_error_as_txt", "last_error_txt"):
            v = getattr(c, attr, None)
            if v is not None:
                return v() if callable(v) else str(v)
        return "erro desconhecido"

    def _execute(self, p):
        """Executa a requisição Modbus. Roda em thread de trabalho."""
        fc, addr, qty, vals = p["fc"], p["addr"], p["qty"], p["vals"]
        c = self.client
        try:
            with self.lock:
                if not self._is_open() and not c.open():
                    return {"ok": False, "err": "Sem conexão com o host"}

                if fc == 1:
                    res = c.read_coils(addr, qty)
                elif fc == 2:
                    res = c.read_discrete_inputs(addr, qty)
                elif fc == 3:
                    res = c.read_holding_registers(addr, qty)
                elif fc == 4:
                    res = c.read_input_registers(addr, qty)
                elif fc == 5:
                    res = vals if c.write_single_coil(addr, vals[0]) else None
                elif fc == 6:
                    res = vals if c.write_single_register(addr, vals[0]) else None
                elif fc == 15:
                    res = vals if c.write_multiple_coils(addr, vals) else None
                elif fc == 16:
                    res = vals if c.write_multiple_registers(addr, vals) else None
                else:
                    return {"ok": False, "err": f"Função {fc} não suportada"}

                if res is None:
                    return {"ok": False, "err": self._last_error()}
            return {"ok": True, "vals": res}
        except Exception as ex:  # noqa: BLE001
            return {"ok": False, "err": str(ex)}

    def _run_and_report(self, p, cyclic=False):
        r = self._execute(p)
        if r["ok"]:
            if cyclic and self._last_err is not None:
                self.q.put(("log", "Comunicação restabelecida.", "OK"))
            self._last_err = None
            self.q.put(("data", p, r["vals"], cyclic))
        else:
            if not cyclic or r["err"] != self._last_err:   # evita flood no log
                self.q.put(("log", f"FC{p['fc']:02d} @ {p['addr']}: {r['err']}", "ERRO"))
            self._last_err = r["err"]

    def _run_once(self):
        p = self._read_params()
        if not p:
            return
        threading.Thread(target=self._run_and_report, args=(p,), daemon=True).start()

    # ------------------------------------------------- Monitoramento cíclico
    def _read_interval(self, quiet=False):
        try:
            ms = int(self.ent_rate.get())
            if ms < 10:
                raise ValueError("mínimo de 10 ms")
            return ms / 1000.0
        except ValueError as e:
            if not quiet:
                self._log(f"Intervalo inválido: {e}", "ERRO")
            return None

    def _toggle_cyclic(self):
        if self.cyclic_running:
            self._stop_cyclic()
        else:
            self._start_cyclic()

    def _start_cyclic(self):
        p = self._read_params()
        interval = self._read_interval()
        if not p or interval is None:
            return
        with self._cyc_lock:
            self._cyc_params, self._cyc_interval = p, interval

        self.stop_evt.clear()
        self.cyclic_running = True
        self._last_err = None
        self.btn_cyclic.configure(text="■  Parar monitoramento", fg_color="#c0392b",
                                  hover_color="#992d22")
        # função e botão Ler ficam travados; endereço, quantidade e intervalo
        # continuam editáveis e valem a partir do próximo ciclo
        self.opt_func.configure(state="disabled")
        self.btn_once.configure(state="disabled")
        self._log(f"Monitoramento iniciado ({int(interval * 1000)} ms).")

        def loop():
            while not self.stop_evt.is_set():
                t0 = time.monotonic()
                with self._cyc_lock:
                    params, itv = dict(self._cyc_params), self._cyc_interval
                self._run_and_report(params, cyclic=True)
                if self.stop_evt.wait(max(0.0, itv - (time.monotonic() - t0))):
                    break

        threading.Thread(target=loop, daemon=True).start()

    def _stop_cyclic(self):
        if not self.cyclic_running:
            return
        self.stop_evt.set()
        self.cyclic_running = False
        self.btn_cyclic.configure(text="⟳  Iniciar monitoramento", fg_color="#2e8b57",
                                  hover_color="#246b44")
        self.opt_func.configure(state="normal")
        self.btn_once.configure(state="normal" if self.connected else "disabled")
        self._refresh_cyclic_btn()
        self._log("Monitoramento parado.")

    def _on_live_edit(self, _evt=None):
        """Aplica mudanças de endereço/quantidade/intervalo com o monitoramento ativo."""
        if not self.cyclic_running:
            return
        p = self._read_params(quiet=True)
        itv = self._read_interval(quiet=True)
        with self._cyc_lock:
            if p:
                self._cyc_params = p
            if itv is not None:
                self._cyc_interval = itv

    # ------------------------------------------------------------ Tabela
    @staticmethod
    def _fmt_row(addr, v, is_bit):
        if is_bit:
            return (addr, int(bool(v)), "-", "-", "-")
        v = int(v) & 0xFFFF
        signed = v - 65536 if v >= 32768 else v
        b = f"{v:016b}"
        return (addr, v, signed, f"0x{v:04X}", " ".join(b[i:i + 4] for i in range(0, 16, 4)))

    def _update_table(self, p, values):
        ts = datetime.now().strftime("%H:%M:%S")
        rows = [self._fmt_row(p["addr"] + i, v, p["is_bit"]) + (ts,) for i, v in enumerate(values)]
        sig = (p["addr"], len(rows))

        if sig == self._row_sig and len(self._row_ids) == len(rows):
            for iid, r in zip(self._row_ids, rows):          # atualiza sem recriar
                self.tree.item(iid, values=r)
        else:
            self.tree.delete(*self.tree.get_children())
            self._row_ids = []
            for i, r in enumerate(rows):
                iid = self.tree.insert("", "end", values=r, tags=("odd" if i % 2 else "even",))
                self._row_ids.append(iid)
            self._row_sig = sig

    def _on_row_double_click(self, _evt):
        if not self.connected:
            return
        sel = self.tree.selection()
        if not sel:
            return
        addr = int(self.tree.item(sel[0], "values")[0])
        _, _, is_bit = FUNCTIONS[self.opt_func.get()]

        dlg = ctk.CTkInputDialog(
            text=f"Novo valor para o endereço {addr}"
                 + (" (0/1):" if is_bit else " (aceita 0x..):"),
            title="Escrever valor")
        txt = dlg.get_input()
        if txt is None or not txt.strip():
            return
        try:
            if is_bit:
                v, fc = parse_bool(txt), 5
            else:
                v, fc = parse_int(txt) & 0xFFFF, 6
        except ValueError as e:
            self._log(f"Valor inválido: {e}", "ERRO")
            return

        p = {"fc": fc, "addr": addr, "qty": 1, "vals": [v], "is_bit": is_bit, "no_table": True}
        # sem monitoramento ativo, relê a faixa atual depois de escrever
        p_read = None
        if not self.cyclic_running and FUNCTIONS[self.opt_func.get()][0] <= 4:
            p_read = self._read_params(quiet=True)

        def work():
            self._run_and_report(p)
            if p_read:
                self._run_and_report(p_read)

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------- Fila (thread -> UI)
    def _process_queue(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._log(msg[1], msg[2])
                elif kind == "data":
                    _, p, vals, cyclic = msg
                    if not p.get("no_table"):
                        self._update_table(p, vals)
                    if not cyclic and (p["fc"] >= 5 or not p.get("no_table")):
                        verb = "escrito(s)" if p["fc"] >= 5 else "lido(s)"
                        self._log(f"FC{p['fc']:02d}: {len(vals)} valor(es) {verb} a partir de {p['addr']}.")
                elif kind == "connect_result":
                    ok, client, host, port = msg[1], msg[2], msg[3], msg[4]
                    self.btn_connect.configure(state="normal")
                    if ok:
                        self.client = client
                        self._set_connected(True)
                        self._log(f"Conectado a {host}:{port}.", "OK")
                    else:
                        extra = f" ({msg[5]})" if len(msg) > 5 else ""
                        self._set_connected(False)
                        self._log(f"Não foi possível conectar a {host}:{port}{extra}", "ERRO")
        except queue.Empty:
            pass
        self.after(50, self._process_queue)

    # -------------------------------------------------------------- Fechar
    def _on_close(self):
        self.stop_evt.set()
        try:
            if self.client:
                self.client.close()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()


if __name__ == "__main__":
    ModbusApp().mainloop()
