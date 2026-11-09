# 隐私计算开放互联平台 - 前端 UI 重新设计

> 设计日期：2026-07-08
> 状态：已确认，待制定实施计划
> 技术栈：React 18 + UmiJS 4 + Ant Design 5 + Less + Nx monorepo
> 前端源码：`NewProject/secretpad-frontend/apps/platform`

## 1. 品牌系统

### 1.1 品牌名称

- **平台全称**：隐私计算开放互联平台
- **简称**：开放互联平台（用于侧边栏 Logo 旁、浏览器标签短标题）
- **英文副标**：Privacy Computing Open Interconnection Platform（用于登录页脚标、favicon alt）

### 1.2 Slogan

> 让隐私计算，开放互联

### 1.3 Logo 设计

- **图形标识**：互联节点抽象图——3 个节点（圆形）通过曲线互联，形成三角拓扑，节点用青色渐变填充，连线用半透明白。寓意"多节点隐私计算互联"
- **字标**：图形右侧搭配"隐私计算开放互联平台"文字，主标题用深色 `#001529`，副标题"Open Interconnection"用浅青小字
- **变体**：
  - `logo-full.svg`（图形 + 字标，用于登录页、首页顶部）
  - `logo-compact.svg`（仅图形，用于折叠侧边栏、favicon）
- **配色**：图形用互联青渐变 `#08979c → #13c2c5`，字标深色 `#001529`

### 1.4 Favicon

- 基于 `logo-compact.svg` 图形标识生成 `favicon.ico`（32x32, 16x16）

## 2. 配色系统

### 2.1 核心色板

| 角色 | 色值 | 用途 |
|------|------|------|
| 主色 Primary | `#08979c`（互联青） | 按钮、链接、菜单选中、图标高亮、品牌强调 |
| 主色浅 | `#13c2c5` | Hover、渐变终点、浅色图标 |
| 主色更浅 | `#e6fffb` | 选中背景、Tag 背景、浅色卡片 |
| 主色深 | `#006d75` | Pressed、深色文本强调 |
| 成功 Success | `#52c41a` | 成功状态、完成态 |
| 警告 Warning | `#faad14` | 警告提示、待审核 |
| 错误 Error | `#ff4d4f` | 错误、失败、删除 |
| 信息 Info | `#08979c` | 复用主色 |

### 2.2 中性色板

| 角色 | 色值 | 用途 |
|------|------|------|
| Sider 背景 | `#001529`（深墨蓝） | 折叠侧边栏底色 |
| Sider Hover | `#112545` | 菜单项 Hover |
| Sider 选中 | `#08979c`（主色） | 菜单选中项背景 |
| Header/内容区背景 | `#f5f7fa` | 浅灰，减少视觉疲劳 |
| 卡片背景 | `#ffffff` | 内容卡片 |
| 主文本 | `#1f2937` | 标题、正文 |
| 次文本 | `#6b7280` | 描述、辅助文字 |
| 禁用 | `#d1d5db` | 禁用态 |
| 边框 | `#e5e7eb` | 卡片边框、分割线 |

### 2.3 品牌渐变色

```
linear-gradient(135deg, #08979c 0%, #13c2c5 100%)
```

用途：Logo 图形、登录页背景、首页欢迎卡、关键 CTA 按钮

### 2.4 技术实现策略

当前项目有 80+ 处硬编码 `#0068fa`/`#1677ff`，采用双层策略：

1. **集中变量层**：在 `platform.config.tsx` 改 `colorPrimary: '#08979c'`，antd 组件自动跟随主题
2. **Less 变量统一层**：新建 `src/styles/variables.less`，定义 `@primary-color: #08979c` 等变量，全局引入，逐个替换硬编码色值

## 3. 布局结构

### 3.1 整体布局

从"顶部 Header + 左侧 Sider"双层结构变更为**单一深色左侧 Sider + 全宽内容区**。

```
┌──────────────────────────────────────────────┐
│ ┌─────────┐                                  │
│ │ Sider   │   Content（全宽）                │
│ │ (深色)  │                                  │
│ │         │   ┌──────────────────────────┐   │
│ │ [Logo]  │   │ 面包屑/页面标题           │   │
│ │         │   ├──────────────────────────┤   │
│ │ [菜单]  │   │                          │   │
│ │ 工作台  │   │  内容区                   │   │
│ │ 合作节点│   │                          │   │
│ │ 我的项目│   │                          │   │
│ │ 数据管理│   │                          │   │
│ │ 结果管理│   │                          │   │
│ │ 已集成算│   │                          │   │
│ │         │   │                          │   │
│ │ ─────── │   │                          │   │
│ │ [消息🔔] │   │                          │   │
│ │ [用户👤] │   └──────────────────────────┘   │
│ └─────────┘                                  │
└──────────────────────────────────────────────┘
```

