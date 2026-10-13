# 随申办保障房监控通知机器人

自动监视上海"随申办"一网通办的**保障性租赁住房**房源名单，一旦有符合条件的新房源或数量变化，通过**企业微信群机器人**推送微信通知。

- 数据源：随申办一网通办（`zwdt.sh.gov.cn`）
- 运行方式：GitHub Actions（免费，无需服务器）
- 推送方式：企业微信群机器人 Webhook

---

## 一、功能说明

| 功能 | 说明 |
|---|---|
| 定时轮询 | 每 **5 分钟**查询一次浦东新区保障房房源 |
| 变动告警 | 项目**新增 / 房源增加 / 房源减少 / 下架**时推送（**随时**，不受整点限制） |
| 关键字告警 | 命中关键字的新增房源会**置顶单独标出**（🔔），普通命中用 ⭐，一并随时推送 |
| 心跳通知 | **8:00–20:00 每小时整点后推送一次；22:00 再推送一次**（内容为项目数/在线总数/关键字房源） |
| 夜间静默 | **北京时间 00:00–08:00 不推送**；但每 5 分钟仍会静默请求一次以**保活登录会话**（避免 Cookie 空闲失效） |
| 忽略名单 | 名单内的项目不参与变动告警（但会在心跳中显示并标注"已忽略"） |
| 异常通知 | 登录失效 / 抓取失败 / 返回空数据时推送提醒，并提示重新登录 |
| 推送渠道 | **企业微信 + 可选 Server酱（普通微信）并存** |

### 当前关键字
`森兰`、`中铁`、`桂竹`、`海上`、`西派`、`海华智`、`万安里`

### 当前忽略名单
| 项目 ID | 名称 |
|---|---|
| 4594 | 森兰星遇公寓(新展城店) |
| 3025 | 城家高级公寓（森兰洲海路地铁站店） |

> 注：当前监控范围为**浦东新区**。"中铁""海上"等关键字在浦东暂时匹配不到（只在其他区有）。

---

## 二、整体流程

```
GitHub Actions 每5分钟触发
        │
        ▼
ssb_monitor.py 调用随申办接口（带登录 Cookie）
        │
        ▼
与上次快照对比（ssb_state.json）
        │
   ┌────┴─────┐
   ▼          ▼
有变动/命中   无变动
   │          │
发变动告警   到点发心跳
   └────┬─────┘
        ▼
企业微信群机器人（企业微信 App 收到通知）
```

---

## 三、数据来源（接口说明）

抓包得到的关键接口：

- **URL**：`POST https://zwdt.sh.gov.cn/smzy/shspacelife/bzf/getProjectList`
- **鉴权**：必须带登录 `Cookie`（含 `SESSION` 和 `shspace_auth_token`），不带会重定向到登录页
- **请求体**：`application/x-www-form-urlencoded`，内容为

```
params={"pageNo":1,"pageSize":500,"param":{"districtId":"14","doorType":"","rentHigh":"","rentLow":"","searchWord":"","street":[],"supplyWay":"","ringRdId":"","orderBy":"","isAsc":true}}
```

- **响应**：套了两层 JSON

```
body
 └─ json.data (字符串)
      └─ json.loads → data.data.results [ ... 房源列表 ... ]
```

- **分页**：`pageSize=500` 时浦东全部（约 64 条）一页即可取完
- **常用区 ID**：浦东新区=`14`（其余见 `districtId` 字段）

单个房源的关键字段：

| 字段 | 含义 |
|---|---|
| `projectId` | 项目唯一 ID（用于对比） |
| `projectName` | 项目名称 |
| `districtName` / `projectDistrictId` | 所在区 |
| `onlineFlatNum` | 在售/在线房源数（对比增减用） |
| `totalFlatNum` | 总房源数 |
| `rentLow` / `rentHigh` | 租金范围 |
| `projectTel` | 联系电话 |

---

