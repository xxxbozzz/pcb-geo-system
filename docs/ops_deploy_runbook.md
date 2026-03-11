# GEO 生产部署运行手册

## 目标

这份手册只覆盖当前生产环境的标准动作：

- 日常发布
- 首次初始化
- 定期 Docker 清理
- 常见故障排查

## 日常发布

日常发布只允许使用预构建镜像，不允许在服务器本地构建。

```bash
./deploy.sh 47.76.50.157 latest
```

如果要发布到指定镜像版本：

```bash
./deploy.sh 47.76.50.157 sha-<git短SHA>
```

日常发布会自动完成：

- 拉取服务器上的最新部署脚本和 compose 文件
- 拉取 GHCR 应用镜像
- 重建 `backend / geo-agent-app / dashboard / scheduler`
- 执行 `alembic upgrade head`
- 检查 backend 健康状态

日常发布不会再执行：

- `scripts/init_mysql.py`
- `scripts/load_seed_topics.py`

## 首次初始化

以下动作只在“全新环境”或“明确需要补数据”时手动执行，不属于日常发布。

### 1. 首次建库

优先使用 Alembic 建表：

```bash
ssh root@<服务器IP>
cd /opt/pcb-geo-system
docker exec geo-backend python -m alembic -c /app/backend/alembic.ini upgrade head
```

### 2. 种子话题导入

只在首次导入或明确需要补种子时执行：

```bash
ssh root@<服务器IP>
cd /opt/pcb-geo-system
docker exec geo-agent-core python scripts/load_seed_topics.py
```

### 3. 平台登录

知乎和微信登录需要在有图形界面的机器上手动完成一次。

```bash
python scripts/login_platforms.py --platform zhihu
python scripts/login_platforms.py --platform wechat
```

## 定期清理

推荐只做温和清理，不把清理动作放进部署脚本。

执行方式：

```bash
./scripts/remote_docker_cleanup.sh 47.76.50.157
```

该脚本只会执行：

- `docker image prune -f`
- `docker builder prune -f`

不要作为日常动作执行：

- `docker system prune -a`
- `docker compose up --build`

## 常见故障

### 1. 查库接口超时

先看 backend 健康：

```bash
curl http://127.0.0.1:8001/api/v1/health
```

如果 `health` 正常，但 `articles`、`publications` 等接口超时，优先检查 MySQL 是否被元数据锁卡住：

```bash
docker exec geo-mysql mysql -uroot -proot_password -e "show processlist;"
```

如果看到大量 `Waiting for schema metadata lock`，通常是错误执行了初始化脚本，例如：

- `scripts/init_mysql.py`

这类脚本不应在生产日常发布时运行。

### 2. 发布后 build 标签显示异常

当前 build 标签来自服务器上的 `build_info.json`，它应该反映“实际部署的镜像 tag”，而不是你本地工作区状态。

如需刷新标签，重新执行一次标准发布即可：

```bash
./deploy.sh 47.76.50.157 sha-<git短SHA>
```

### 3. 需要回滚

直接发布上一版镜像 tag，不要在服务器本地回滚源码构建：

```bash
./deploy.sh 47.76.50.157 sha-<上一版SHA>
```
