# 随申办 + 明珠在线 房源监控通知机器人

自动监视上海两个官方平台的房源，一旦有新房源或数量变化，通过**企业微信 / 普通微信**推送通知。

| 数据源 | 说明 | 覆盖 |
|---|---|---|
| **随申办 一网通办** | `zwdt.sh.gov.cn` 保障性租赁住房 | 浦东新区（可改区） |
| **明珠在线**（浦东人才公寓/安居平台） | `pdrcgy.pudong.gov.cn` | 全部 |

- 运行方式：**GitHub Actions**（免费，无需服务器）+ 外部定时器（cron-job.org）保证准点
- 推送渠道：**企业微信群机器人** +（可选）**Server酱**（推到普通微信）

---

## 一、功能说明

| 功能 | 说明 |
|---|---|
| 定时轮询 | 每 **5 分钟**查询两个数据源 |
| 随申办·变动告警 | 项目**新增 / 房源增加 / 房源减少 / 改名 / 下架**时**立即**推送（不受整点限制） |
| 随申办·关键字 | 命中关键字的房源用 ⭐ 标注；命中关键字的**新增**置顶 🔔 单独标出 |
| 随申办·供应预告 | 抓取 `getNotice` 预告；**有新增预告立即推送**（名称/地址/计划供应日/租金/电话），并列入心跳与每日报表 |
| 明珠在线·变动告警 | 房源列表**新增 / 减少 / 改名**时**立即**推送，含**名称、地址、电话、状态、可租套数** |
| 心跳通知 | **08:00–20:00 每小时整点后一次；22:00 再一次**（内容：各自项目数、随申办在线总数与关键字房源） |
| 夜间静默 | **北京时间 00:00–08:00 不推送**；但仍每 5 分钟静默请求一次（保活） |
| 忽略名单 | 名单内项目不参与告警（心跳中标注“已忽略”） |
| 异常通知 | 登录失效 / 抓取失败 / 空数据时**推送提醒一次**，恢复后提示“✅ 已恢复” |
| 双渠道 | 企业微信 + 可选 Server酱 并存 |

### 当前关键字
`森兰`、`中铁`、`桂竹`、`海上`、`西派`、`海华智`、`万安里`

### 当前忽略名单（随申办）
| 项目 ID | 名称 |
|---|---|
| 4594 | 森兰星遇公寓(新展城店) |
| 3025 | 城家高级公寓（森兰洲海路地铁站店） |

> 监控范围为**浦东新区**（`DISTRICT_ID="14"`）。“中铁”“海上”等关键字在浦东暂时匹配不到。

---

## 二、整体流程

```
GitHub Actions（cron-job.org 每5分钟触发）
        │
        ▼
ssb_monitor.py  ← 一次运行查两个源
   ├── 随申办：带 Cookie 调 getProjectList
   └── 明珠在线：带 remember-me 调 getProjectAndHouse
        │
        ▼
   与上次快照对比（ssb_state.json）
        │
   ┌────┴─────────┐
有变动/关键字新增   无变动
   │                │
立即推送变动      到整点发心跳
   └───────┬────────┘
           ▼
   企业微信群 / Server酱（普通微信）
```

---

## 三、数据源一：随申办（zwdt.sh.gov.cn）

- **接口**：`POST https://zwdt.sh.gov.cn/smzy/shspacelife/bzf/getProjectList`
- **鉴权**：必须带登录 `Cookie`（含 `SESSION`、`shspace_auth_token`），不带会跳登录页
- **请求体**：`application/x-www-form-urlencoded`
  ```
  params={"pageNo":1,"pageSize":500,"param":{"districtId":"14","doorType":"","rentHigh":"","rentLow":"","searchWord":"","street":[],"supplyWay":"","ringRdId":"","orderBy":"","isAsc":true}}
  ```
- **响应**：**两层 JSON**
  ```
  body → json.data（字符串）→ 再 json.loads → data.data.results [ ... ]
  ```
