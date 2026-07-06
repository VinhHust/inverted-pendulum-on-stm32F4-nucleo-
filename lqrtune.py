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
        left_frame = tk.Frame(self.root)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=15, pady=10)

        # 1. Kết nối COM
        conn_frame = tk.Frame(left_frame)
        conn_frame.pack(pady=10)
        tk.Label(conn_frame, text="COM:", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        self.com_entry = tk.Entry(conn_frame, width=8, font=("Arial", 10))
        self.com_entry.insert(0, "COM3")
        self.com_entry.pack(side=tk.LEFT, padx=5)
        self.btn_connect = tk.Button(conn_frame, text="Kết nối", bg="lightblue", command=self.toggle_connection)
        self.btn_connect.pack(side=tk.LEFT)

        tk.Frame(left_frame, height=2, bg="gray").pack(fill=tk.X, pady=10) # Đường gạch ngang phân cách

        # 2. Các thanh trượt LQR & Offset
        self.sliders = {}
        self.create_slider(left_frame, "Góc", 0x01, -300, 500, 350.0)
        self.create_slider(left_frame, "Vận tốc Góc", 0x02, -150, 150, 60.0)
        self.create_slider(left_frame, "Vị trí Xe", 0x03, -200, 300, 100.0)
        self.create_slider(left_frame, "Vận tốc Xe", 0x04, -100, 100, 15.0)
        self.create_slider(left_frame, "Angle Offset", 0x05, -0.2, 0.2, 0.0, 0.001)

        tk.Frame(left_frame, height=2, bg="gray").pack(fill=tk.X, pady=10) # Đường gạch ngang phân cách

        # 3. Các thanh trượt Giới hạn (Max Speed & Accel)
        self.create_slider(left_frame, "Max Vận tốc (m/s)", 0x06, 0.5, 5.0, 2.5, 0.1)
        self.create_slider(left_frame, "Max Gia tốc (m/s²)", 0x07, 0.5, 10.0, 2.5, 0.1)

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
        self.line_cart, = self.ax1.plot(self.q_cart, color='#1f77b4') # Màu xanh dương
        
        self.ax2.set_title("Góc Pendulum (rad)", fontsize=10)
        self.line_angle, = self.ax2.plot(self.q_angle, color='#ff7f0e') # Màu cam

        self.ax3.set_title("Target Speed (m/s)", fontsize=10)
        self.line_speed, = self.ax3.plot(self.q_speed, color='#2ca02c') # Màu xanh lá

        # Căn chỉnh khoảng cách giữa 3 đồ thị để không bị đè chữ lên nhau
        self.fig.tight_layout(pad=2.0)

        self.canvas = FigureCanvasTkAgg(self.fig, master=right_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

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
    root.geometry("1100x650") 
    app = LQRTunerApp(root)
    root.mainloop()