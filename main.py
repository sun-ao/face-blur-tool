import cv2
import numpy as np
from insightface.app import FaceAnalysis
import time
import os
import onnxruntime as ort
import tempfile
import random
import string
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, ttk, messagebox, scrolledtext
import threading
import shutil
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any, Union
import io

# 新增：用于处理Word和PDF的库
try:
    from docx import Document
    from docx.shared import Inches
    DOCX_SUPPORTED = True
except ImportError:
    DOCX_SUPPORTED = False

# 修正PDF依赖检查 - 现在正确检查PyMuPDF(fitz)而不是PyPDF2
try:
    import fitz  # PyMuPDF
    from PIL import Image as PILImage
    PDF_SUPPORTED = True
except ImportError:
    PDF_SUPPORTED = False

# 全局变量缓存预计算参数
g_precomputed: Dict[str, Any] = {
    "kernel_size": None,
    "blur_type": None,
    "feather_radius": None,
    "opacity": None,
    "feather_kernel": None,
    "mosaic_block_size": None
}

# 打码类型中英文映射
BLUR_TYPE_MAP: Dict[str, str] = {
    "圆形模糊": "circle",
    "椭圆形模糊": "ellipse",
    "矩形模糊": "rectangle",
    "马赛克": "mosaic",
    "像素化": "pixelate"
}
# 反向映射，用于初始值设置
REVERSE_BLUR_TYPE_MAP: Dict[str, str] = {v: k for k, v in BLUR_TYPE_MAP.items()}

# 新增：文件类型映射
FILE_TYPE_MAP: Dict[str, str] = {
    "视频文件": "video",
    "图片文件": "image",
    "Word文档": "word",
    "PDF文档": "pdf"
}

# 新增：文件类型对应的扩展名
FILE_EXTENSIONS: Dict[str, List[str]] = {
    "video": ["*.mp4", "*.avi", "*.mov", "*.mkv", "*.flv"],
    "image": ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.gif"],
    "word": ["*.docx"],
    "pdf": ["*.pdf"]
}

# 新增：超链接标签类
class HyperlinkLabel(tk.Label):
    def __init__(self, parent, text, url, *args, **kwargs):
        super().__init__(parent, text=text, fg="blue", cursor="hand2", *args, **kwargs)
        self.url = url
        self.bind("<Button-1>", self.open_url)
        self.bind("<Enter>", lambda e: self.config(fg="purple"))
        self.bind("<Leave>", lambda e: self.config(fg="blue"))

    def open_url(self, event):
        if sys.platform.startswith('win'):
            os.startfile(self.url)  # type: ignore
        elif sys.platform.startswith('darwin'):
            subprocess.run(['open', self.url])
        else:
            subprocess.run(['xdg-open', self.url])

def generate_random_suffix(length: int = 6) -> str:
    """生成随机字符串作为文件名后缀"""
    letters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(letters) for _ in range(length))

# 获取资源路径（兼容PyInstaller打包）
def get_resource_path(relative_path: str) -> str:
    """获取资源文件的绝对路径，兼容开发环境和打包后的EXE"""
    try:
        # PyInstaller打包后会创建临时文件夹，并设置_MEIPASS2变量
        base_path = sys._MEIPASS  # type: ignore
    except Exception:
        # 开发环境下使用当前文件所在目录
        if '__file__' in globals():
            base_path = os.path.dirname(os.path.abspath(__file__))
        else:
            # 如果__file__未定义，使用当前工作目录
            base_path = os.getcwd()
    
    return os.path.join(base_path, relative_path)

class FaceBlurApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("人脸打码工具")
        self.root.geometry("950x850")
        self.root.resizable(True, True)
        
        # 设置中文字体支持
        self.style = ttk.Style()
        self.style.configure("TLabel", font=("SimHei", 10))
        self.style.configure("TButton", font=("SimHei", 10))
        self.style.configure("TCombobox", font=("SimHei", 10))
        
        # 资源路径初始化
        self.insightface_dir = get_resource_path(".insightface")
        self.ffmpeg_path = get_resource_path(os.path.join("ffmpeg", "ffmpeg.exe"))
        
        # 验证资源是否存在
        self.validate_resources()
        
        # 变量初始化 - 使用中文作为显示值
        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.whitelist_dir = tk.StringVar()
        self.blur_type = tk.StringVar(value=REVERSE_BLUR_TYPE_MAP["circle"])  # 默认圆形模糊
        self.similarity_threshold = tk.DoubleVar(value=0.5)
        self.blur_strength = tk.IntVar(value=50)
        self.feather_radius = tk.IntVar(value=8)
        self.opacity = tk.DoubleVar(value=0.95)
        self.start_time = tk.DoubleVar(value=0)
        self.duration = tk.DoubleVar(value=0)
        self.mosaic_block_size = tk.IntVar(value=15)
        # 新增：文件类型选择
        self.file_type = tk.StringVar(value="视频文件")
        
        # 用于直接输入的变量
        self.similarity_threshold_str = tk.StringVar(value="0.5")
        self.blur_strength_str = tk.StringVar(value="50")
        self.feather_radius_str = tk.StringVar(value="8")
        self.opacity_str = tk.StringVar(value="0.95")
        self.start_time_str = tk.StringVar(value="0")
        self.duration_str = tk.StringVar(value="0")
        self.mosaic_block_size_str = tk.StringVar(value="15")
        
        # 绑定变量更新事件
        self.bind_variable_updates()
        
        self.processing = False
        self.process_thread: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()
        
        self.create_widgets()
        self.initialize_log_messages()  # 初始化日志信息
    
    def bind_variable_updates(self):
        """绑定变量更新事件，实现滑块和输入框的双向同步"""
        # 相似度阈值
        def update_similarity_from_scale(value):
            self.similarity_threshold_str.set(f"{float(value):.2f}")
        
        def update_similarity_from_entry(*args):
            try:
                value = float(self.similarity_threshold_str.get())
                if 0.1 <= value <= 0.9:
                    self.similarity_threshold.set(value)
            except:
                pass
        
        self.similarity_threshold.trace_add("write", lambda *args: update_similarity_from_scale(self.similarity_threshold.get()))
        self.similarity_threshold_str.trace_add("write", update_similarity_from_entry)
        
        # 模糊强度
        def update_blur_from_scale(value):
            self.blur_strength_str.set(str(int(float(value))))
        
        def update_blur_from_entry(*args):
            try:
                value = int(self.blur_strength_str.get())
                if 5 <= value <= 100:
                    self.blur_strength.set(value)
            except:
                pass
        
        self.blur_strength.trace_add("write", lambda *args: update_blur_from_scale(self.blur_strength.get()))
        self.blur_strength_str.trace_add("write", update_blur_from_entry)
        
        # 马赛克块大小
        def update_mosaic_from_scale(value):
            self.mosaic_block_size_str.set(str(int(float(value))))
        
        def update_mosaic_from_entry(*args):
            try:
                value = int(self.mosaic_block_size_str.get())
                if 5 <= value <= 50:
                    self.mosaic_block_size.set(value)
            except:
                pass
        
        self.mosaic_block_size.trace_add("write", lambda *args: update_mosaic_from_scale(self.mosaic_block_size.get()))
        self.mosaic_block_size_str.trace_add("write", update_mosaic_from_entry)
        
        # 羽化半径
        def update_feather_from_scale(value):
            self.feather_radius_str.set(str(int(float(value))))
        
        def update_feather_from_entry(*args):
            try:
                value = int(self.feather_radius_str.get())
                if 0 <= value <= 20:
                    self.feather_radius.set(value)
            except:
                pass
        
        self.feather_radius.trace_add("write", lambda *args: update_feather_from_scale(self.feather_radius.get()))
        self.feather_radius_str.trace_add("write", update_feather_from_entry)
        
        # 不透明度
        def update_opacity_from_scale(value):
            self.opacity_str.set(f"{float(value):.2f}")
        
        def update_opacity_from_entry(*args):
            try:
                value = float(self.opacity_str.get())
                if 0.1 <= value <= 1.0:
                    self.opacity.set(value)
            except:
                pass
        
        self.opacity.trace_add("write", lambda *args: update_opacity_from_scale(self.opacity.get()))
        self.opacity_str.trace_add("write", update_opacity_from_entry)
        
        # 开始时间
        def update_start_from_entry(*args):
            try:
                value = float(self.start_time_str.get())
                if value >= 0:
                    self.start_time.set(value)
            except:
                pass
        
        def update_start_from_var(*args):
            self.start_time_str.set(f"{self.start_time.get():.1f}")
        
        self.start_time.trace_add("write", update_start_from_var)
        self.start_time_str.trace_add("write", update_start_from_entry)
        
        # 持续时间
        def update_duration_from_entry(*args):
            try:
                value = float(self.duration_str.get())
                if value >= 0:
                    self.duration.set(value)
            except:
                pass
        
        def update_duration_from_var(*args):
            self.duration_str.set(f"{self.duration.get():.1f}")
        
        self.duration.trace_add("write", update_duration_from_var)
        self.duration_str.trace_add("write", update_duration_from_entry)
        
        # 新增：文件类型变更时的处理
        def on_file_type_change(*args):
            # 清空输入和输出文件路径
            self.input_path.set("")
            self.output_path.set("")
            
            current_type = FILE_TYPE_MAP[self.file_type.get()]
            # 视频特有选项的显示控制
            if current_type == "video":
                # 显示时间设置控件，放在同一行
                self.time_frame.grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=5)
            else:
                # 隐藏时间设置控件
                self.time_frame.grid_remove()
        
        self.file_type.trace_add("write", on_file_type_change)
        
        # 新增：输入文件变更时自动生成输出文件默认值
        def on_input_path_change(*args):
            input_path = self.input_path.get()
            if input_path:
                # 无论输出路径是否已存在，都根据新的输入路径生成新的输出路径
                dirname, basename = os.path.split(input_path)
                name, ext = os.path.splitext(basename)
                output_filename = os.path.join(dirname, f"{name}_blurred{ext}")
                self.output_path.set(output_filename)
        
        self.input_path.trace_add("write", on_input_path_change)
    
    def validate_resources(self) -> None:
        """验证必要的资源文件是否存在"""
        missing_resources: List[str] = []
        
        models_dir = os.path.join(self.insightface_dir, "models")
        # 检查模型目录
        if not os.path.exists(models_dir):
            missing_resources.append(f"模型目录不存在: {models_dir}")
        else:
            required_models = ["buffalo_l"]
            for model in required_models:
                if not os.path.exists(os.path.join(models_dir, model)):
                    missing_resources.append(f"缺少模型: {model}")
        
        # 检查FFmpeg（视频处理需要）
        if not os.path.exists(self.ffmpeg_path):
            missing_resources.append(f"FFmpeg不存在: {self.ffmpeg_path}")
        
        # 检查Word处理支持
        if not DOCX_SUPPORTED:
            missing_resources.append("未安装python-docx库，Word文档处理功能不可用")
        
        # 检查PDF处理支持（已修正为检查PyMuPDF）
        if not PDF_SUPPORTED:
            missing_resources.append("未安装pymupdf库，PDF文档处理功能不可用，请安装：pip install pymupdf")
        
        # 如果有缺失资源，显示错误
        if missing_resources:
            error_msg = "检测到以下问题，部分功能可能受限：\n" + "\n".join(missing_resources)
            error_msg += "\n\n可以继续使用其他可用功能。"
            messagebox.showwarning("资源检查警告", error_msg)
    
    def create_widgets(self) -> None:
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 输入输出设置
        io_frame = ttk.LabelFrame(main_frame, text="文件设置", padding="10")
        io_frame.pack(fill=tk.X, pady=5)
        
        # 新增：文件类型选择
        ttk.Label(io_frame, text="文件类型:").grid(row=0, column=0, sticky=tk.W, pady=5)
        file_type_combo = ttk.Combobox(io_frame, textvariable=self.file_type, state="readonly", width=15)
        file_type_combo['values'] = list(FILE_TYPE_MAP.keys())
        file_type_combo.grid(row=0, column=1, pady=5, padx=5, sticky=tk.W)
        
        ttk.Label(io_frame, text="输入文件:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(io_frame, textvariable=self.input_path, width=50).grid(row=1, column=1, pady=5, padx=5)
        ttk.Button(io_frame, text="浏览...", command=self.browse_input).grid(row=1, column=2, pady=5, padx=5)
        
        ttk.Label(io_frame, text="输出文件:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(io_frame, textvariable=self.output_path, width=50).grid(row=2, column=1, pady=5, padx=5)
        ttk.Button(io_frame, text="浏览...", command=self.browse_output).grid(row=2, column=2, pady=5, padx=5)
        
        # 时间设置控件（放在同一行）
        self.time_frame = ttk.Frame(io_frame)
        
        self.start_time_label = ttk.Label(self.time_frame, text="开始时间(秒):")
        self.start_time_entry = ttk.Entry(self.time_frame, textvariable=self.start_time_str, width=15)
        
        self.duration_label = ttk.Label(self.time_frame, text="处理时长(秒，0表示全部):")
        self.duration_entry = ttk.Entry(self.time_frame, textvariable=self.duration_str, width=15)
        
        # 布局时间控件在同一行
        self.start_time_label.pack(side=tk.LEFT, pady=5, padx=(0, 5))
        self.start_time_entry.pack(side=tk.LEFT, pady=5, padx=5)
        self.duration_label.pack(side=tk.LEFT, pady=5, padx=(20, 5))
        self.duration_entry.pack(side=tk.LEFT, pady=5, padx=5)
        
        # 白名单和相似度设置（单独的LabelFrame）
        whitelist_frame = ttk.LabelFrame(main_frame, text="人脸白名单设置", padding="10")
        whitelist_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(whitelist_frame, text="白名单目录:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(whitelist_frame, textvariable=self.whitelist_dir, width=50).grid(row=0, column=1, pady=5, padx=5)
        ttk.Button(whitelist_frame, text="浏览...", command=self.browse_whitelist).grid(row=0, column=2, pady=5, padx=5)
        
        ttk.Label(whitelist_frame, text="人脸相似度阈值:").grid(row=2, column=0, sticky=tk.W, pady=5)
        threshold_frame = ttk.Frame(whitelist_frame)
        threshold_frame.grid(row=2, column=1, sticky=tk.W, pady=5)
        # 缩短滑块长度
        ttk.Scale(threshold_frame, variable=self.similarity_threshold, from_=0.1, to=0.9, length=200).pack(side=tk.LEFT)
        ttk.Entry(threshold_frame, textvariable=self.similarity_threshold_str, width=8).pack(side=tk.LEFT, padx=5)
        ttk.Label(whitelist_frame, text="(0.1-0.9)").grid(row=2, column=2, sticky=tk.W, pady=5)
        
        # 打码设置 - 左右布局，中间添加垂直分割线
        effect_frame = ttk.LabelFrame(main_frame, text="打码设置", padding="10")
        effect_frame.pack(fill=tk.X, pady=5)
        
        # 左右布局容器
        effect_inner_frame = ttk.Frame(effect_frame)
        effect_inner_frame.pack(fill=tk.X, expand=True)
        
        # 左侧部分
        left_effect_frame = ttk.Frame(effect_inner_frame)
        left_effect_frame.pack(side=tk.LEFT, padx=(10, 20), fill=tk.X, expand=True)
        
        ttk.Label(left_effect_frame, text="打码类型:").grid(row=0, column=0, sticky=tk.W, pady=8)
        blur_type_combo = ttk.Combobox(left_effect_frame, textvariable=self.blur_type, state="readonly", width=15)
        blur_type_combo['values'] = list(BLUR_TYPE_MAP.keys())
        blur_type_combo.grid(row=0, column=1, pady=8, padx=5, sticky=tk.W)
        
        ttk.Label(left_effect_frame, text="马赛克块大小:").grid(row=2, column=0, sticky=tk.W, pady=8)
        mosaic_frame = ttk.Frame(left_effect_frame)
        mosaic_frame.grid(row=2, column=1, sticky=tk.W, pady=8)
        # 缩短滑块长度
        ttk.Scale(mosaic_frame, variable=self.mosaic_block_size, from_=5, to=50, length=180).pack(side=tk.LEFT)
        ttk.Entry(mosaic_frame, textvariable=self.mosaic_block_size_str, width=8).pack(side=tk.LEFT, padx=5)
        ttk.Label(left_effect_frame, text="(5-50)").grid(row=2, column=2, sticky=tk.W, pady=8)
        
        # 垂直分割线
        ttk.Separator(effect_inner_frame, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # 右侧部分
        right_effect_frame = ttk.Frame(effect_inner_frame)
        right_effect_frame.pack(side=tk.RIGHT, padx=(20, 10), fill=tk.X, expand=True)
        
        ttk.Label(right_effect_frame, text="模糊强度:").grid(row=0, column=0, sticky=tk.W, pady=8)
        blur_frame = ttk.Frame(right_effect_frame)
        blur_frame.grid(row=0, column=1, sticky=tk.W, pady=8)
        # 缩短滑块长度
        ttk.Scale(blur_frame, variable=self.blur_strength, from_=5, to=100, length=180).pack(side=tk.LEFT)
        ttk.Entry(blur_frame, textvariable=self.blur_strength_str, width=8).pack(side=tk.LEFT, padx=5)
        ttk.Label(right_effect_frame, text="(5-100)").grid(row=0, column=2, sticky=tk.W, pady=8)
        
        ttk.Label(right_effect_frame, text="羽化半径:").grid(row=2, column=0, sticky=tk.W, pady=8)
        feather_frame = ttk.Frame(right_effect_frame)
        feather_frame.grid(row=2, column=1, sticky=tk.W, pady=8)
        # 缩短滑块长度
        ttk.Scale(feather_frame, variable=self.feather_radius, from_=0, to=20, length=180).pack(side=tk.LEFT)
        ttk.Entry(feather_frame, textvariable=self.feather_radius_str, width=8).pack(side=tk.LEFT, padx=5)
        ttk.Label(right_effect_frame, text="(0-20)").grid(row=2, column=2, sticky=tk.W, pady=8)
        
        ttk.Label(right_effect_frame, text="不透明度:").grid(row=4, column=0, sticky=tk.W, pady=8)
        opacity_frame = ttk.Frame(right_effect_frame)
        opacity_frame.grid(row=4, column=1, sticky=tk.W, pady=8)
        # 缩短滑块长度
        ttk.Scale(opacity_frame, variable=self.opacity, from_=0.1, to=1.0, length=180).pack(side=tk.LEFT)
        ttk.Entry(opacity_frame, textvariable=self.opacity_str, width=8).pack(side=tk.LEFT, padx=5)
        ttk.Label(right_effect_frame, text="(0.1-1.0)").grid(row=4, column=2, sticky=tk.W, pady=8)
        
        # 进度和日志区域
        log_frame = ttk.LabelFrame(main_frame, text="处理日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=8)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state=tk.DISABLED)
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        # 按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        self.process_btn = ttk.Button(btn_frame, text="开始处理", command=self.start_processing)
        self.process_btn.pack(side=tk.LEFT, padx=5)
        
        self.cancel_btn = ttk.Button(btn_frame, text="取消", command=self.cancel_processing, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="退出", command=self.root.quit).pack(side=tk.RIGHT, padx=5)
        
        # 初始显示控制
        self.on_file_type_change()
    
    def initialize_log_messages(self):
        """初始化日志框中的提示信息"""
        self.log("📋 欢迎使用人脸打码工具！")
        self.log("")
        self.log("⚠️ 重要提示：")
        self.log("1. 白名单功能：请指定一个存放人脸头像截图的文件夹，工具将自动识别并保留这些人脸不打码")
        self.log("2. GPU加速配置：")
        self.log("   - 需要安装onnxruntime-gpu而非普通的onnxruntime")
        
        # 添加可点击的下载链接
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, "   - 需要安装与GPU匹配的 ")
        
        # 创建CUDA下载链接
        cuda_link = HyperlinkLabel(self.log_text, text="CUDA 12.9.1", 
                                 url="https://developer.nvidia.com/cuda-12-9-1-download-archive")
        self.log_text.window_create(tk.END, window=cuda_link)
        
        self.log_text.insert(tk.END, " 和 ")
        
        # 创建cuDNN下载链接
        cudnn_link = HyperlinkLabel(self.log_text, text="cuDNN 9.11.0", 
                                  url="https://developer.nvidia.com/cudnn-9-11-0-download-archive")
        self.log_text.window_create(tk.END, window=cudnn_link)
        
        self.log_text.insert(tk.END, " 工具包\n")
        self.log_text.config(state=tk.DISABLED)
        
        self.log("   - 配置完成后，工具会自动检测并使用GPU加速")
        self.log("3. 支持的文件类型：视频、图片、Word文档和PDF文档")
        self.log("")
        self.log("请选择文件类型并设置相关参数开始处理...")
    
    def on_file_type_change(self):
        """文件类型变更时的处理"""
        current_type = FILE_TYPE_MAP[self.file_type.get()]
        if current_type == "video":
            # 显示时间设置控件，放在输入文件下方的同一行
            self.time_frame.grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=5)
        else:
            # 隐藏时间设置控件
            self.time_frame.grid_remove()
    
    def browse_input(self) -> None:
        file_type = FILE_TYPE_MAP[self.file_type.get()]
        file_extensions = FILE_EXTENSIONS.get(file_type, ["*.*"])
        
        filetypes = [(f"{self.file_type.get()}", ";".join(file_extensions))]
        
        filename = filedialog.askopenfilename(
            filetypes=filetypes
        )
        if filename:
            self.input_path.set(filename)
            # 自动设置输出路径
            if not self.output_path.get():
                dirname, basename = os.path.split(filename)
                name, ext = os.path.splitext(basename)
                output_filename = os.path.join(dirname, f"{name}_blurred{ext}")
                self.output_path.set(output_filename)
    
    def browse_output(self) -> None:
        file_type = FILE_TYPE_MAP[self.file_type.get()]
        file_extensions = FILE_EXTENSIONS.get(file_type, ["*.*"])
        
        # 获取默认扩展名
        default_ext = file_extensions[0][1:] if file_extensions else "*.*"
        
        filename = filedialog.asksaveasfilename(
            defaultextension=default_ext,
            filetypes=[(f"{self.file_type.get()}", ";".join(file_extensions))]
        )
        if filename:
            self.output_path.set(filename)
    
    def browse_whitelist(self) -> None:
        directory = filedialog.askdirectory()
        if directory:
            self.whitelist_dir.set(directory)
    
    def log(self, message: str) -> None:
        """向日志区域添加消息"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.update_idletasks()
    
    def update_progress(self, value: float) -> None:
        """更新进度条"""
        self.progress_var.set(value)
        self.root.update_idletasks()
    
    def handle_existing_output_file(self, output_path: str) -> Optional[str]:
        """处理已存在的输出文件，返回新的路径或None表示取消"""
        if not os.path.exists(output_path):
            return output_path
            
        # 创建自定义对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("文件已存在")
        dialog.geometry("350x150")
        dialog.resizable(False, False)
        dialog.transient(self.root)  # 设置为主窗口的子窗口
        dialog.grab_set()  # 模态窗口，阻止操作主窗口
        
        # 居中显示
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (self.root.winfo_width() // 2) - (width // 2) + self.root.winfo_x()
        y = (self.root.winfo_height() // 2) - (height // 2) + self.root.winfo_y()
        dialog.geometry(f"+{x}+{y}")
        
        # 提示信息
        ttk.Label(dialog, text=f"文件 '{os.path.basename(output_path)}' 已存在。", 
                 font=("SimHei", 10)).pack(pady=10, padx=10)
        
        # 按钮框架
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        # 结果变量
        result = tk.StringVar(value="cancel")
        
        # 取消按钮
        def on_cancel():
            result.set("cancel")
            dialog.destroy()
        
        # 重命名按钮
        def on_rename():
            result.set("rename")
            dialog.destroy()
        
        # 覆盖按钮
        def on_overwrite():
            result.set("overwrite")
            dialog.destroy()
        
        ttk.Button(btn_frame, text="取消操作", command=on_cancel).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="随机重命名", command=on_rename).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="覆盖", command=on_overwrite).pack(side=tk.LEFT, padx=5)
        
        # 等待对话框关闭
        self.root.wait_window(dialog)
        
        if result.get() == "cancel":
            return None
        elif result.get() == "overwrite":
            return output_path
        
        # 生成新的文件名
        dirname, basename = os.path.split(output_path)
        name, ext = os.path.splitext(basename)
        random_suffix = generate_random_suffix()
        new_name = f"{name}_{random_suffix}{ext}"
        new_path = os.path.join(dirname, new_name)
        
        self.log(f"输出文件已存在，自动重命名为: {new_name}")
        return new_path
    
    def start_processing(self) -> None:
        """开始处理文件"""
        # 验证输入
        if not self.input_path.get():
            messagebox.showerror("错误", "请选择输入文件")
            return
        
        output_path = self.output_path.get()
        if not output_path:
            messagebox.showerror("错误", "请选择输出文件路径")
            return
        
        # 检查文件类型支持
        file_type = FILE_TYPE_MAP[self.file_type.get()]
        if file_type == "word" and not DOCX_SUPPORTED:
            messagebox.showerror("错误", "Word文档处理需要python-docx库，请先安装：\npip install python-docx")
            return
        
        if file_type == "pdf" and not PDF_SUPPORTED:
            messagebox.showerror("错误", "PDF文档处理需要pymupdf库，请先安装：\npip install pymupdf")
            return
        
        # 处理已存在的输出文件
        new_output_path = self.handle_existing_output_file(output_path)
        if new_output_path is None:  # 用户选择取消
            return
        if new_output_path != output_path:  # 文件名已更改
            self.output_path.set(new_output_path)
            output_path = new_output_path
        
        # 检查输入输出是否相同
        if os.path.abspath(self.input_path.get()) == os.path.abspath(output_path):
            if not messagebox.askyesno("警告", "输入和输出文件相同，这将覆盖原文件。是否继续？"):
                return
        
        # 禁用按钮
        self.process_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.processing = True
        self.cancel_event.clear()
        
        # 在新线程中处理，避免UI冻结
        self.process_thread = threading.Thread(target=self.process_file)
        self.process_thread.start()
    
    def cancel_processing(self) -> None:
        """取消处理"""
        if messagebox.askyesno("确认", "确定要取消处理吗？"):
            self.cancel_event.set()
            self.log("正在取消处理...")
            self.cancel_btn.config(state=tk.DISABLED)
    
    def process_file(self) -> None:
        """处理文件的实际函数"""
        try:
            # 获取参数，将中文打码类型转换为英文
            input_path = self.input_path.get()
            output_path = self.output_path.get()
            whitelist_dir = self.whitelist_dir.get() if self.whitelist_dir.get() else None
            file_type = FILE_TYPE_MAP[self.file_type.get()]
            
            # 根据文件类型调用不同的处理函数
            self.log(f"开始处理{self.file_type.get()}: {input_path}")
            self.log(f"输出路径: {output_path}")
            
            success = False
            blur_type = BLUR_TYPE_MAP[self.blur_type.get()]  # 转换为英文值
            
            # 初始化FaceAnalysis模型
            self.app = self.initialize_face_analysis()
            if not self.app:
                raise Exception("无法初始化人脸检测模型")
            
            # 加载白名单
            self.whitelist_data, self.threshold = self.load_whitelist_faces(
                self.app, whitelist_dir, self.similarity_threshold.get())
            
            # 预计算图像处理参数
            self.precompute_image_processing_params(
                blur_type, self.blur_strength.get(), 
                self.feather_radius.get(), self.opacity.get(), 
                self.mosaic_block_size.get())
            
            # 根据文件类型处理
            if file_type == "video":
                start_time = self.start_time.get()
                duration = self.duration.get() if self.duration.get() > 0 else None
                success = self.blur_faces_in_video(
                    input_path=input_path,
                    output_path=output_path,
                    start_time=start_time,
                    duration=duration
                )
            elif file_type == "image":
                success = self.blur_faces_in_image(
                    input_path=input_path,
                    output_path=output_path
                )
            elif file_type == "word":
                success = self.blur_faces_in_word(
                    input_path=input_path,
                    output_path=output_path
                )
            elif file_type == "pdf":
                success = self.blur_faces_in_pdf(
                    input_path=input_path,
                    output_path=output_path
                )
            
            if success and not self.cancel_event.is_set():
                self.log("处理完成！")
                self.update_progress(100)
                messagebox.showinfo("成功", f"{self.file_type.get()}处理完成，已保存至:\n{output_path}")
                # 添加打开文件按钮功能
                if messagebox.askyesno("完成", "是否打开输出文件？"):
                    self.open_output_file(output_path)
            elif self.cancel_event.is_set():
                self.log("处理已取消")
            else:
                self.log("处理失败")
                messagebox.showerror("失败", f"{self.file_type.get()}处理过程中发生错误")
                
        except Exception as e:
            self.log(f"处理错误: {str(e)}")
            messagebox.showerror("错误", f"处理过程中发生错误:\n{str(e)}")
        finally:
            # 恢复UI状态
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)
            self.cancel_btn.config(state=tk.DISABLED)
            self.update_progress(0)
    
    def open_output_file(self, file_path: str) -> None:
        """打开输出文件"""
        try:
            if sys.platform.startswith('win'):
                os.startfile(file_path)  # type: ignore
            elif sys.platform.startswith('darwin'):
                subprocess.run(['open', file_path])
            else:
                subprocess.run(['xdg-open', file_path])
        except Exception as e:
            self.log(f"无法打开文件: {str(e)}")
    
    def initialize_face_analysis(self) -> Optional[FaceAnalysis]:
        """初始化人脸分析模型"""
        try:
            # GPU检查与模型初始化
            gpu_available = self.check_gpu_availability()
            providers = ['CUDAExecutionProvider'] if gpu_available else ['CPUExecutionProvider']
            self.log(f"使用提供者: {providers}")
            
            # 初始化FaceAnalysis，使用本地模型
            app = FaceAnalysis(providers=providers, name='buffalo_l', root=self.insightface_dir)
            app.prepare(ctx_id=0, det_size=(640, 640))
            return app
        except Exception as e:
            self.log(f"初始化buffalo_l模型失败: {str(e)}")
            return None
    
    def check_gpu_availability(self) -> bool:
        """检查系统是否支持GPU加速"""
        self.log("检查ONNX Runtime可用提供者...")
        available_providers = ort.get_available_providers()
        self.log(f"可用提供者: {available_providers}")
        
        if 'CUDAExecutionProvider' in available_providers:
            self.log("✅ CUDA加速可用")
            return True
        else:
            self.log("⚠️ CUDA加速不可用，将使用CPU")
            self.log("提示: 请确保安装了onnxruntime-gpu和兼容的CUDA/cuDNN")
            return False
    
    def load_whitelist_faces(self, app: FaceAnalysis, whitelist_dir: Optional[str], 
                            similarity_threshold: float = 0.5) -> Tuple[Optional[Dict[str, Any]], float]:
        """加载人脸白名单并返回特征向量矩阵"""
        whitelist_features: List[Dict[str, Any]] = []
        if whitelist_dir and os.path.exists(whitelist_dir):
            self.log(f"正在加载人脸白名单，目录: {whitelist_dir}")
            valid_files = [f for f in os.listdir(whitelist_dir) 
                          if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            
            for filename in valid_files:
                img_path = os.path.join(whitelist_dir, filename)
                try:
                    img = cv2.imread(img_path)
                    if img is None:
                        self.log(f"错误: 无法读取图片 {filename}")
                        continue
                        
                    faces = app.get(img)
                    if faces:
                        whitelist_features.append({
                            'feature': faces[0].normed_embedding,
                            'filename': filename
                        })
                        self.log(f"已加载白名单人脸: {filename}")
                    else:
                        self.log(f"警告: 在白名单图片 {filename} 中未检测到人脸")
                except Exception as e:
                    self.log(f"错误: 无法加载白名单图片 {filename}: {str(e)}")
        
        if not whitelist_features:
            self.log("警告: 未加载到任何白名单人脸，所有检测到的人脸都将被打码")
            return None, similarity_threshold
        
        # 转换为特征矩阵（n_features × embedding_dim），加速批量计算
        feature_matrix = np.array([item['feature'] for item in whitelist_features])
        return {
            'matrix': feature_matrix,
            'entries': whitelist_features
        }, similarity_threshold
    
    def precompute_image_processing_params(self, blur_type: str, blur_strength: int, 
                                         feather_radius: int, opacity: float, 
                                         mosaic_block_size: int) -> None:
        """预计算图像处理参数，避免循环内重复计算"""
        # 计算高斯模糊核
        kernel_size = int(blur_strength // 2 * 2 + 1)
        kernel_size = max(kernel_size, 3)
        
        # 存储预计算参数到全局变量
        g_precomputed.update({
            "kernel_size": kernel_size,
            "blur_type": blur_type,
            "feather_radius": feather_radius,
            "opacity": opacity,
            "mosaic_block_size": mosaic_block_size,
            # 预计算羽化核（如果需要）
            "feather_kernel": (feather_radius*2+1, feather_radius*2+1) if feather_radius > 0 else None
        })
    
    def apply_mosaic(self, face_region: np.ndarray, block_size: int) -> np.ndarray:
        """应用马赛克效果"""
        height, width = face_region.shape[:2]
        
        # 缩小图像
        small = cv2.resize(face_region, (width // block_size, height // block_size), interpolation=cv2.INTER_LINEAR)
        
        # 放大回原尺寸
        mosaic = cv2.resize(small, (width, height), interpolation=cv2.INTER_NEAREST)
        return mosaic
    
    def apply_pixelate(self, face_region: np.ndarray, block_size: int) -> np.ndarray:
        """应用像素化效果（比马赛克更规则）"""
        height, width = face_region.shape[:2]
        
        # 遍历每个块并应用平均颜色
        for y in range(0, height, block_size):
            for x in range(0, width, block_size):
                y_end = min(y + block_size, height)
                x_end = min(x + block_size, width)
                
                # 获取块区域
                block = face_region[y:y_end, x:x_end]
                
                # 计算块的平均颜色
                avg_color = block.mean(axis=0).mean(axis=0)
                
                # 用平均颜色填充块
                face_region[y:y_end, x:x_end] = avg_color
        
        return face_region
    
    def process_single_face(self, frame: np.ndarray, face: Any) -> np.ndarray:
        """处理单个人脸的打码逻辑"""
        # 检查是否在白名单中
        is_whitelisted = False
        if self.whitelist_data:
            # 批量计算当前人脸与所有白名单人脸的相似度
            similarities = np.dot(self.whitelist_data['matrix'], face.normed_embedding)
            if np.any(similarities > self.threshold):
                is_whitelisted = True
        
        if is_whitelisted:
            return frame  # 白名单人脸不处理
        
        # 人脸边界框处理
        bbox = face.bbox.astype(int)
        x1, y1, x2, y2 = bbox
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
        
        # 提取人脸区域
        face_region = frame[y1:y2, x1:x2]
        region_height, region_width = face_region.shape[:2]
        if region_height == 0 or region_width == 0:
            return frame
        
        # 1. 创建打码区域掩码
        mask = np.zeros((region_height, region_width, 3), dtype=np.uint8)
        if g_precomputed["blur_type"] in ['circle', 'mosaic', 'pixelate']:
            center = (region_width // 2, region_height // 2)
            radius = int(max(region_width, region_height) * 0.45)
            cv2.circle(mask, center, radius, (255, 255, 255), -1)
        elif g_precomputed["blur_type"] == 'ellipse':
            center = (region_width // 2, region_height // 2)
            axes = (int(region_width * 0.45), int(region_height * 0.45))
            cv2.ellipse(mask, center, axes, 0, 0, 360, (255, 255, 255), -1)
        else:  # rectangle
            cv2.rectangle(mask, (0, 0), (region_width, region_height), (255, 255, 255), -1)
        
        # 2. 羽化处理
        if g_precomputed["feather_radius"] > 0:
            gray_mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
            blurred_mask = cv2.GaussianBlur(gray_mask, g_precomputed["feather_kernel"], 0)
            mask = cv2.cvtColor(blurred_mask, cv2.COLOR_GRAY2BGR) / 255.0  # 归一化
        else:
            mask = mask / 255.0
        
        # 3. 应用打码效果
        if g_precomputed["blur_type"] == 'mosaic':
            processed_face = self.apply_mosaic(face_region.copy(), g_precomputed["mosaic_block_size"])
        elif g_precomputed["blur_type"] == 'pixelate':
            processed_face = self.apply_pixelate(face_region.copy(), g_precomputed["mosaic_block_size"])
        else:  # 模糊效果
            processed_face = cv2.GaussianBlur(face_region, 
                                           (g_precomputed["kernel_size"], g_precomputed["kernel_size"]), 
                                           g_precomputed["kernel_size"] // 2)
        
        # 4. 混合处理
        opacity = g_precomputed["opacity"]
        if opacity < 1.0:
            face_region[:] = (face_region * (1 - mask) + 
                             (processed_face * opacity + face_region * (1 - opacity)) * mask).astype(np.uint8)
        else:
            face_region[:] = (face_region * (1 - mask) + processed_face * mask).astype(np.uint8)
        
        return frame
    
    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, int]:
        """处理单帧图像，增加错误处理"""
        if self.cancel_event.is_set():
            return frame, 0
            
        # 检查帧是否有效
        if frame is None:
            self.log("错误: 接收到空帧")
            return np.array([]), 0
            
        if not isinstance(frame, np.ndarray):
            self.log(f"错误: 帧不是有效的numpy数组，类型为{type(frame)}")
            return np.array([]), 0
            
        if len(frame.shape) != 3:
            self.log(f"错误: 帧形状不正确，应为3维，实际为{frame.shape}")
            return np.array([]), 0
        
        try:
            faces = self.app.get(frame)
            for face in faces:
                frame = self.process_single_face(frame, face)
            return frame, len(faces)
        except Exception as e:
            self.log(f"处理帧时出错: {str(e)}")
            # 返回原始帧以继续处理流程
            return frame, 0
    
    # 图片处理函数
    def blur_faces_in_image(self, input_path: str, output_path: str) -> bool:
        """对图片中的人脸进行打码处理"""
        try:
            # 读取图片
            img = cv2.imread(input_path)
            if img is None:
                raise Exception(f"无法读取图片: {input_path}")
            
            self.log(f"处理图片: {os.path.basename(input_path)}")
            self.log(f"图片尺寸: {img.shape[1]}x{img.shape[0]}")
            
            # 处理人脸
            processed_img, face_count = self.process_frame(img)
            self.log(f"检测到 {face_count} 个人脸")
            
            # 保存处理后的图片
            success = cv2.imwrite(output_path, processed_img)
            if not success:
                raise Exception(f"无法保存处理后的图片到: {output_path}")
                
            return True
        except Exception as e:
            self.log(f"图片处理错误: {str(e)}")
            return False
    
    # Word文档处理函数
    def blur_faces_in_word(self, input_path: str, output_path: str) -> bool:
        """对Word文档中的图片人脸进行打码处理"""
        if not DOCX_SUPPORTED:
            self.log("错误: Word文档处理需要python-docx库")
            return False
            
        try:
            # 加载Word文档
            doc = Document(input_path)
            self.log(f"加载Word文档: {os.path.basename(input_path)}")
            
            # 创建临时目录存储处理后的图片
            with tempfile.TemporaryDirectory() as temp_dir:
                image_count = 0
                modified_count = 0
                processed_images = []  # 存储处理后的图片信息
                
                # 提取文档中的所有图片
                self.log("从Word文档中提取图片...")
                for rel in doc.part.rels.values():
                    if "image" in rel.target_ref:
                        image_count += 1
                        # 获取图片数据和扩展名
                        img_data = rel.target_part._blob
                        content_type = rel.target_part.content_type
                        img_ext = content_type.split('/')[-1].lower()
                        if img_ext == 'jpeg':
                            img_ext = 'jpg'
                        if img_ext not in ['png', 'jpg', 'jpeg', 'gif', 'bmp']:
                            img_ext = 'png'
                            
                        # 保存原始图片到临时文件
                        temp_img_path = os.path.join(temp_dir, f"img_{image_count}.{img_ext}")
                        with open(temp_img_path, 'wb') as f:
                            f.write(img_data)
                            
                        # 处理图片
                        img = cv2.imread(temp_img_path)
                        if img is not None:
                            processed_img, face_count = self.process_frame(img)
                            
                            # 保存处理后的图片
                            processed_img_path = os.path.join(temp_dir, f"processed_img_{image_count}.{img_ext}")
                            cv2.imwrite(processed_img_path, processed_img)
                            
                            # 记录需要替换的图片信息
                            processed_images.append({
                                'rel_id': rel.rId,
                                'processed_path': processed_img_path,
                                'face_count': face_count
                            })
                            
                            if face_count > 0:
                                modified_count += 1
                                self.log(f"处理图片 {image_count}，检测到 {face_count} 个人脸")
                            else:
                                self.log(f"处理图片 {image_count}，未检测到人脸")
                        else:
                            self.log(f"警告: 无法读取图片 {image_count}，将使用原始图片")
                            processed_images.append({
                                'rel_id': rel.rId,
                                'processed_path': temp_img_path,
                                'face_count': 0
                            })
                
                # 替换文档中的图片 - 将此操作移至with块内部
                self.log("替换Word文档中的图片...")
                for img_info in processed_images:
                    # 检查文件是否存在
                    if not os.path.exists(img_info['processed_path']):
                        self.log(f"警告: 处理后的图片不存在 {img_info['processed_path']}")
                        continue
                        
                    rel = doc.part.rels[img_info['rel_id']]
                    # 读取处理后的图片
                    with open(img_info['processed_path'], 'rb') as f:
                        processed_blob = f.read()
                    # 直接替换图片二进制数据
                    rel.target_part._blob = processed_blob
            
            self.log(f"共处理 {image_count} 张图片，其中 {modified_count} 张包含人脸并已打码")
            
            # 保存处理后的文档
            doc.save(output_path)
            return True
            
        except Exception as e:
            self.log(f"Word文档处理错误: {str(e)}")
            return False
    
    # PDF文档处理函数
    def blur_faces_in_pdf(self, input_path: str, output_path: str) -> bool:
        """对PDF文档中的图片人脸进行打码处理，使用PyMuPDF库，不依赖Poppler"""
        try:
            import fitz  # 确保导入PyMuPDF库
        except ImportError:
            self.log("错误: PDF文档处理需要pymupdf库，请安装: pip install pymupdf")
            return False
            
        try:
            # 加载PDF文档
            pdf_document = fitz.open(input_path)
            page_count = len(pdf_document)
            self.log(f"加载PDF文档: {os.path.basename(input_path)}，共 {page_count} 页")
            
            # 创建临时目录存储处理后的图片
            with tempfile.TemporaryDirectory() as temp_dir:
                image_count = 0
                modified_count = 0
                processed_images = []  # 存储处理后的图片信息
                
                # 提取文档中的所有图片
                self.log("从PDF文档中提取图片...")
                for page_num in range(page_count):
                    page = pdf_document[page_num]
                    images = page.get_images(full=True)
                    
                    for img_index, img in enumerate(images):
                        image_count += 1
                        xref = img[0]
                        
                        # 提取图片数据
                        base_image = pdf_document.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        
                        # 保存原始图片到临时文件
                        temp_img_path = os.path.join(temp_dir, f"page_{page_num}_img_{img_index}.{image_ext}")
                        with open(temp_img_path, "wb") as f:
                            f.write(image_bytes)
                            
                        # 获取图片在页面中的位置
                        img_rects = page.get_image_rects(xref)
                        img_rect = img_rects[0] if img_rects else None
                        
                        # 处理图片
                        img = cv2.imread(temp_img_path)
                        if img is not None:
                            processed_img, face_count = self.process_frame(img)
                            
                            # 保存处理后的图片
                            processed_img_path = os.path.join(temp_dir, f"processed_page_{page_num}_img_{img_index}.{image_ext}")
                            cv2.imwrite(processed_img_path, processed_img)
                            
                            # 记录需要替换的图片信息
                            processed_images.append({
                                'xref': xref,
                                'page_num': page_num,
                                'rect': img_rect,
                                'ext': image_ext,
                                'processed_path': processed_img_path,
                                'face_count': face_count
                            })
                            
                            if face_count > 0:
                                modified_count += 1
                                self.log(f"处理图片 {image_count} (第{page_num+1}页)，检测到 {face_count} 个人脸")
                            else:
                                self.log(f"处理图片 {image_count} (第{page_num+1}页)，未检测到人脸")
                        else:
                            self.log(f"警告: 无法读取图片 {image_count} (第{page_num+1}页)，将使用原始图片")
                            processed_images.append({
                                'xref': xref,
                                'page_num': page_num,
                                'rect': img_rect,
                                'ext': image_ext,
                                'processed_path': temp_img_path,
                                'face_count': 0
                            })
                
                # 关闭原始PDF文档
                pdf_document.close()
                
                # 创建新的PDF文档并替换图片
                self.log("替换PDF文档中的图片...")
                new_pdf = fitz.open()
                original_pdf = fitz.open(input_path)
                
                # 按页面分组处理后的图片
                page_image_map = {}
                for img in processed_images:
                    page_num = img['page_num']
                    if page_num not in page_image_map:
                        page_image_map[page_num] = []
                    page_image_map[page_num].append(img)
                
                # 处理每一页
                for page_num in range(page_count):
                    # 复制原始页面
                    original_page = original_pdf.load_page(page_num)
                    new_page = new_pdf.new_page(
                        width=original_page.rect.width,
                        height=original_page.rect.height
                    )
                    
                    # 将原始页面内容绘制到新页面
                    new_page.show_pdf_page(new_page.rect, original_pdf, page_num)
                    
                    # 如果当前页没有图片需要处理，继续下一页
                    if page_num not in page_image_map:
                        continue
                        
                    images = page_image_map[page_num]
                    
                    # 先覆盖原始图片
                    for img in images:
                        if img['rect']:
                            # 绘制白色矩形覆盖原始图片
                            new_page.draw_rect(
                                img['rect'], 
                                color=(1, 1, 1), 
                                fill=(1, 1, 1), 
                                width=0
                            )
                    
                    # 插入处理后的图片
                    for img in images:
                        if not img['rect']:
                            self.log(f"警告: 无法确定图片位置，跳过替换: {os.path.basename(img['processed_path'])}")
                            continue
                        
                        try:
                            # 插入处理后的图片
                            new_page.insert_image(
                                img['rect'],  # 图片位置和大小
                                filename=img['processed_path']  # 图片文件路径
                            )
                        except Exception as e:
                            self.log(f"插入图片时出错: {str(e)}，尝试备选方法")
                            # 备选方法：使用PIL处理图片
                            try:
                                from PIL import Image
                                with Image.open(img['processed_path']) as pil_img:
                                    img_byte_arr = io.BytesIO()
                                    pil_img.save(img_byte_arr, format=img['ext'].upper())
                                    img_byte_arr = img_byte_arr.getvalue()
                                    
                                    new_page.insert_image(
                                        img['rect'],
                                        stream=img_byte_arr
                                    )
                            except Exception as e2:
                                self.log(f"备选方法也失败: {str(e2)}，跳过此图片")
                
                # 保存处理后的文档
                new_pdf.save(output_path)
                new_pdf.close()
                original_pdf.close()
            
            self.log(f"共处理 {image_count} 张图片，其中 {modified_count} 张包含人脸并已打码")
            self.log(f"处理后的PDF文档已保存至: {output_path}")
            return True
            
        except Exception as e:
            self.log(f"PDF文档处理错误: {str(e)}")
            return False
    
    # 视频处理函数
    def process_video_frames(self, input_path: str, start_time: float = 0, duration: Optional[float] = None) -> Tuple[Optional[str], Optional[float], Optional[int], Optional[int]]:
        """视频帧处理函数，加强错误处理"""
        # 参数验证与初始化
        if not (0 <= g_precomputed["opacity"] <= 1):
            raise ValueError("不透明度(opacity)必须在0到1之间")
        if g_precomputed["feather_radius"] < 0:
            raise ValueError("羽化半径(feather_radius)不能为负数")
        if g_precomputed["kernel_size"] < 1:
            raise ValueError("模糊强度(blur_strength)必须大于0")
        if g_precomputed["mosaic_block_size"] < 1:
            raise ValueError("马赛克块大小必须大于0")
        
        # 视频基础信息读取
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"输入视频文件不存在: {input_path}")
        cap = cv2.VideoCapture(input_path)
        
        # 检查视频是否打开成功
        if not cap.isOpened():
            raise Exception(f"无法打开视频文件: {input_path}")
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_duration = total_frames / fps if fps > 0 else 0
        
        # 计算处理区间
        start_frame = int(start_time * fps) if fps > 0 else 0
        end_frame = min(start_frame + int(duration * fps), total_frames) if duration and fps > 0 else total_frames
        if start_frame >= total_frames:
            raise ValueError(f"开始时间 {start_time}s 超出视频时长 {video_duration}s")
        
        # 设置起始帧位置
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        actual_start = cap.get(cv2.CAP_PROP_POS_FRAMES)
        if abs(actual_start - start_frame) > 10:  # 允许一定误差
            self.log(f"警告: 无法精确跳转到起始帧 {start_frame}，实际从 {actual_start} 开始")
        
        # 临时文件与输出设置
        try:
            # 使用更稳定的临时文件创建方式
            temp_dir = tempfile.gettempdir()
            temp_video_name = f"temp_video_{generate_random_suffix()}.mp4"
            temp_video_path = os.path.join(temp_dir, temp_video_name)
            
            # 尝试使用合适的编码器
            try:
                fourcc = cv2.VideoWriter_fourcc(*'avc1')  # H.264
                if cv2.VideoWriter_fourcc(*'avc1') == -1:
                    raise ValueError("不支持avc1编码器")
            except:
                try:
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # MPEG-4
                except:
                    fourcc = cv2.VideoWriter_fourcc(*'XVID')  # 后备方案
            
            # 检查输出是否可以打开
            out = cv2.VideoWriter(temp_video_path, fourcc, fps, (width, height))
            if not out.isOpened():
                raise Exception(f"无法创建视频写入器，编码器: {fourcc}")
        except Exception as e:
            cap.release()
            raise Exception(f"初始化视频处理失败: {str(e)}")
        
        # 统计初始化
        process_start_time = time.time()
        total_frames_to_process = end_frame - start_frame
        total_faces_detected = 0
        failed_frames = 0
        
        self.log(f"开始处理视频帧: {input_path}")
        self.log(f"处理区间: {start_time}s ~ {min(start_time + (end_frame - start_frame)/fps, video_duration):.2f}s")
        self.log(f"打码参数: 类型={g_precomputed['blur_type']} | 相似度阈值={self.threshold} | 模糊强度={g_precomputed['kernel_size']} | "
                f"羽化半径={g_precomputed['feather_radius']} | 不透明度={g_precomputed['opacity']}")
        
        # 并行处理帧
        max_workers = min(os.cpu_count() or 4, 4)  # 减少worker数量，降低内存占用
        executor = ThreadPoolExecutor(max_workers=max_workers)
        futures: List[Tuple[int, Any]] = []
        
        # 帧处理和写入的批处理大小
        batch_size = 15  # 减小批处理大小，降低内存占用
        
        # 处理视频帧
        frame_index = 0
        last_progress = 0
        
        while True:
            if self.cancel_event.is_set():
                # 清理资源
                executor.shutdown(wait=False)
                cap.release()
                out.release()
                if os.path.exists(temp_video_path):
                    try:
                        os.remove(temp_video_path)
                    except:
                        pass
                return None, None, None, None
            
            ret, frame = cap.read()
            if not ret or frame_index >= total_frames_to_process:
                break
                
            # 检查帧是否有效
            if frame is None or not isinstance(frame, np.ndarray) or len(frame.shape) != 3:
                self.log(f"警告: 无效帧 #{frame_index}，跳过处理")
                failed_frames += 1
                frame_index += 1
                continue
                
            # 提交帧处理任务
            future = executor.submit(self.process_frame, frame.copy())
            futures.append((frame_index, future))
            
            # 按批处理和写入
            if len(futures) >= batch_size or frame_index == total_frames_to_process - 1:
                # 按顺序处理结果
                for idx, future in sorted(futures, key=lambda x: x[0]):
                    try:
                        processed_frame, face_count = future.result()
                        # 检查处理后的帧是否有效
                        if processed_frame is not None and isinstance(processed_frame, np.ndarray) and len(processed_frame.shape) == 3:
                            total_faces_detected += face_count
                            out.write(processed_frame)
                        else:
                            self.log(f"警告: 处理后的帧 #{idx} 无效，使用原始帧")
                            out.write(frame)  # 使用原始帧
                            failed_frames += 1
                    except Exception as e:
                        self.log(f"处理帧 #{idx} 时出错: {str(e)}")
                        failed_frames += 1
                
                # 更新进度
                progress = int((frame_index / total_frames_to_process) * 100)
                if progress > last_progress:
                    self.update_progress(progress)
                    last_progress = progress
                
                futures.clear()
                
            frame_index += 1
            # 定期释放资源
            if frame_index % 100 == 0:
                self.root.update_idletasks()
    
        # 清理资源
        executor.shutdown()
        cap.release()
        out.release()
        
        # 检查是否生成了有效视频
        if os.path.exists(temp_video_path) and os.path.getsize(temp_video_path) < 1024:  # 小于1KB的视频视为无效
            self.log("警告: 生成的临时视频文件过小，可能处理失败")
            try:
                os.remove(temp_video_path)
                return None, None, None, None
            except:
                pass
        
        # 统计与输出
        elapsed_time = time.time() - process_start_time
        fps_processing = total_frames_to_process / elapsed_time if elapsed_time > 0 else 0
        
        self.log("\n视频帧处理完成！")
        self.log(f"临时视频已保存至: {temp_video_path}")
        self.log(f"总处理时间: {elapsed_time:.2f} 秒")
        self.log(f"平均处理速度: {fps_processing:.2f} 帧/秒")
        self.log(f"共检测到人脸: {total_faces_detected}")
        self.log(f"处理失败的帧: {failed_frames}")
        self.log(f"白名单保留人脸: {len(self.whitelist_data['entries']) if self.whitelist_data else 0}")
        
        return temp_video_path, fps, width, height
    
    def merge_audio_and_video(self, video_without_audio: str, original_video: str, output_path: str, 
                            start_time: float = 0, duration: Optional[float] = None) -> bool:
        """合并音频和视频，使用本地FFmpeg"""
        self.log("\n开始合并音频和视频...")
        try:
            # 获取原始视频信息
            cap = cv2.VideoCapture(original_video)
            original_fps = cap.get(cv2.CAP_PROP_FPS)
            original_duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / original_fps if original_fps > 0 else 0
            cap.release()
            
            # 计算音频提取的时间范围
            audio_start = max(0, start_time)
            audio_end = min(original_duration, start_time + (duration if duration else float('inf')))
            audio_duration = audio_end - audio_start
            
            # 创建临时文件 - 使用更稳定的方式
            temp_dir = tempfile.gettempdir()
            temp_audio_name = f"temp_audio_{generate_random_suffix()}.aac"
            temp_audio = os.path.join(temp_dir, temp_audio_name)
            
            # 提取音频，使用本地FFmpeg
            cmd_extract = [
                self.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                '-ss', str(audio_start),
                '-t', str(audio_duration),
                '-i', original_video,
                '-vn', '-c:a', 'aac', '-b:a', '192k', temp_audio
            ]
            result = subprocess.run(cmd_extract, check=False, capture_output=True, text=True)
            if result.returncode != 0:
                self.log(f"FFmpeg提取音频错误: {result.stderr}")
                # 尝试不带时间参数提取整个音频
                self.log("尝试提取整个音频...")
                cmd_extract = [
                    self.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                    '-i', original_video,
                    '-vn', '-c:a', 'aac', '-b:a', '192k', temp_audio
                ]
                result = subprocess.run(cmd_extract, check=False, capture_output=True, text=True)
                if result.returncode != 0:
                    self.log(f"FFmpeg提取音频再次失败: {result.stderr}")
                    raise Exception("无法提取音频")
            
            # 合并音视频
            cmd_merge = [
                self.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                '-i', video_without_audio, 
                '-i', temp_audio,
                '-c:v', 'copy',  # 直接复制视频流，不重新编码
                '-c:a', 'aac',
                '-strict', 'experimental',
                output_path
            ]
            result = subprocess.run(cmd_merge, check=False, capture_output=True, text=True)
            if result.returncode != 0:
                self.log(f"FFmpeg合并错误: {result.stderr}")
                # 尝试重新编码视频
                self.log("尝试重新编码视频和音频...")
                cmd_merge = [
                    self.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                    '-i', video_without_audio, 
                    '-i', temp_audio,
                    '-c:v', 'libx264',
                    '-c:a', 'aac',
                    '-strict', 'experimental',
                    output_path
                ]
                result = subprocess.run(cmd_merge, check=True, capture_output=True, text=True)
                
            self.log(f"音视频合并成功，输出至: {output_path}")
            return True
            
        except Exception as e:
            self.log(f"FFmpeg合并失败: {str(e)}")
            self.log("尝试不使用FFmpeg直接保存...")
            
            # 尝试直接复制（无音频）
            try:
                shutil.copy(video_without_audio, output_path)
                self.log(f"已保存无音频的处理结果至: {output_path}")
                return True
            except Exception as e2:
                self.log(f"保存无音频视频失败: {str(e2)}")
                return False
        finally:
            if 'temp_audio' in locals() and os.path.exists(temp_audio):
                try:
                    os.remove(temp_audio)
                except:
                    pass
    
    def blur_faces_in_video(self, input_path: str, output_path: str, start_time: float = 0, duration: Optional[float] = None) -> bool:
        """对视频中的人脸进行打码处理"""
        # 第一步：处理视频帧（无音频）
        temp_video_path, fps, width, height = self.process_video_frames(
            input_path, start_time, duration
        )
        
        if not temp_video_path or self.cancel_event.is_set():
            return False
        
        # 第二步：合并音频和视频
        try:
            success = self.merge_audio_and_video(temp_video_path, input_path, output_path, start_time, duration)
        except Exception as e:
            self.log(f"合并音频和视频时出错: {str(e)}")
            # 即使合并失败，也保留处理后的无音频视频作为备份
            try:
                shutil.copy(temp_video_path, output_path)
                self.log(f"已保存无音频的处理结果至: {output_path}")
                success = True
            except:
                success = False
        finally:
            # 清理临时文件
            if os.path.exists(temp_video_path):
                try:
                    os.remove(temp_video_path)
                except:
                    self.log(f"警告: 无法删除临时文件 {temp_video_path}")
        
        return success

def main() -> None:
    # 确保中文显示正常
    os.environ["PYTHONUTF8"] = "1"
    
    # 启动GUI
    root = tk.Tk()
    app = FaceBlurApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