- **分页**：`pageSize=500` 时浦东全部（约 64 条）一页取完
- **区 ID**：浦东=`14`（其余见返回的 `districtId`）

关键字段：`projectId`、`projectName`、`onlineFlatNum`（在线/可租房源数）、`totalFlatNum`、`rentLow/rentHigh`、`projectTel`、`districtName`。

### 供应预告接口

- **URL**：`POST https://zwdt.sh.gov.cn/smzy/shspacelife/bzf/getNotice`（**multipart/form-data**，字段 `params`）
- **参数**：`params={"pageNo":1,"pageSize":100,"param":{"noticeId":""}}`
- **响应**：同样两层结构；字段有 `noticeId`、`projectName`、`projectAddress`、`planRentLevel`（计划租金）、`planSupplyDate`（计划供应日）、`contact`（电话）、`orgName`（运营单位）、`introduction`（介绍）
- 用于：心跳里的“供应预告”板块、**新增预告即时推送**、以及每日报表的预告表

---

## 四、数据源二：明珠在线（pdrcgy.pudong.gov.cn）

南康 GIS 房源平台，**需要登录**。

- **接口**：`POST https://pdrcgy.pudong.gov.cn/api/rcaj/fwcx/getProjectAndHouse.html`
- **鉴权**：`Cookie`（`JSESSIONID`+`SERVERID` 或 `remember-me`）**且** 头带 `x-csrf-token`（缺 → `403`）
- **请求体**：JSON，关键 `"type":2`、`"page_param":{"PAGE":1,"LIMIT":500}`（一次取全）
- **响应**：`project1/project2/project3` 为三种排序的同一批项目，**按 `projectId` 去重**；`xm_total` 为总数
- **关键字段**：`projectId`、`villageProjectName`、`projectStatusName`（待供应/运营/在建）、`kzts`（可租套数）、`LOCATION`（地址）、`lxdh`（电话）、`releaseTime`

### 登录与会话：全自动（无需手动更新 Cookie）

该站会话（`JSESSIONID`）约 **40–60 分钟**就失效，保活无效。脚本用**自动登录 + remember-me 长期会话**解决：

1. 会话失效时自动登录：
   - 取登录页拿 CSRF → 取 `/captcha.jpg`
   - 用 **ddddocr** 识别 **5 位数字验证码**（识别不到 5 位就换图重试，最多 12 次）
   - 用页面里的 RSA 公钥加密密码 → `POST /login?z=1`（带 `remember-me=true`）
2. 登录成功得到 **`remember-me` cookie**（Spring 记住我，约 **2 周**有效）。脚本**加密后**存进 `ssb_state.json`（密钥 = Secret `PD_ENC_KEY`）。即使 `JSESSIONID` 过期，服务器也会凭 remember-me 自动重建会话。
3. remember-me 到期后自动重登，循环往复。

> - 账号密码只存 Secret `PD_USER`/`PD_PASS`；会话用 `PD_ENC_KEY` 加密后才落仓库，**不会明文暴露**。
> - 自动登录依赖第三方 OCR（ddddocr），属自动化登录手段，请自行斟酌。
> - 首次运行建立基线，只报之后的新增/减少/改名。

---

## 五、抓包（仅随申办换 Cookie / 接口变动时需要；Mac）

> 明珠在线已自动登录，**不需要抓包**。

### 1. 安装 mitmproxy
```bash
pip3 install mitmproxy    # 没有 pip 就用 python3 -m pip install mitmproxy
```

### 2. 生成证书（首次必须真正启动一次）
```bash
mitmdump -p 8080          # 看到 listening 后 Ctrl+C 退出
```
证书在 `~/.mitmproxy/mitmproxy-ca-cert.pem`。

### 3. 信任证书
```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain \
  ~/.mitmproxy/mitmproxy-ca-cert.pem
```

