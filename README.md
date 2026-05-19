# 校园活动管理平台后端

基于 Python 3.10+、Flask、SQLAlchemy、SQLite 的后端项目骨架。

## 项目结构

```text
backend/
  app/
    api/v1/              # API 蓝图
    common/              # 响应、异常、数据库会话等公共能力
    services/            # 业务逻辑层
  config.py              # 配置、数据库连接
  init_db.py             # 初始化数据库与基础数据
  models.py              # SQLAlchemy 模型
  run.py                 # 本地启动入口
```

## 快速开始

```bash
pip install -r requirements.txt
python init_db.py
python run.py
```

服务默认启动在 `http://127.0.0.1:5000`。

## 接口示例

### 健康检查

```bash
curl http://127.0.0.1:5000/api/health
```

### 获取活动分类

```bash
curl http://127.0.0.1:5000/api/categories
```

返回格式遵循 API 文档：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": 1,
      "name": "学术类",
      "level": 1,
      "sort_order": 1,
      "children": []
    }
  ]
}
```

新增业务接口时，建议按 `api/v1/<模块>.py` 负责路由、`services/<模块>_service.py` 负责业务逻辑的方式扩展。