### 3.2 Sider 侧边栏

- **背景**：深墨蓝 `#001529`
- **宽度**：展开 220px / 折叠 60px
- **折叠快捷键**：⌘+Ctrl+↑（保留现有交互）

| 区域 | 说明 |
|------|------|
| 顶部 Logo 区（64px 高） | 展开态：`logo-compact.svg` 图形 + "开放互联平台"文字；折叠态：仅 `logo-compact.svg` 图形居中 |
| 菜单区 | BFIA 菜单项 + 隐语原生菜单项。每项配 Antd 图标，选中态用主色背景 `#08979c` + 白字 |
| 底部功能区 | 消息通知🔔（带红点角标）+ 用户头像下拉菜单 |

### 3.3 内容区

- **页面标题栏**（可选）：内容区顶部 48px 半透明白条，左侧面包屑，右侧可放操作按钮
- **内容容器**：`padding: 24px`，背景 `#f5f7fa`
- **卡片**：白底、圆角 8px、阴影 `0 1px 2px rgba(0,0,0,0.06)`

### 3.4 移除的元素

- 顶部 Header 整个移除（Logo、子标题 Center/Edge、社区链接、帮助中心、协议切换移入用户下拉菜单）
- "隐语开源社区"外链移除（换品牌后不适用）
- `subTitle`（Center/Edge 标识）移入用户下拉菜单显示节点信息

### 3.5 路由层级

路由结构不变（`config/routes.ts` 保持），仅替换 `layout.view` 的子布局组件：
- `home-layout` 移除顶部 Header，改为纯内容容器
- `management-layout` 保留并增强为新的深色 SaaS Sider

## 4. 登录页设计

### 4.1 风格

居中毛玻璃卡片：全屏互联青渐变背景 + 居中毛玻璃登录卡片。

### 4.2 背景层

- **底色**：互联青渐变 `linear-gradient(135deg, #08979c 0%, #0050b3 100%)` 斜向铺满
- **装饰图形**：右上和左下各放半透明（opacity 0.08）的大尺寸互联节点 SVG，呼应 Logo 图形
- **动效**：背景渐变缓慢呼吸（20s 循环 opacity 微变）

### 4.3 毛玻璃登录卡片

| 属性 | 值 |
|------|-----|
| 尺寸 | 宽 420px，自适应高度 |
| 背景 | `rgba(255, 255, 255, 0.15)` 半透明白 |
| 模糊 | `backdrop-filter: blur(20px)` |
| 边框 | `1px solid rgba(255, 255, 255, 0.25)` |
| 圆角 | 16px |
| 阴影 | `0 8px 32px rgba(0, 0, 0, 0.2)` |
| 内边距 | 40px |

### 4.4 卡片内容

| 元素 | 样式 |
|------|------|
| Logo 图形 | `logo-compact.svg` 居中，48x48px |
| 平台名称 | "隐私计算开放互联平台"，白色，18px，加粗，居中 |
| Slogan | "让隐私计算，开放互联"，半透明白（0.7），13px，居中，间距 8px |
| 表单间距 | 上方 32px |
| 用户名输入框 | 毛玻璃风格：半透明白底 `rgba(255,255,255,0.2)`，白色边框，占位符白色半透明，输入文字深色。带 UserOutlined 图标前缀 |
| 密码输入框 | 同上，带 LockOutlined 图标前缀 |
| 登录按钮 | 全宽，白色背景 + 主色文字 `#08979c`，加粗，高度 44px，圆角 8px，Hover 微阴影 |
| 页脚 | 卡片下方 24px，"Privacy Computing Open Interconnection Platform"，白色半透明（0.5），11px，居中 |

### 4.5 交互

- 登录失败：卡片内顶部滑出红色 Toast 提示
- 登录成功：渐隐过渡跳转首页
- 输入框聚焦：边框变亮白 + 轻微发光阴影

## 5. 关键页面视觉规范

### 5.1 通用组件规范

