# PCB GEO 知识引擎 v2.0 使用指南

本版本针对 **内容质量、自动分发、AI 搜索优化** 进行了全面升级。

## 🚀 快速开始

### 1. 启动服务
生产环境改为 GitHub Actions 预构建镜像部署，不再在服务器本地构建镜像。

首次使用前：
- 在 GitHub Actions 中完成 `Build Image`
- 将 GHCR 容器包设为 `public`，或在执行部署命令的终端中导出 `GHCR_USERNAME / GHCR_TOKEN`

部署命令：
```bash
./deploy.sh 47.76.50.157 latest
```
如果需要部署到指定提交镜像，可使用：
```bash
./deploy.sh 47.76.50.157 sha-<git短SHA>
```
启动后访问控制台：[http://47.76.50.157:8503](http://47.76.50.157:8503)

日常发布只跑镜像拉取、容器重建和 Alembic 迁移，不再混入初始化脚本。
首次初始化、种子导入、定期清理请看：[docs/ops_deploy_runbook.md](/Users/kev/Documents/pcb-geo-system/docs/ops_deploy_runbook.md)

### 2. 初始化自动发布 (必须)
为了让 AI 能够发布到知乎和微信公众号，需要手动登录一次以保存 Cookie：

```bash
# 登录知乎
python scripts/login_platforms.py --platform zhihu

# 登录微信公众号
python scripts/login_platforms.py --platform wechat
```
_注意：此步骤需在有图形界面的机器上运行，或使用 X11 转发。_

### 3. 开始批量生产
后台运行批量生成器 (包含自动返修机制)：
```bash
nohup python batch_generator.py > batch.log 2>&1 &
```

---

## ✨ 新特性说明

### 1. 自动返修与质检 (Auto-Repair)
- 引擎生成初稿后，会自动运行 **9维度质检**。
- 若评分 < 95，系统会自动分析扣分原因，并指示 Generator 重新修改。
- 修正过程完全自动化，最多重试 3 次。

### 2. 统一控制台 (Unified Dashboard)
- **生产监控**：查看待处理队列、平均分、最新文章。
- **内容管理**：预览 Markdown 源码，渲染效果。
- **主动探测**：监控 DeepSeek/豆包/混元 对 "深亚电子" 的品牌覆盖率。
- **知识图谱**：可视化文章间的内部链接拓扑。

### 3. SEO 与官网同步
- 导出的 HTML 现在包含 **Schema.org JSON-LD** (Article, FAQPage)。
- 自动生成 `sitemap.xml` 和 `robots.txt`。
- 请定期将 `output/website_sync` 目录同步到官网服务器。

### 4. 资源保护
- 容器限制为 **3.5 CPU / 7GB RAM** 以防止服务器卡死。
- 批量生成器启用单线程串行模式，并强制垃圾回收。

---

## 🔧 常见问题

**Q: 为什么 Playwright 报错？**
A: 请检查 `config/cookies/*.json` 是否存在。如果失效，请重新运行登录脚本。

**Q: 如何添加更多话题？**
A: 直接修改 `seed_topics.json` 或让 Scout Agent 自动发现。

**Q: 仪表盘报错 "Database Error"？**
A: 请等待 `docker-compose` 中的 `mysql_db` 完全启动（初次启动可能需要 1-2 分钟）。