### 4. 启动代理（有 VPN 时用 upstream 转发）
```bash
mitmproxy -m upstream:http://127.0.0.1:7897 -p 8080
```
> 没有 VPN 就用 `mitmproxy -p 8080`。**别把 mitmproxy 设成 7897**（那是 VPN 端口）。

### 5. 让 Mac 走代理
系统设置 → 网络 → WiFi → 详细信息 → 代理，两项都指 `127.0.0.1:8080`（HTTP + HTTPS）。

### 6. 抓随申办小程序
Mac 版微信 → 随申办小程序 → 保障房页面 → 下拉刷新；在 mitmproxy 里找返回房源的请求（按 `f` 过滤，如 `~u bzf`）。

### 7. 导出 / 转文本
选中请求按 **`w`** 存成 `.flow`，再用 `dump_flow.py` 转文本：
```bash
python3 dump_flow.py /Users/你/ssb.flow      # 生成 ssb.flow.txt
```
在 txt 里找 `Cookie:` 行，取 `SESSION=...; shspace_auth_token=...` 即 `SSB_COOKIE`。

### 8. 收尾
关掉系统两个代理，mitmproxy 里 `Ctrl+C`。

---

## 六、推送渠道

### 企业微信群机器人（主渠道）
1. `work.weixin.qq.com` 注册企业微信（个人也能注册）→ 下载 App 登录
2. 建一个群（拉同事或微信小号）
3. 进群 → 右上角 **···** → **群机器人** → 添加 → 复制 Webhook
   （域名是 `qyapi.weixin.qq.com`，不是 `work.weixin.qq.com/wework_admin/...`）

验证：
```bash
curl -X POST '你的Webhook' -H 'Content-Type: application/json' \
  -d '{"msgtype":"text","text":{"content":"测试"}}'
```

### （可选）Server酱 → 普通微信
1. `https://sct.ftqq.com` → 微信扫码登录 → 复制 SendKey（`SCT`/`sctp` 开头）→ 存 Secret `SERVERCHAN_SENDKEY`
2. **免费版每天仅 5 条**，因此默认**心跳不发 Server酱**，只有“变动 / 关键字 / 异常”会发：

| 消息 | 企业微信 | Server酱 |
|---|---|---|
| 变动 / 关键字新房源 | ✅ | ✅ |
| 登录失效 / 抓取失败 | ✅ | ✅ |
| 定时心跳 | ✅ | ❌（默认） |

想让心跳也发 Server酱：设环境变量 `SERVERCHAN_HEARTBEAT=1`（注意额度）。

---

## 七、部署到 GitHub Actions

### 1. 仓库文件
```
Notify_Bot/
├── ssb_monitor.py                  # 监控主程序
├── dump_flow.py                    # 抓包 flow 转文本工具
├── .github/workflows/monitor.yml   # Actions 任务
└── README.md
```

### 2. 添加 Secrets
仓库 → Settings → Secrets and variables → Actions：

| 名称 | 值 |
|---|---|
| `WECOM_WEBHOOK` | 企业微信机器人 Webhook |
| `SERVERCHAN_SENDKEY` | （可选）Server酱 SendKey |
| `SSB_COOKIE` | 随申办 Cookie：`SESSION=...; shspace_auth_token=...` |
| `PD_USER` | 明珠在线账号（手机号） |
| `PD_PASS` | 明珠在线密码 |
| `PD_ENC_KEY` | 会话加密密钥：`python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` |

### 3. 手动测试
仓库 → Actions → `ssb-monitor` → **Run workflow**。首次只建基线；勾选 **test** 可强制发一条心跳。

### 4. 自动运行
`.github/workflows/monitor.yml` 里 `cron: "*/5 * * * *"`。状态自动提交回仓库（`ssb_state.json`）。

> ⚠️ 用**公开仓库**：Actions 免费不限量；私有仓库每月仅 2000 分钟，每 5 分钟会超额。

---

## 八、让定时更可靠：外部定时器（重要）