| 组件 | 规范 |
|------|------|
| 卡片 | 白底、圆角 8px、`box-shadow: 0 1px 2px rgba(0,0,0,0.06)`、Hover 阴影加深 `0 4px 12px rgba(0,0,0,0.1)` |
| 主按钮 | 主色 `#08979c` 实心、白字、圆角 6px、高度 32/40px、Hover 色 `#13c2c5` |
| 次按钮 | 白底、主色字 + 主色边框、Hover 浅青底 `#e6fffb` |
| 表格 | 表头浅灰 `#fafafa` + 主色下划线、行 Hover `#e6fffb`、操作列用主色文字链接 |
| Tag | 状态色浅底 + 状态色文字（成功绿/警告橙/错误红/进行中青） |
| Modal/Drawer | 圆角 8px、Header 主色背景渐变 + 白字标题、关闭按钮右上角 |

### 5.2 首页（工作台）

- **欢迎栏**：主色渐变背景卡片（`#08979c → #13c2c5`），白字问候语 + 右侧主操作按钮
- **统计卡**：4 列白卡，大数字（28px 主色加粗）+ 标签（14px 灰）+ 底部趋势小图标
- **列表卡**：2 列，每行带状态 Tag，Hover 整行浅青底

### 5.3 项目列表页

- 顶部：标题"我的项目" + 右侧"新建项目"主按钮
- 卡片网格布局（每行 3 张），每张卡：
  - 项目名（加粗）+ 状态 Tag（右上角）
  - 描述（2 行截断）
  - 底部：节点数、创建时间、参与方头像组
  - Hover：上浮 2px + 阴影加深 + 边框主色
- 空状态：互联节点插画 + "暂无项目，点击新建"

### 5.4 DAG 编辑器（BFIA 核心）

| 区域 | 规范 |
|------|------|
| 组件树面板（左） | 浅灰底 `#fafafa`，组件项带主色图标，Hover 浅青底，可拖拽 |
| 画布（中） | 网格背景（点阵 `#e5e7eb`），节点白底圆角卡片带主色顶边，选中节点主色边框 + 浅青发光 |
| 配置面板（右） | 白底，表单项 Antd5 标准，分组用浅灰分割线，保存按钮主色 |
| 顶部工具栏 | 白底，左侧画布名 + 右侧"保存草稿"次按钮 + "提交"主按钮 |

### 5.5 空状态/加载规范

| 状态 | 规范 |
|------|------|
| 加载中 | Antd Spin 主色，大区域用骨架屏（浅灰块） |
| 空状态 | 互联节点线性插画 + 描述文字 + 主色操作引导按钮 |
| 错误状态 | 红色插画 + 错误描述 + 重试按钮 |

## 6. 信息架构与菜单

### 6.1 菜单整合

当前两套菜单（隐语原生 / BFIA 互联互通）通过协议切换。新设计统一为一套菜单，通过节点模式区分。

### 6.2 Autonomy 模式菜单

```
🏠 工作台           ← /home
🔗 合作节点         ← /node
📁 我的项目         ← /dag（含 BFIA + 原生项目）
📊 数据管理         ← /datatable
📥 数据源管理       ← /datasource
📤 结果管理         ← /record
🧩 已集成算法       ← /components（BFIA 模式）
```

### 6.3 Center 模式菜单

```
🏠 工作台           ← /
📦 节点注册         ← /node
📁 项目管理         ← /dag
```

### 6.4 用户下拉菜单

```
admin
节点: alice          ← 原 subTitle 信息
模式: Autonomy
─────────────────
🔗 切换协议          ← 隐语 / BFIA 互联
📖 帮助中心
🚪 退出登录
```

### 6.5 菜单项图标映射（@ant-design/icons）

| 菜单 | 图标 |
|------|------|
| 工作台 | HomeOutlined |
| 合作节点 | ApiOutlined |
| 我的项目 | FolderOutlined |
| 数据管理 | DatabaseOutlined |
| 数据源管理 | HddOutlined |
| 结果管理 | ExportOutlined |
| 已集成算法 | AppstoreOutlined |
| 消息中心 | BellOutlined |
| 节点注册 | ClusterOutlined |
| 项目管理 | FolderOutlined |

### 6.6 关键决策

1. **取消顶部协议切换**：原 Header 的"隐语/BFIA" Select 移入用户下拉菜单，默认根据部署模式自动选择
2. **"我的项目"统一入口**：BFIA 项目和隐语原生项目在同一列表，通过项目卡片上的 Tag 区分类型（`BFIA互联` / `原生协同`）
3. **消息中心位置**：从 Header 移至 Sider 底部，带红点角标
4. **菜单折叠态**：仅显示图标，Hover 显示 Tooltip 文字

### 6.7 路由变更