## 四、抓包获取接口与 Cookie（Mac）

> 只有在**更换 Cookie**或**接口变动**时才需要重新做这一步。

### 1. 安装 mitmproxy

```bash
pip3 install mitmproxy
# 若提示没有 pip，用 python3 -m pip install mitmproxy
```

### 2. 生成证书（首次必须真正启动一次）

```bash
mitmdump -p 8080
# 看到 "HTTP(S) proxy listening at *:8080" 后按 Ctrl+C 退出
```

证书生成在 `~/.mitmproxy/mitmproxy-ca-cert.pem`。

### 3. 信任证书

```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain \
  ~/.mitmproxy/mitmproxy-ca-cert.pem
```

（若报 `Error reading file ...`，说明第 2 步没生成成功，回去重做。）

### 4. 启动代理（本机有 VPN 时用 upstream 转发）

VPN（如 Clash）通常在 `127.0.0.1:7897`，mitmproxy 监听另一个端口 `8080`，并转发给它：

```bash
mitmproxy -m upstream:http://127.0.0.1:7897 -p 8080
```

> 没有 VPN 时直接 `mitmproxy -p 8080` 即可。**不要把 mitmproxy 也设成 7897**，那个端口被 VPN 占了。

### 5. 设置系统代理

系统设置 → 网络 → WiFi → 详细信息 → 代理，打开：
- 网页代理 (HTTP)：`127.0.0.1:8080`
- 安全网页代理 (HTTPS)：`127.0.0.1:8080`

用 Safari 打开任意 https 网站，若能正常访问且 mitmproxy 里能看到请求，说明证书 OK。

### 6. 抓取小程序请求

1. 打开 **Mac 版微信** → 进入"随申办"小程序 → 进入"保障房查询"页面 → 下拉刷新
2. 在 mitmproxy 里找到返回房源 JSON 的那条请求（按 `f` 可过滤，如 `~u bzf`）
3. 选中它

### 7. 导出并转成可读文本

选中请求后按 **`w`**，输入文件名（如 `/Users/你/ssb.flow`）保存。再用下面的脚本转换为文本：

`dump_flow.py`：

```python
import sys
from mitmproxy.io import FlowReader
from mitmproxy import http

src = sys.argv[1]
dst = sys.argv[2] if len(sys.argv) > 2 else src + ".txt"

out = []
with open(src, "rb") as f:
    for flow in FlowReader(f).stream():
        if not isinstance(flow, http.HTTPFlow):
            continue
        req = flow.request
        out.append("=" * 80)
        out.append(f"{req.method} {req.pretty_url}")
        out.append("--- REQUEST HEADERS ---")
        for k, v in req.headers.items():
            out.append(f"{k}: {v}")
        out.append("--- REQUEST BODY ---")
        try:
            out.append(req.get_text(strict=False) if req.content else "")
        except Exception:
            out.append(repr(req.content))
        if flow.response:
            resp = flow.response
            out.append(f"--- RESPONSE {resp.status_code} ---")
            for k, v in resp.headers.items():
                out.append(f"{k}: {v}")
            out.append("--- RESPONSE BODY ---")
            try:
                out.append(resp.get_text(strict=False) if resp.content else "")
            except Exception:
                out.append(repr(resp.content))

with open(dst, "w") as f:
    f.write("\n".join(out))
print(f"written: {dst}")
```

运行：

```bash
python3 dump_flow.py /Users/你/ssb.flow
# 生成 /Users/你/ssb.flow.txt
```

在 `.txt` 里找到 `Cookie:` 那一行，复制其中的 `SESSION=...; shspace_auth_token=...`（这就是后面要用的 `SSB_COOKIE`）。

### 8. 收尾（重要）

- 系统设置里**关掉两个代理**
- mitmproxy 窗口 `Ctrl+C`

---

## 五、企业微信群机器人申请

