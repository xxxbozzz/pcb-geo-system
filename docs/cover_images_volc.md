# 火山引擎封面图生成

这个方案只做一件事：

- 读取 `output/website_sync/*.html`
- 为每篇 HTML 生成同名封面图
- 输出为同目录下的 `*.jpg`

例如：

- `gold-finger-pcb-gold-plating-thickness-standard-process-reliability.html`
- `gold-finger-pcb-gold-plating-thickness-standard-process-reliability.jpg`

## 1. 环境变量

不要把密钥写进代码或仓库。

```bash
export VOLC_ACCESS_KEY_ID='你的 Access Key ID'
export VOLC_SECRET_ACCESS_KEY='你的 Secret Access Key'
```

可选参数：

```bash
export VOLC_REGION='cn-north-1'
export VOLC_CV_HOST='open.volcengineapi.com'
export VOLC_CV_REQ_KEY='high_aes_general_v20_L'
export VOLC_CV_MODEL_VERSION='general_v2.0_L'
export VOLC_CV_SCALE='3.5'
export VOLC_CV_DDIM_STEPS='25'
```

说明：

- 当前脚本默认使用火山新版 `CV20240606Api`
- 默认模型请求键为 `high_aes_general_v20_L`
- 如果你账号侧可用模型配置不同，可以通过环境变量覆盖

## 2. 依赖安装

```bash
python3 -m pip install --user volcengine-python-sdk
```

## 3. 先做 dry run

先看脚本会处理哪些文件：

```bash
python3 scripts/generate_cover_images_volc.py --dry-run --limit 10
```

## 4. 生成最近一批封面

```bash
python3 scripts/generate_cover_images_volc.py --limit 10
```

## 5. 只生成指定文章

```bash
python3 scripts/generate_cover_images_volc.py --only \
  gold-finger-pcb-gold-plating-thickness-standard-process-reliability \
  pcb-back-drilling-technology-precision-control
```

## 6. 覆盖重生成

```bash
python3 scripts/generate_cover_images_volc.py --limit 10 --overwrite
```

## 7. 可选风格

```bash
python3 scripts/generate_cover_images_volc.py --style-preset pcb-tech-cover
python3 scripts/generate_cover_images_volc.py --style-preset micrograph
python3 scripts/generate_cover_images_volc.py --style-preset factory-process
python3 scripts/generate_cover_images_volc.py --style-preset material-engineering
```

建议顺序：

1. 先 `--dry-run`
2. 再 `--limit 10`
3. 看效果后再全量跑

## 8. 当前默认行为

- 已有同名图片时默认跳过
- 不会修改 HTML
- 不会把图片写入页面
- 只会把图片保存到 HTML 同目录