路由文件 `config/routes.ts` 结构不变，仅菜单配置在 `pages/edge.tsx` 和 `pages/new-home.tsx` 中调整：
- 合并 `isPrivacyComputeMenuItems` 和 `isBfiaMenuItems` 为统一菜单
- 菜单项根据 `platformType` 和协议状态动态显示/隐藏

## 7. 技术实现策略

### 7.1 修改文件清单

#### 品牌配置层

| 文件 | 修改内容 |
|------|----------|
| `src/platform.config.tsx` | `colorPrimary: '#08979c'`、`slogan: '让隐私计算，开放互联'`、`HomePageTitle` 换品牌名、`header.logo` 换新 Logo |
| `config/config.ts` | `title: '隐私计算开放互联平台'` |

#### Logo 资源

| 文件 | 操作 |
|------|------|
| `src/assets/logo.svg` | 替换为新的 `logo-compact.svg`（侧边栏用） |
| `src/assets/logo1.svg` | 替换为新的 `logo-full.svg`（登录页用） |
| `public/favicon.ico` | 替换为新 favicon |
| `src/assets/logo-compact.svg` | 新增，纯图形标识 |
| `src/assets/logo-full.svg` | 新增，图形 + 字标 |

#### 配色统一层

| 文件 | 操作 |
|------|------|
| `src/styles/variables.less` | 新建，定义 `@primary-color: #08979c`、`@sider-bg: #001529`、`@brand-gradient` 等变量 |
| `src/global.less` | 引入 variables.less，替换 `#0068fa`/`#1677ff` 硬编码 |
| 80+ 个 `.less` 文件 | 逐个将硬编码 `#0068fa`/`#1677ff` 替换为 `@primary-color` 变量 |

#### 布局重构层

| 文件 | 修改内容 |
|------|----------|
| `src/modules/layout/home-layout/header-view.tsx` | 移除顶部 Header，Logo/用户/消息/协议切换迁移到 Sider 或下拉菜单 |
| `src/modules/layout/home-layout/index.tsx` | 改为纯内容容器 |
| `src/modules/layout/management-layout/index.tsx` | 增强为深色 SaaS Sider：Logo 区 + 菜单 + 底部功能区（消息 + 用户下拉） |
| `src/modules/layout/management-layout/index.less` | 深色背景 `#001529`、主色选中态、折叠 60px/展开 220px |

#### 登录页重构

| 文件 | 修改内容 |
|------|----------|
| `src/modules/login/index.tsx` | 改为全屏渐变背景 + 居中毛玻璃卡片 |
| `src/modules/login/index.less` | 毛玻璃样式 `backdrop-filter: blur(20px)` |
| `src/modules/login/component/login-form/index.tsx` | 标题改"隐私计算开放互联平台"、Slogan 替换、表单输入框毛玻璃风格 |

#### 菜单与信息架构

| 文件 | 修改内容 |
|------|----------|
| `src/pages/edge.tsx` | 合并两套菜单为统一菜单，配图标 |
| `src/pages/new-home.tsx` | Center 模式菜单更新 |

### 7.2 实施顺序（6 个阶段）

1. **品牌资源层**：生成新 Logo SVG + favicon，替换品牌文案 → 可立即看到品牌变化
2. **配色变量层**：新建 variables.less，改 `colorPrimary`，批量替换硬编码 → 全站配色切换
3. **侧边栏布局**：重构 management-layout 为深色 SaaS Sider → 导航结构落地
4. **移除顶部 Header**：迁移 Header 元素到 Sider/下拉菜单 → 布局结构完成
5. **登录页重构**：毛玻璃卡片 + 渐变背景 → 登录体验升级
6. **页面视觉打磨**：首页、项目列表、DAG 编辑器、空状态等视觉规范落地 → 全站视觉统一

### 7.3 风险与缓解

| 风险 | 缓解 |
|------|------|
| 80+ 硬编码色值遗漏 | 用 Grep 全量扫描 `#0068fa`/`#1677ff`，逐文件替换验证 |
| 布局重构影响路由鉴权 | 路由结构和 wrappers 不变，仅替换布局组件渲染 |
| DAG 编辑器（x6）视觉改动 | x6 节点样式通过 GraphRegistry 注册，单独调整不影响业务逻辑 |
| 构建产物需同步到 Spring Boot | 前端构建后复制到 `secretpad-web/src/main/resources/static/` |

### 7.4 验证方式

- 前端独立构建：`pnpm build`，本地预览验证
- 集成验证：构建产物复制到 Spring Boot static 目录，重启 Alice/Bob 服务，浏览器全流程走查