1. 打开 **work.weixin.qq.com** 注册企业微信（**个人也能注册**，无需营业执照）
2. 下载**企业微信 App** 登录
3. 建一个群（发起群聊，拉一个同事或用微信小号，外部群也可）
4. 进群 → 右上角 **···** → **群机器人** → **添加机器人** → 起名
5. 复制 **Webhook 地址**（形如 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxx`）

> 注意：`work.weixin.qq.com/wework_admin/...` 是后台资料页，**不是** Webhook。真正的 Webhook 域名是 `qyapi.weixin.qq.com`。

验证：

```bash
curl -X POST '你的Webhook' -H 'Content-Type: application/json' \
  -d '{"msgtype":"text","text":{"content":"测试"}}'
```

---

## 五之二、可选：接入普通微信（Server酱）

企业微信是官方接口，但如果你想在**普通微信**里收通知，可以加接 **Server酱**（通过它的公众号推送）。脚本支持**两个渠道并存**。

### 获取 SendKey

1. 打开 `https://sct.ftqq.com`，用**微信扫码登录**
2. 进入「SendKey」页面，复制密钥（以 `SCT` 或 `sctp` 开头）

### 配置

把 SendKey 加到仓库 Secret `SERVERCHAN_SENDKEY` 即可（见下一节）。

### 额度提醒（重要）

Server酱**免费版每天只有 5 条**。我们的心跳每小时一条会远超额度，所以默认策略是：

| 消息类型 | 企业微信 | Server酱 |
|---|---|---|
| 变动告警 / 关键字新房源 | ✅ | ✅ |
| 登录失效 / 抓取失败 | ✅ | ✅ |
| 定时心跳 | ✅ | ❌（默认不发） |

想让心跳也发到 Server酱：在 workflow 里设环境变量 `SERVERCHAN_HEARTBEAT=1`（需注意额度，建议先订阅会员）。

> SendKey 等同推送凭证，只放 Secret，别提交到仓库。

---

## 六、部署到 GitHub Actions（免费运行）

### 1. 建仓库并推送

```bash
git clone 本仓库地址
cd Notify_Bot
```

本仓库包含：

```
Notify_Bot/
├── ssb_monitor.py            # 监控脚本
├── .github/workflows/monitor.yml  # Actions 定时任务
└── README.md
```

### 2. 添加仓库 Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret：

| 名称 | 值 |
|---|---|
| `WECOM_WEBHOOK` | 企业微信机器人 Webhook |
| `SERVERCHAN_SENDKEY` | （可选）Server酱 SendKey，用于推送到普通微信 |
| `SSB_COOKIE` | `SESSION=...; shspace_auth_token=...` |

### 3. 手动触发测试

仓库 → Actions → 左侧 `ssb-monitor` → **Run workflow**。
- 成功会收到心跳消息
- 首次运行只建立基线，不推送历史房源

### 4. 自动运行

之后 GitHub 会按 `.github/workflows/monitor.yml` 里的 `cron: "*/5 * * * *"` 每 5 分钟自动运行。状态自动提交回仓库（`ssb_state.json`）。

> ⚠️ 建议用**公开仓库**：公开仓库 Actions 免费不限量；私有仓库每月只有 2000 分钟，每 5 分钟跑一次会超额。

---

## 六之二、让定时更可靠：外部定时器触发（重要）

GitHub Actions 自带的 `schedule` **非常不可靠**：官方明确说明会延迟（高峰尤甚），延迟过久甚至当天不触发，高频（如每 5 分钟）尤其容易丢。实测本仓库曾数小时不运行。

因此推荐用**外部定时服务**每 5 分钟调用 GitHub API 主动触发（保留 `schedule` 作为兜底）。

### 1. 生成 Token

细粒度 Token（Settings → Developer settings → Fine-grained tokens）：
- Repository access：Only select repositories → `Notify_Bot`
- Permissions：**Actions → Read and write**

（或经典 Token 勾选 `workflow` 权限。）

