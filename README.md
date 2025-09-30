# 人脸打码工具

一个多功能人脸模糊工具，支持对**图片、视频、Word文档、PDF文档**中的人脸进行自动检测与模糊处理，提供直观的GUI界面操作。本程序首推在Windows 11平台使用。

![人脸打码工具GUI主界面](https://raw.githubusercontent.com/sun-ao/face-blur-tool/main/images/face-blur-tool.png)  

## 功能特性

- 🖼️ **图片处理**：自动检测并模糊单张图片中的人脸
- 🎥 **视频处理**：支持指定时间区间的视频人脸模糊，保留原始音频
- 📄 **文档处理**：
  - Word（`.docx`）：识别并模糊文档中嵌入图片的人脸
  - PDF：识别并模糊PDF页面中图片的人脸（依赖`PyMuPDF`）
- 🎨 **多种模糊效果**：圆形模糊、椭圆形模糊、矩形模糊、马赛克、像素化
- 🛡️ **人脸白名单**：指定目录的人脸头像将被"豁免"（不进行模糊）
- 🚀 **GPU加速**：支持CUDA硬件加速（需额外配置）
- 🎚️ **精细参数**：模糊强度、羽化半径、不透明度、马赛克块大小等均可调节


## 快速开始

### 1. Conda安装（推荐）

Conda是一个开源的包管理系统和环境管理系统，推荐使用它来创建独立的运行环境：

1. 从[Miniconda官网](https://docs.conda.io/en/latest/miniconda.html)下载Windows版本的Miniconda3
2. 运行安装程序，按照向导完成安装（建议勾选"Add Miniconda3 to my PATH environment variable"）
3. 安装完成后，可通过Windows开始菜单打开"Anaconda Prompt"验证安装是否成功

### 2. 克隆仓库

首先，克隆本仓库到本地（需先安装[Git for Windows](https://git-scm.com/download/win)）：

```bash
# 克隆仓库
git clone https://github.com/sun-ao/face-blur-tool.git

# 进入项目目录
cd face-blur-tool
```

### 3. 环境搭建

```bash
# 创建并激活虚拟环境
conda create -n face-blur-tool python=3.12 --no-default-packages -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/

conda activate face-blur-tool

# 安装依赖
pip install -r requirements.txt
```


### 4. 模型准备

项目依赖InsightFace的 `buffalo_l` 模型，需将模型文件放置在 `.insightface/models/buffalo_l/` 目录下。模型包含以下文件（需从[InsightFace官方仓库](https://github.com/deepinsight/insightface)下载）：

- `1k3d68.onnx`
- `2d106det.onnx`
- `det_10g.onnx`
- `genderage.onnx`
- `w600k_r50.onnx`


### 5. FFmpeg 依赖（视频处理必需）

视频处理需依赖 **FFmpeg**，请将 `ffmpeg.exe` 放置在项目的 `ffmpeg/` 目录下。可从[FFmpeg官方网站](https://ffmpeg.org/)下载Windows版本。


## 使用方法

### 启动GUI工具

在虚拟环境中执行以下命令，启动图形界面：

```bash
python main.py
```


### GUI界面操作流程

1. **选择文件类型**：从下拉框选择"视频/图片/Word文档/PDF文档"；
2. **选择输入文件**：点击"浏览..."选择待处理的源文件；
3. **设置输出路径**：默认在输入文件同目录生成 `{文件名}_blurred{扩展名}`，也可自定义；
4. **（视频专属）时间区间**：如需部分处理，可设置"开始时间"和"处理时长"（设为`0`表示处理全部）；
5. **配置模糊参数**：选择模糊类型，调整"模糊强度""羽化半径"等参数；
6. **（可选）人脸白名单**：指定包含"无需模糊人脸"的目录（如员工头像文件夹）；
7. **开始处理**：点击"开始处理"，通过日志和进度条查看实时状态。


### 使用PyInstaller打包为可执行文件

项目已包含打包配置文件 `face_blur.spec` 和自动化打包脚本 `package.bat`，可直接打包为Windows可执行文件：

1. 确保已安装PyInstaller：
   ```bash
   pip install pyinstaller
   ```

2. 运行打包脚本：
   ```bash
   package.bat
   ```

3. 打包完成后，可执行文件及相关依赖会生成在 `dist/` 目录下，其中 `face-blur.exe` 是主程序。

4. 打包注意事项：
   - 打包前请确保所有模型文件和FFmpeg已正确放置
   - 首次打包可能需要较长时间
   - 打包过程会自动清理之前的打包结果
   - 如遇打包错误，可查看控制台输出的错误信息排查问题


## 参数说明

| 参数             | 说明                                 | 可调范围/选项                     |
|------------------|--------------------------------------|----------------------------------|
| 打码类型         | 人脸模糊的形状/效果                 | 圆形/椭圆形/矩形/马赛克/像素化   |
| 人脸相似度阈值   | 白名单人脸的匹配严格程度（越高越严） | 0.1 ~ 0.9                        |
| 模糊强度         | 模糊效果的明显程度（值越大越模糊）   | 5 ~ 100                          |
| 马赛克块大小     | 马赛克/像素化的块尺寸（值越大块越大）| 5 ~ 50                           |
| 羽化半径         | 模糊边缘的过渡范围（值越大过渡越自然）| 0 ~ 20                           |
| 不透明度         | 模糊区域的透明度（1为完全不透明）    | 0.1 ~ 1.0                        |


## 依赖库

核心依赖通过 `requirements.txt` 管理：

```bash
pip install -r requirements.txt
```

关键依赖说明：

- `insightface`：人脸检测与特征提取；
- `onnxruntime`：ONNX模型推理（CPU）；
- `onnxruntime-gpu`：ONNX模型推理（GPU，可选，需额外配置）；
- `opencv-python`：图像处理；
- `python-docx`：Word文档解析；
- `PyMuPDF`：PDF文档解析；
- `tkinter`：GUI界面。


## GPU加速配置

若需GPU加速（大幅提升视频/多图处理速度），需额外配置：

1. 安装GPU版本的`onnxruntime`：
   ```bash
   pip uninstall onnxruntime  # 若已安装CPU版本
   pip install onnxruntime-gpu
   ```

2. 安装与`onnxruntime-gpu`兼容的 [**CUDA Toolkit**](https://developer.nvidia.com/cuda-12-9-1-download-archive) 和 [**cuDNN**](https://developer.nvidia.com/cudnn-9-11-0-download-archive)（版本需匹配，参考[官方文档](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)）。


## 常见问题（FAQ）

### Q1：启动时报"模型不存在"错误？
A：请确认`buffalo_l`模型文件已完整放置在 `.insightface/models/buffalo_l/` 目录下，包含所有必需的 `.onnx` 文件。

### Q2：视频处理后没有声音？
A：需确保`ffmpeg`可正常调用，检查`ffmpeg/ffmpeg.exe`是否存在且可用。工具会自动提取并合并原始视频的音频，若仍异常，可尝试更新`ffmpeg`版本。

### Q3：Word/PDF处理无效果？
A：请确认已安装对应依赖：
- Word支持：`pip install python-docx`
- PDF支持：`pip install PyMuPDF`

### Q4：GPU加速不生效？
A：检查三点：
- 是否安装了 `onnxruntime-gpu`（而非`onnxruntime`）；
- CUDA和cuDNN版本是否与`onnxruntime-gpu`兼容；(已验证 CUDA 12.9.1 + cuDNN 9.11.0 可行)
- 工具日志中是否显示"使用提供者: ['CUDAExecutionProvider']"。


## 致谢

- 感谢[InsightFace](https://github.com/deepinsight/insightface)提供高效的人脸检测与特征提取能力；
- 感谢[FFmpeg](https://ffmpeg.org/)提供强大的音视频处理支持；
- 感谢所有依赖库的开发者们。


若发现问题或有功能建议，欢迎提交[Issue](https://github.com/sun-ao/face-blur-tool/issues)或[Pull Request](https://github.com/sun-ao/face-blur-tool/pulls)！