GitHub 自带 `schedule` **极不可靠**（官方不保证，延迟/漏跑常见，高频尤甚）。实测本仓库曾数小时不跑。因此用**外部定时服务**每 5 分钟主动触发（保留 `schedule` 兜底）。

1. 建**细粒度 Token**：`Notify_Bot` → 权限 **Actions: Read and write**
2. `https://cron-job.org` 注册 → Create cronjob：
   | 项 | 值 |
   |---|---|
   | URL | `https://api.github.com/repos/TJiangF/Notify_Bot/actions/workflows/monitor.yml/dispatches` |
   | Method | **POST** |
   | Schedule | Every 5 minutes |
   | Header | `Authorization: Bearer <Token>` |
   | Header | `Accept: application/vnd.github+json` |
   | Header | `Content-Type: application/json` |
   | Body | `{"ref":"main"}` |

3. TEST RUN 返回 **204** 即成功。

---

## 九、日常维护

### 改关键字 / 忽略名单 / 监控范围
编辑 `ssb_monitor.py` 顶部：
```python
DISTRICT_ID = "14"                     # 浦东=14
KEYWORDS = [...]                        # 需随申办关键字；可用环境变量 SSB_KEYWORDS 覆盖
IGNORE = {"4594": "...", "3025": "..."} # 忽略名单：项目ID -> 名称
```

### 改频率 / 静默时段
`ssb_monitor.py` 里 `HEARTBEAT_HOURS`、`in_quiet_hours()`；工作流里 `cron`。
> 夜间（00:00–08:00）即使不推送，也会每 5 分钟请求一次保活——**不要把这个停掉**，否则会话会失效。

### 失效怎么处理
- **随申办**：会推送“登录信息已失效”，按第五节重新抓 Cookie，更新 `SSB_COOKIE`。
- **明珠在线**：**全自动**，无需处理；只有自动登录也失败（如改密码）才推送提醒，届时更新 `PD_USER`/`PD_PASS`。

---

## 十、本地测试（可选）

```bash
pip3 install requests cryptography        # 需要自动登录再加 ddddocr

export WECOM_WEBHOOK='...'                 # 不设则只打印
export SSB_COOKIE='SESSION=...; shspace_auth_token=...'
export PD_USER='手机号'; export PD_PASS='密码'
export PD_ENC_KEY='Fernet密钥'
export SSB_STATE='ssb_state.json'

python3 ssb_monitor.py --once              # 跑一次
python3 ssb_monitor.py                     # 常驻循环（本地服务器/NAS）
```

---

## 十一、每日存档与 HTML 报表

每天 12:00 后的首次运行会自动：

- `snapshot.py`：抓取**全部行政区**的随申办 + 明珠在线 + **供应预告**，存为 `data/YYYY-MM-DD.json`
- `report.py`：生成 `report.html`

报表内容：随申办「供应预告」表、各区统计、变动明细、全部房源（可按区筛选）、逐日趋势。

---

## 十二、常见问题

**Q：Actions 报 SSL / 超时？** GitHub 在国外 IP，个别时候访问 gov 慢或被限；持续失败就改用国内服务器或家里常开设备跑。

**Q：本地测试报 `CERTIFICATE_VERIFY_FAILED`？** 因为还开着 mitmproxy 系统代理。临时 `export REQUESTS_CA_BUNDLE="$HOME/.mitmproxy/mitmproxy-ca-cert.pem"`，或关掉系统代理。

**Q：定时不跑 / 不准时？** GitHub cron 不可靠，务必配外部定时器（第八节）。

**Q：明珠在线为什么会话老失效？** 服务器端约 40–60 分钟硬超时；已用 remember-me（约 2 周）+ 自动登录解决，无需手动干预。

**Q：多久会因不活动被停？** GitHub 规定 60 天无提交活动停用定时任务；本脚本会持续提交状态，保持活动。

**Q：合规吗？** 均为政府公开房源信息，低频个人查询（每 5 分钟一次请求）。请勿提高频率或用于批量抓取。