### 2. 用 cron-job.org 定时触发

注册 `https://cron-job.org`（免费）→ Create cronjob：

| 项 | 值 |
|---|---|
| URL | `https://api.github.com/repos/TJiangF/Notify_Bot/actions/workflows/monitor.yml/dispatches` |
| Method | `POST` |
| Schedule | Every 5 minutes |
| Header | `Authorization: Bearer <你的Token>` |
| Header | `Accept: application/vnd.github+json` |
| Header | `Content-Type: application/json` |
| Request body | `{"ref":"main"}` |

保存后即可稳定触发（TEST RUN 返回 204 表示成功）。

### 3. 手动验证

```bash
curl -i -X POST \
  -H "Authorization: Bearer <你的Token>" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/TJiangF/Notify_Bot/actions/workflows/monitor.yml/dispatches \
  -d '{"ref":"main"}'
# HTTP/2 204 = 成功
```

> Token 只放外部服务里，注意保密，用完可随时撤销。

---

## 七、日常维护

### 修改关键字 / 忽略名单 / 监控范围

编辑 `ssb_monitor.py` 顶部：

```python
DISTRICT_ID = "14"          # 区 ID，浦东=14
KEYWORDS = [...默认...]     # 支持环境变量 SSB_KEYWORDS 覆盖
IGNORE = {                  # 忽略名单：项目ID -> 名称
    "4594": "森兰星遇公寓(新展城店)",
    "3025": "城家高级公寓（森兰洲海路地铁站店）",
}
```

### 修改运行频率

编辑 `.github/workflows/monitor.yml`：

```yaml
on:
  schedule:
    - cron: "*/5 * * * *"   # 每5分钟；改成 "0 * * * *" 即每小时
```

### Cookie 失效怎么办

脚本检测到会推送"**登录信息已失效，请重新登录**"。
处理：按第四节重新抓一次 Cookie → 更新仓库 Secret `SSB_COOKIE` 即可。
（脚本在同一次失效期间**只提醒一次**，不会每 5 分钟刷屏。）

> 该登录态疑似**滑动过期**（空闲约 1 小时即失效）。因此：
> - 白天靠每 5 分钟轮询保持活跃
> - 夜间（00:00–08:00）仍会静默请求一次保活
> - **前提是触发要稳定**（见「六之二、外部定时器」），否则断档就会失效

---

## 八、本地测试（可选）

```bash
pip3 install requests

export WECOM_WEBHOOK='你的webhook'   # 不设则只打印，不发消息
export SSB_COOKIE='SESSION=...; shspace_auth_token=...'
export SSB_STATE='ssb_state.json'

# 跑一次
python3 ssb_monitor.py --once

# 常驻循环（本地服务器/NAS）
python3 ssb_monitor.py
```

---

## 九、常见问题

**Q：GitHub Actions 报 SSL / 超时？**
A：GitHub 运行在国外 IP，个别时候访问 gov 站点慢或被限。若持续失败，改用国内云服务器或家里常开设备运行 `ssb_monitor.py`。

**Q：本地测试报 `CERTIFICATE_VERIFY_FAILED`？**
A：因为还开着 mitmproxy 系统代理，Python 走了代理但不认其证书。临时用
`export REQUESTS_CA_BUNDLE="$HOME/.mitmproxy/mitmproxy-ca-cert.pem"`，
或直接关掉系统代理再测。

**Q：定时任务没按时跑？**
A：GitHub 的 cron 是"尽力而为"，可能延迟几分钟，属正常。

**Q：多久会因不活动被停？**
A：GitHub 规定 60 天仓库无提交活动会停用定时任务。本脚本每 2 小时的心跳会更新状态文件并提交，能保持活动。

**Q：合规吗？**
A：这是政府公开的保障房公示信息，脚本为**低频个人查询**（每 5 分钟一次请求）。请勿提高频率或用于批量抓取。
