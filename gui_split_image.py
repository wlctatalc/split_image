import os
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# 复用已有逻辑
from split_image import (
    ensure_dir,
    is_image_file,
    parse_pixels,
    sizes_average,
    split_vertical,
    split_horizontal,
    imread_unicode,
    imwrite_unicode,
)

APP_TITLE = "图片分割工具（支持中文路径）"
APP_GEOMETRY = "720x560"

def list_image_tasks(input_path: str):
    tasks = []
    if os.path.isdir(input_path):
        for name in sorted(os.listdir(input_path)):
            if is_image_file(name):
                tasks.append(os.path.join(input_path, name))
    else:
        if is_image_file(input_path):
            tasks.append(input_path)
    return tasks

def build_slices(total: int, sizes, append_remainder: bool, clip_excess: bool):
    # 复制 split_image 中的逻辑以避免循环依赖（该函数在 GUI 内部使用）
    sum_sizes = sum(sizes)
    slices = []
    start = 0

    if sum_sizes > total:
        if not clip_excess:
            raise ValueError(f"指定像素总和({sum_sizes})超过图像尺寸({total})，可勾选“超过裁边”以允许裁边")
        for i, sz in enumerate(sizes):
            end = start + sz
            if end > total:
                end = total
            if end <= start:
                break
            slices.append((start, end))
            start = end
            if start >= total:
                break
        return slices

    for sz in sizes:
        end = start + sz
        slices.append((start, end))
        start = end

    if sum_sizes < total and append_remainder:
        slices.append((start, total))

    slices = [(s, e) for (s, e) in slices if e > s]
    return slices

def process_one_image(in_path: str, out_dir: str, orientation: str, mode: str,
                      count: int, pixels, append_remainder: bool,
                      clip_excess: bool, out_ext: str, zero_pad: int):
    img = imread_unicode(in_path)
    if img is None:
        raise RuntimeError(f"无法读取图片: {in_path}")
    h, w = img.shape[:2]

    if mode == "average":
        if count <= 0:
            raise ValueError("average 模式需要“分割数量”且 > 0")
        sizes = sizes_average(w, count) if orientation == "vertical" else sizes_average(h, count)
    else:
        if not pixels:
            raise ValueError("pixels 模式需要像素列表")
        sizes = pixels

    if orientation == "vertical":
        ranges = build_slices(w, sizes, append_remainder, clip_excess)
        crops = [img[:, s:e] for (s, e) in ranges]
    else:
        ranges = build_slices(h, sizes, append_remainder, clip_excess)
        crops = [img[s:e, :] for (s, e) in ranges]

    base = os.path.splitext(os.path.basename(in_path))[0]
    ensure_dir(out_dir)

    digits = max(zero_pad, len(str(len(crops))))
    for i, crop in enumerate(crops, 1):
        out_name = f"{base}_part_{str(i).zfill(digits)}{out_ext}"
        out_path = os.path.join(out_dir, out_name)
        if not imwrite_unicode(out_path, crop):
            raise RuntimeError(f"写出失败: {out_path}")

    return len(crops)

class SplitGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(APP_GEOMETRY)
        self.resizable(True, True)

        self.var_input = tk.StringVar()
        self.var_output = tk.StringVar()
        self.var_orientation = tk.StringVar(value="vertical")
        self.var_mode = tk.StringVar(value="average")
        self.var_count = tk.IntVar(value=2)
        self.var_pixels = tk.StringVar(value="")
        self.var_append_remainder = tk.BooleanVar(value=True)
        self.var_clip_excess = tk.BooleanVar(value=False)
        self.var_ext = tk.StringVar(value=".jpg")
        self.var_zero_pad = tk.IntVar(value=2)

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}

        frm_paths = ttk.LabelFrame(self, text="路径")
        frm_paths.pack(fill="x", **pad)

        row1 = ttk.Frame(frm_paths); row1.pack(fill="x", **pad)
        ttk.Label(row1, text="输入文件/文件夹：").pack(side="left")
        ttk.Entry(row1, textvariable=self.var_input).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row1, text="选择文件", command=self.choose_file).pack(side="left", padx=4)
        ttk.Button(row1, text="选择文件夹", command=self.choose_dir).pack(side="left", padx=4)

        row2 = ttk.Frame(frm_paths); row2.pack(fill="x", **pad)
        ttk.Label(row2, text="输出目录：").pack(side="left")
        ttk.Entry(row2, textvariable=self.var_output).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row2, text="选择目录", command=self.choose_output).pack(side="left", padx=4)

        frm_opts = ttk.LabelFrame(self, text="参数")
        frm_opts.pack(fill="x", **pad)

        row3 = ttk.Frame(frm_opts); row3.pack(fill="x", **pad)
        ttk.Label(row3, text="方向：").pack(side="left")
        ttk.Radiobutton(row3, text="竖向(按宽度切)", variable=self.var_orientation, value="vertical").pack(side="left", padx=4)
        ttk.Radiobutton(row3, text="横向(按高度切)", variable=self.var_orientation, value="horizontal").pack(side="left", padx=4)

        row4 = ttk.Frame(frm_opts); row4.pack(fill="x", **pad)
        ttk.Label(row4, text="模式：").pack(side="left")
        ttk.Radiobutton(row4, text="平均分割", variable=self.var_mode, value="average", command=self._toggle_mode).pack(side="left", padx=4)
        ttk.Radiobutton(row4, text="按像素", variable=self.var_mode, value="pixels", command=self._toggle_mode).pack(side="left", padx=4)

        row5 = ttk.Frame(frm_opts); row5.pack(fill="x", **pad)
        self.lbl_count = ttk.Label(row5, text="分割数量：")
        self.lbl_count.pack(side="left")
        ttk.Spinbox(row5, from_=1, to=999, textvariable=self.var_count, width=8).pack(side="left", padx=4)

        row6 = ttk.Frame(frm_opts); row6.pack(fill="x", **pad)
        self.lbl_pixels = ttk.Label(row6, text="像素列表(逗号分隔)：")
        self.lbl_pixels.pack(side="left")
        ttk.Entry(row6, textvariable=self.var_pixels).pack(side="left", fill="x", expand=True, padx=4)

        row7 = ttk.Frame(frm_opts); row7.pack(fill="x", **pad)
        ttk.Checkbutton(row7, text="像素不足追加剩余", variable=self.var_append_remainder).pack(side="left", padx=4)
        ttk.Checkbutton(row7, text="像素超出裁边", variable=self.var_clip_excess).pack(side="left", padx=12)

        row8 = ttk.Frame(frm_opts); row8.pack(fill="x", **pad)
        ttk.Label(row8, text="输出格式：").pack(side="left")
        ttk.Combobox(row8, textvariable=self.var_ext, values=[".jpg", ".png", ".bmp", ".webp"], width=8, state="readonly").pack(side="left", padx=4)
        ttk.Label(row8, text="编号最少位数：").pack(side="left", padx=(12, 0))
        ttk.Spinbox(row8, from_=1, to=6, textvariable=self.var_zero_pad, width=6).pack(side="left", padx=4)

        frm_actions = ttk.Frame(self); frm_actions.pack(fill="x", **pad)
        self.btn_start = ttk.Button(frm_actions, text="开始分割", command=self.start_task)
        self.btn_start.pack(side="left")
        ttk.Button(frm_actions, text="清空日志", command=self.clear_log).pack(side="left", padx=8)

        frm_log = ttk.LabelFrame(self, text="日志")
        frm_log.pack(fill="both", expand=True, **pad)
        self.txt_log = tk.Text(frm_log, height=14)
        self.txt_log.pack(fill="both", expand=True, padx=6, pady=6)

        self._toggle_mode()

    def choose_file(self):
        path = filedialog.askopenfilename(title="选择图片文件")
        if path:
            self.var_input.set(path)

    def choose_dir(self):
        path = filedialog.askdirectory(title="选择图片文件夹")
        if path:
            self.var_input.set(path)

    def choose_output(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.var_output.set(path)

    def _toggle_mode(self):
        if self.var_mode.get() == "average":
            self.lbl_count.configure(state="normal")
            self.lbl_pixels.configure(state="disabled")
        else:
            self.lbl_count.configure(state="disabled")
            self.lbl_pixels.configure(state="normal")

    def log(self, msg: str):
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")
        self.update_idletasks()

    def clear_log(self):
        self.txt_log.delete("1.0", "end")

    def start_task(self):
        input_path = self.var_input.get().strip()
        output_dir = self.var_output.get().strip()

        if not input_path:
            messagebox.showwarning("提示", "请选择输入文件或文件夹")
            return
        if not os.path.exists(input_path):
            messagebox.showerror("错误", "输入路径不存在")
            return
        if not output_dir:
            messagebox.showwarning("提示", "请选择输出目录")
            return

        orientation = self.var_orientation.get()
        mode = self.var_mode.get()
        count = self.var_count.get()
        pixels_str = self.var_pixels.get().strip()
        append_remainder = self.var_append_remainder.get()
        clip_excess = self.var_clip_excess.get()
        out_ext = self.var_ext.get() if self.var_ext.get().startswith(".") else f".{self.var_ext.get()}"
        zero_pad = max(1, self.var_zero_pad.get())

        pixels_list = []
        if mode == "pixels":
            try:
                pixels_list = parse_pixels(pixels_str)
            except Exception as e:
                messagebox.showerror("错误", f"像素列表不合法：{e}")
                return

        # 后台线程执行
        self.btn_start.configure(state="disabled")
        t = threading.Thread(
            target=self._run_task,
            args=(input_path, output_dir, orientation, mode, count, pixels_list, append_remainder, clip_excess, out_ext, zero_pad),
            daemon=True,
        )
        t.start()

    def _run_task(self, input_path, output_dir, orientation, mode, count, pixels_list, append_remainder, clip_excess, out_ext, zero_pad):
        try:
            ensure_dir(output_dir)
            tasks = list_image_tasks(input_path)
            if not tasks:
                self.log("未找到可处理的图片")
                return

            ok = 0
            for p in tasks:
                try:
                    num = process_one_image(
                        in_path=p,
                        out_dir=output_dir,
                        orientation=orientation,
                        mode=mode,
                        count=count,
                        pixels=pixels_list,
                        append_remainder=append_remainder,
                        clip_excess=clip_excess,
                        out_ext=out_ext,
                        zero_pad=zero_pad,
                    )
                    ok += 1
                    self.log(f"[OK] {os.path.basename(p)} -> 切出 {num} 片")
                except Exception as e:
                    self.log(f"[FAIL] {os.path.basename(p)}: {e}")
            self.log(f"完成。成功: {ok}/{len(tasks)} 输出目录: {output_dir}")
        except Exception as e:
            self.log("发生错误：\n" + "".join(traceback.format_exception(e)))
        finally:
            self.btn_start.configure(state="normal")

if __name__ == "__main__":
    app = SplitGUI()
    app.mainloop()