# 模型文件说明

本目录需放置InsightFace的`buffalo_l`模型文件，用于人脸检测与特征提取。

## 所需文件
需包含以下`.onnx`文件：
- 1k3d68.onnx
- 2d106det.onnx
- det_10g.onnx
- genderage.onnx
- w600k_r50.onnx

## 下载来源
可从InsightFace官方仓库或模型库下载：
- 官方仓库：https://github.com/deepinsight/insightface
- 模型下载页：https://github.com/deepinsight/insightface/releases/

## 放置要求
将上述文件直接放在本目录下（无需额外子文件夹），确保路径为：
`.insightface/models/buffalo_l/[模型文件]`