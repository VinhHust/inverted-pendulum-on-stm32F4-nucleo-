import tkinter as tk
from tkinter import ttk, messagebox
import serial
import struct
import collections
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class LQRTunerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LQR Tuner")
        self.serial_port = None
        self.is_reading = False

        # --- Dữ liệu vẽ đồ thị (lưu 150 điểm gần nhất cho mượt) ---
        self.data_len = 150
        self.q_cart = collections.deque([0]*self.data_len, maxlen=self.data_len)
        self.q_angle = collections.deque([0]*self.data_len, maxlen=self.data_len)
        self.q_speed = collections.deque([0]*self.data_len, maxlen=self.data_len)

        self.setup_ui()

    def setup_ui(self):
        # ==========================================
        # KHUNG TRÁI: BẢNG ĐIỀU KHIỂN (TUNER)
        # ==========================================
        # Dùng Canvas + Scrollbar vì số lượng slider đã tăng lên nhiều
        container = tk.Frame(self.root)
        container.pack(side=tk.LEFT, fill=tk.Y, padx=0, pady=0)

        canvas_scroll = tk.Canvas(container, borderwidth=0, highlightthickness=0, width=330)
        scrollbar = tk.Scrollbar(container, orient=tk.VERTICAL, command=canvas_scroll.yview)
        left_frame = tk.Frame(canvas_scroll)

        left_frame.bind(
            "<Configure>",
            lambda e: canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))
        )

        canvas_scroll.create_window((0, 0), window=left_frame, anchor="nw")
        canvas_scroll.configure(yscrollcommand=scrollbar.set)

        canvas_scroll.pack(side=tk.LEFT, fill=tk.Y)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y)

        left_frame.configure(padx=15, pady=10)

        # 1. Kết nối COM
        conn_frame = tk.Frame(left_frame)
        conn_frame.pack(pady=10)
        tk.Label(conn_frame, text="COM:", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        self.com_entry = tk.Entry(conn_frame, width=8, font=("Arial", 10))
        self.com_entry.insert(0, "COM3")
        self.com_entry.pack(side=tk.LEFT, padx=5)
        self.btn_connect = tk.Button(conn_frame, text="Kết nối", bg="lightblue", command=self.toggle_connection)
        self.btn_connect.pack(side=tk.LEFT)

        self._separator(left_frame)

        # 2. Data LQR (0x01 - 0x04)
        tk.Label(left_frame, text="Data LQR", font=("Arial", 9, "bold"), fg="#444").pack(anchor="w", pady=(0, 4))
        self.sliders = {}
        self.create_slider(left_frame, "Góc", 0x01, -300, 500, 350.0)
        self.create_slider(left_frame, "Vận tốc Góc", 0x02, -150, 150, 60.0)
        self.create_slider(left_frame, "Vị trí Xe", 0x03, -200, 300, 100.0)
        self.create_slider(left_frame, "Vận tốc Xe", 0x04, -100, 100, 15.0)

        self._separator(left_frame)

        # Angle Offset (0x05)
        self.create_slider(left_frame, "Angle Offset", 0x05, -0.2, 0.2, 0.0, 0.001)

        self._separator(left_frame)

        # 3. Data tốc độ max balance (0x06 - 0x07)
        tk.Label(left_frame, text="Tốc độ max balance", font=("Arial", 9, "bold"), fg="#444").pack(anchor="w", pady=(0, 4))
        self.create_slider(left_frame, "vận tốc LQR max", 0x06, 0.5, 5.0, 2.5, 0.1)
        self.create_slider(left_frame, "gia tốc LQR max", 0x07, 0.5, 10.0, 2.5, 0.1)

        self._separator(left_frame)

        # 4. Data kickstart (0x08 - 0x09)
        tk.Label(left_frame, text="Data kickstart", font=("Arial", 9, "bold"), fg="#444").pack(anchor="w", pady=(0, 4))
        self.create_slider(left_frame, "kick_acce", 0x08, 0.0, 10.0, 2.5, 0.1)
        self.create_slider(left_frame, "max_kick_speed", 0x09, 0.0, 5.0, 1.0, 0.1)

        self._separator(left_frame)

        # 5. Data balance (0x10 - 0x11)
        tk.Label(left_frame, text="Data balance", font=("Arial", 9, "bold"), fg="#444").pack(anchor="w", pady=(0, 4))
        self.create_slider(left_frame, "k_swing", 0x10, 0.0, 10.0, 1.0, 0.1)
        self.create_slider(left_frame, "max_swing_acce", 0x11, 0.0, 10.0, 2.5, 0.1)

        self._separator(left_frame)

        # 6. Data cho PD trong swing up (0x12 - 0x13)
        tk.Label(left_frame, text="Data cho PD trong swing up", font=("Arial", 9, "bold"), fg="#444").pack(anchor="w", pady=(0, 4))
        self.create_slider(left_frame, "k1_swing", 0x12, 0.0, 10.0, 1.0, 0.1)
        self.create_slider(left_frame, "k2_swing", 0x13, 0.0, 10.0, 1.0, 0.1)

        # ==========================================
        # KHUNG PHẢI: 3 ĐỒ THỊ REAL-TIME
        # ==========================================
        right_frame = tk.Frame(self.root)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.fig = Figure(figsize=(7, 6), dpi=100)

        # Tạo 3 Subplot xếp dọc (3 hàng, 1 cột)
        self.ax1 = self.fig.add_subplot(311)
        self.ax2 = self.fig.add_subplot(312)
        self.ax3 = self.fig.add_subplot(313)

        # Cài đặt tiêu đề và màu cho từng đồ thị
        self.ax1.set_title("Vị trí Cart (m)", fontsize=10)
        self.line_cart, = self.ax1.plot(self.q_cart, color='#1f77b4')  # Màu xanh dương

        self.ax2.set_title("Góc Pendulum (rad)", fontsize=10)
        self.line_angle, = self.ax2.plot(self.q_angle, color='#ff7f0e')  # Màu cam

        self.ax3.set_title("Target Speed (m/s)", fontsize=10)
        self.line_speed, = self.ax3.plot(self.q_speed, color='#2ca02c')  # Màu xanh lá

        # Căn chỉnh khoảng cách giữa 3 đồ thị để không bị đè chữ lên nhau
        self.fig.tight_layout(pad=2.0)

        self.canvas = FigureCanvasTkAgg(self.fig, master=right_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _separator(self, parent):
        tk.Frame(parent, height=2, bg="gray").pack(fill=tk.X, pady=10)

    def create_slider(self, parent, label, address, min_val, max_val, default_val, resolution=0.1):
        frame = tk.Frame(parent)
        frame.pack(pady=4, fill=tk.X)
        tk.Label(frame, text=label, width=16, anchor="w", font=("Arial", 9)).pack(side=tk.LEFT)
        val_label = tk.Label(frame, text=f"{default_val:.3f}", width=6, font=("Arial", 9, "bold"))
        val_label.pack(side=tk.RIGHT)
        slider = ttk.Scale(frame, from_=min_val, to=max_val, orient=tk.HORIZONTAL)
        slider.set(default_val)
        slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        slider.configure(command=lambda val, a=address, l=val_label: self.on_slider_change(val, a, l))
        self.sliders[address] = slider

    def toggle_connection(self):
        if self.serial_port and self.serial_port.is_open:
            self.is_reading = False
            self.serial_port.close()
            self.btn_connect.config(text="Kết nối", bg="lightblue")
        else:
            try:
                self.serial_port = serial.Serial(self.com_entry.get(), 115200, timeout=0.1)
                self.btn_connect.config(text="Ngắt kết nối", bg="salmon")
                self.is_reading = True
                self.read_serial()
            except Exception as e:
                messagebox.showerror("Lỗi kết nối", f"Không thể mở cổng COM.\n{str(e)}")

    def on_slider_change(self, val, address, val_label):
        float_val = float(val)
        val_label.config(text=f"{float_val:.3f}")
        if self.serial_port and self.serial_port.is_open:
            packet = struct.pack('<Bf', address, float_val)
            self.serial_port.write(packet)

    def read_serial(self):
        if self.is_reading and self.serial_port and self.serial_port.is_open:
            try:
                while self.serial_port.in_waiting > 0:
                    line = self.serial_port.readline().decode('utf-8').strip()
                    if line:
                        parts = line.split()
                        if len(parts) == 3:
                            self.q_cart.append(float(parts[0]))
                            self.q_angle.append(float(parts[1]))
                            self.q_speed.append(float(parts[2]))

                # Cập nhật dữ liệu cho cả 3 đường
                self.line_cart.set_ydata(self.q_cart)
                self.line_angle.set_ydata(self.q_angle)
                self.line_speed.set_ydata(self.q_speed)

                # Tự động co giãn (Auto-scale) cho cả 3 trục Y
                for ax in [self.ax1, self.ax2, self.ax3]:
                    ax.relim()
                    ax.autoscale_view()

                self.canvas.draw_idle()

            except Exception:
                pass

            self.root.after(20, self.read_serial)

if __name__ == "__main__":
    root = tk.Tk()
    # Tăng kích thước cửa sổ để hiển thị 3 đồ thị thoải mái
    root.geometry("1250x700")
    app = LQRTunerApp(root)
    root.mainloop()