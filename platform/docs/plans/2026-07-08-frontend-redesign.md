# 隐私计算开放互联平台 - 前端 UI 重新设计实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 SecretPad 管理平台前端全面重设计为"隐私计算开放互联平台"，替换品牌名称、Logo、配色方案，重构布局为现代 SaaS 侧边栏风格，重构登录页为毛玻璃卡片风格。

**Architecture:** 前端源码在 `NewProject/secretpad-frontend/apps/platform`，技术栈 React 18 + UmiJS 4 + Ant Design 5 + Less。品牌配置集中在 `platform.config.tsx`，配色通过 antd ConfigProvider token + 80+ 处 less 硬编码实现。本计划分 6 个阶段：品牌资源 → 配色变量 → 侧边栏布局 → 移除 Header → 登录页 → 构建验证。

**Tech Stack:** React 18, UmiJS 4, Ant Design 5, Less, @ant-design/icons 5, @antv/x6 2

**Spec:** `docs/specs/2026-07-08-frontend-redesign-design.md`

**前端根目录（所有相对路径基于此）:** `NewProject/secretpad-frontend/apps/platform`

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/assets/logo-compact.svg` | 新建 | 侧边栏/折叠态 Logo（纯图形） |
| `src/assets/logo-full.svg` | 新建 | 登录页 Logo（图形+字标） |
| `src/assets/logo.svg` | 替换 | 指向 logo-compact.svg 内容（兼容现有 import） |
| `src/assets/logo1.svg` | 替换 | 指向 logo-full.svg 内容（兼容现有 import） |
| `public/favicon.ico` | 替换 | 浏览器标签图标 |
| `src/styles/variables.less` | 新建 | 全局 Less 配色变量定义 |
| `src/platform.config.tsx` | 修改 | 主色、Slogan、HomePageTitle、Logo 引用 |
| `config/config.ts` | 修改 | title |
| `src/global.less` | 修改 | 引入 variables.less，替换硬编码 |
| `src/modules/layout/management-layout/index.tsx` | 修改 | 深色 SaaS Sider（Logo+菜单+底部功能区） |
| `src/modules/layout/management-layout/index.less` | 修改 | 深色背景、主色选中态、220px/60px |
| `src/modules/layout/home-layout/index.tsx` | 修改 | 移除 Header，纯内容容器 |
| `src/modules/layout/home-layout/header-view.tsx` | 修改 | 功能迁移到 Sider/下拉菜单 |
| `src/modules/login/index.tsx` | 修改 | 全屏渐变背景+毛玻璃卡片 |
| `src/modules/login/index.less` | 修改 | 毛玻璃样式 |
| `src/modules/login/component/login-form/index.tsx` | 修改 | 品牌名、Slogan、毛玻璃输入框 |
| `src/modules/login/component/login-form/index.less` | 修改 | 毛玻璃输入框样式 |
| 51 个 `.less` 文件 | 修改 | 替换 `#0068fa`/`#1677ff` 为 `@primary-color` |

---

## Task 1: 生成新 Logo SVG 文件

**Files:**
- Create: `src/assets/logo-compact.svg`
- Create: `src/assets/logo-full.svg`

- [ ] **Step 1: 创建 logo-compact.svg（纯图形标识）**

文件路径：`NewProject/secretpad-frontend/apps/platform/src/assets/logo-compact.svg`

```svg
<svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="logoGradient" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#08979c"/>
      <stop offset="100%" style="stop-color:#13c2c5"/>
    </linearGradient>
  </defs>
  <!-- 互联节点三角拓扑 -->
  <circle cx="20" cy="8" r="5" fill="url(#logoGradient)"/>
  <circle cx="8" cy="28" r="5" fill="url(#logoGradient)"/>
  <circle cx="32" cy="28" r="5" fill="url(#logoGradient)"/>
  <!-- 连线 -->
  <path d="M20 8 L8 28" stroke="#13c2c5" stroke-width="1.5" stroke-linecap="round" opacity="0.6"/>
  <path d="M20 8 L32 28" stroke="#13c2c5" stroke-width="1.5" stroke-linecap="round" opacity="0.6"/>
  <path d="M8 28 L32 28" stroke="#13c2c5" stroke-width="1.5" stroke-linecap="round" opacity="0.6"/>
  <!-- 中心互联点 -->
  <circle cx="20" cy="21" r="2.5" fill="#fff" stroke="#08979c" stroke-width="1.5"/>
</svg>
```

- [ ] **Step 2: 创建 logo-full.svg（图形+字标）**

文件路径：`NewProject/secretpad-frontend/apps/platform/src/assets/logo-full.svg`

```svg
<svg width="280" height="56" viewBox="0 0 280 56" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="logoFullGradient" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#08979c"/>
      <stop offset="100%" style="stop-color:#13c2c5"/>
    </linearGradient>
  </defs>
  <!-- 图形标识 -->
  <circle cx="24" cy="12" r="6" fill="url(#logoFullGradient)"/>
  <circle cx="8" cy="36" r="6" fill="url(#logoFullGradient)"/>
  <circle cx="40" cy="36" r="6" fill="url(#logoFullGradient)"/>
  <path d="M24 12 L8 36" stroke="#13c2c5" stroke-width="2" stroke-linecap="round" opacity="0.6"/>
  <path d="M24 12 L40 36" stroke="#13c2c5" stroke-width="2" stroke-linecap="round" opacity="0.6"/>
  <path d="M8 36 L40 36" stroke="#13c2c5" stroke-width="2" stroke-linecap="round" opacity="0.6"/>
  <circle cx="24" cy="26" r="3" fill="#fff" stroke="#08979c" stroke-width="2"/>
  <!-- 字标 -->
  <text x="56" y="28" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="16" font-weight="bold" fill="#001529">隐私计算开放互联平台</text>
  <text x="56" y="44" font-family="Arial, sans-serif" font-size="9" fill="#08979c" opacity="0.7">Open Interconnection Platform</text>
</svg>
```

- [ ] **Step 3: 复制内容到 logo.svg 和 logo1.svg（兼容现有 import）**

将 `logo-compact.svg` 内容复制到 `src/assets/logo.svg`（Header/侧边栏用）。
将 `logo-full.svg` 内容复制到 `src/assets/logo1.svg`（登录页用）。

- [ ] **Step 4: Commit**

```bash
cd NewProject/secretpad-frontend
git add apps/platform/src/assets/logo-compact.svg apps/platform/src/assets/logo-full.svg apps/platform/src/assets/logo.svg apps/platform/src/assets/logo1.svg
git commit -m "feat: add new logo SVG assets for privacy computing interconnection platform"
```

---

## Task 2: 更新品牌文案和 favicon

**Files:**
- Modify: `src/platform.config.tsx`
- Modify: `config/config.ts`
- Modify: `public/favicon.ico`

- [ ] **Step 1: 修改 platform.config.tsx**

文件：`NewProject/secretpad-frontend/apps/platform/src/platform.config.tsx`

```tsx
import { ReactComponent as Logo } from '@/assets/logo-compact.svg';

const hour = new Date().getHours();
let time = '';
if (hour < 12) {
  time = '上午';
} else if (hour > 18) {
  time = '晚上';
} else if (hour >= 12) {
  time = '下午';
}

export default {
  theme: {
    token: {
      colorPrimary: '#08979c',
    },
  },
  slogan: '让隐私计算，开放互联',
  header: {
    logo: <Logo />,
    rightLinks: true,
  },
  createProject: {
    showTemplate: true,
  },
  home: {
    HomePageTitle: `${time}好，欢迎来到隐私计算开放互联平台`,
  },
  guide: true,
};
```

- [ ] **Step 2: 修改 config.ts title**

文件：`NewProject/secretpad-frontend/apps/platform/config/config.ts`

将第 33 行 `title: '隐语开放平台'` 改为 `title: '隐私计算开放互联平台'`

- [ ] **Step 3: 替换 favicon.ico**

使用 logo-compact.svg 生成 favicon.ico。如果没有 ICO 转换工具，用以下命令（需要 ImageMagick）：

```bash
# 如果有 ImageMagick
convert -background none -define icon:auto-resize=32,16 NewProject/secretpad-frontend/apps/platform/src/assets/logo-compact.svg NewProject/secretpad-frontend/apps/platform/public/favicon.ico
# 如果没有 ImageMagick，手动用在线工具或保留原 favicon，后续替换
```

- [ ] **Step 4: Commit**

```bash
cd NewProject/secretpad-frontend
git add apps/platform/src/platform.config.tsx apps/platform/config/config.ts apps/platform/public/favicon.ico
git commit -m "feat: update brand name, slogan, theme color to privacy computing interconnection platform"
```

---

## Task 3: 新建 variables.less 配色变量文件

**Files:**
- Create: `src/styles/variables.less`

- [ ] **Step 1: 创建 variables.less**

文件：`NewProject/secretpad-frontend/apps/platform/src/styles/variables.less`

```less
// 隐私计算开放互联平台 - 全局配色变量
// 修改此文件即可全站换色

// 主色系（互联青）
@primary-color: #08979c;
@primary-color-light: #13c2c5;
@primary-color-lighter: #e6fffb;
@primary-color-dark: #006d75;

// 功能色
@success-color: #52c41a;
@warning-color: #faad14;
@error-color: #ff4d4f;
@info-color: @primary-color;

// 中性色
@sider-bg: #001529;
@sider-hover-bg: #112545;
@sider-selected-bg: @primary-color;
@content-bg: #f5f7fa;
@card-bg: #ffffff;
@text-primary: #1f2937;
@text-secondary: #6b7280;
@text-disabled: #d1d5db;
@border-color: #e5e7eb;

// 品牌渐变
@brand-gradient: linear-gradient(135deg, #08979c 0%, #13c2c5 100%);
```

- [ ] **Step 2: Commit**

```bash
cd NewProject/secretpad-frontend
git add apps/platform/src/styles/variables.less
git commit -m "feat: add global less color variables for unified theme management"
```

---

## Task 4: 修改 global.less 引入变量并替换硬编码

**Files:**
- Modify: `src/global.less`

- [ ] **Step 1: 修改 global.less**

文件：`NewProject/secretpad-frontend/apps/platform/src/global.less`

```less
@import './styles/variables.less';

html,
body {
  height: 100%;
  padding: 0;
  margin: 0;
}

// drawer 关闭按钮在右侧显示
.ant-drawer {
  .ant-drawer-content-wrapper {
    .ant-drawer-content {
      .ant-drawer-wrapper-body {
        .ant-drawer-header-title {
          flex-direction: row-reverse;

          .ant-drawer-close {
            font-size: 12px;
            margin-inline-end: 0;
          }
        }
      }
    }
  }
}

#root,
#root-master {
  min-width: 1024px;
  height: 100%;
}

a {
  color: @primary-color;
}
```

- [ ] **Step 2: Commit**

```bash
cd NewProject/secretpad-frontend
git add apps/platform/src/global.less
git commit -m "refactor: import variables.less in global.less, replace hardcoded #1677ff"
```

---

## Task 5: 批量替换 51 个 less 文件中的硬编码色值

**Files:**
- Modify: 51 个 `.less` 文件（见下方列表）

- [ ] **Step 1: 在每个 less 文件顶部添加 variables.less 引入**

对于以下 51 个文件，在文件第一行添加 `@import '../../styles/variables.less';`（路径根据文件深度调整）：

需要修改的文件列表（路径相对于 `src/`）：
```
modules/create-project/add-node-tag.less
modules/create-project/template.less
modules/create-project/index.less
modules/create-project/p2p-create-project/index.less
components/vote-insts-graph/index.less
components/popover-copy/index.less
components/switch-card/index.less
modules/component-tree-connectivity/index.less
modules/component-tree/index.less
modules/managed-node-list/node-info/index.less
modules/data-table-tree/index.less
modules/project-list/index.less
modules/p2p-project-list/components/index.less
modules/p2p-project-list/components/auth-project-tag.less
modules/p2p-project-list/index.less
modules/data-table-add/component/httpQueryExample/index.less
modules/data-table-info/data-table-auth/safe-setting-modal.tsx/index.less
modules/data-table-add/component/dataTableStructure/index.less
modules/dag-result-connectivity/index.less
modules/dag-result/index.less
modules/dag-result/vis/groupby-pivot-table/index.less
modules/dag-result/vis/corr-matrix/index.less
modules/dag-result/vis/output-table/index.less
modules/dag-result/vis/mpc-pva-chart/index.less
modules/connectivity/p2p-project-list/components/index.less
modules/connectivity/p2p-project-list/index.less
modules/connectivity/my-data-manager/component/httpQueryExample/index.less
modules/connectivity/my-data-manager/component/dataTableStructure/index.less
modules/data-source-list/components/node-list/index.less
modules/main-dag-connectivity/index.less
modules/main-dag/index.less
modules/message-center/message-info/index.less
modules/message-center/component/index.less
modules/model-manager/model-release/index.less
modules/model-manager/model-info/index.less
modules/my-node/index.less
modules/my-node/refreshToken/index.less
modules/managed-node/index.less
modules/guide-node/node.less
modules/bfia-component-list/bfia-preview-canvas.less
modules/pipeline/index.less
modules/advanced-config/index.less
modules/layout/management-layout/index.less
modules/layout/dag-layout/index.less
modules/layout/dag-layout-connectivity/index.less
modules/component-config-connectivity/config-item-render/custom-render/linear-model-parameters-modification/toolbar/index.less
modules/component-config-connectivity/config-item-render/custom-render/binning-modification/toolbar/index.less
modules/component-config/config-item-render/custom-render/upstream-feature-render/index.less
modules/component-config/config-item-render/custom-render/binning-modification/toolbar/index.less
modules/component-config/config-item-render/custom-render/linear-model-parameters-modification/toolbar/index.less
```

**注意：** `@import` 路径需根据文件深度调整。例如：
- `src/modules/xxx/index.less` → `@import '../../../styles/variables.less';`（3 层深）
- `src/modules/xxx/yyy/index.less` → `@import '../../../../styles/variables.less';`（4 层深）
- `src/components/xxx/index.less` → `@import '../../../styles/variables.less';`（3 层深）
- `src/modules/layout/xxx/index.less` → `@import '../../../../styles/variables.less';`（4 层深）

- [ ] **Step 2: 将所有 `#0068fa` 替换为 `@primary-color`**

在每个文件中，将所有 `#0068fa`（不区分大小写）替换为 `@primary-color`。

- [ ] **Step 3: 将所有 `#1677ff` 替换为 `@primary-color`**

在每个文件中，将所有 `#1677ff`（不区分大小写）替换为 `@primary-color`。

- [ ] **Step 4: 验证无残留硬编码**

运行：
```bash
cd NewProject/secretpad-frontend/apps/platform
grep -rn "#0068fa\|#1677ff" src/ --include="*.less" | grep -v "variables.less"
```
Expected: 无输出（所有硬编码已替换）

- [ ] **Step 5: Commit**

```bash
cd NewProject/secretpad-frontend
git add apps/platform/src/
git commit -m "refactor: replace all hardcoded #0068fa/#1677ff with @primary-color variable across 51 less files"
```

---

## Task 6: 重构 management-layout 为深色 SaaS Sider

**Files:**
- Modify: `src/modules/layout/management-layout/index.tsx`
- Modify: `src/modules/layout/management-layout/index.less`

- [ ] **Step 1: 重构 index.less 为深色主题**

文件：`NewProject/secretpad-frontend/apps/platform/src/modules/layout/management-layout/index.less`

```less
@import '../../../../styles/variables.less';

.layoutContainer {
  display: flex;
  height: 100%;

  .menuContainer {
    display: flex;
    height: 100%;
    flex-direction: column;
    background-color: @sider-bg;
    transition: width 0.3s cubic-bezier(0.2, 0, 0, 1) 0s;

    :global {
      .ant-menu {
        width: 100%;
        background-color: transparent;
        border-inline-end: none;
        color: rgba(255, 255, 255, 0.65);
      }

      .ant-menu-item {
        color: rgba(255, 255, 255, 0.65);

        &:hover {
          color: #fff;
          background-color: @sider-hover-bg;
        }

        &.ant-menu-item-selected {
          color: #fff;
          background-color: @sider-selected-bg;
        }
      }

      .ant-menu-submenu-title {
        color: rgba(255, 255, 255, 0.65);

        &:hover {
          color: #fff;
          background-color: @sider-hover-bg;
        }
      }
    }
  }

  .siderHeader {
    height: 64px;
    display: flex;
    align-items: center;
    padding: 0 16px;
    color: #fff;

    .siderLogo {
      width: 32px;
      height: 32px;
      flex-shrink: 0;
    }

    .siderTitle {
      margin-left: 12px;
      font-size: 14px;
      font-weight: 600;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
    }
  }

  .menuWrapper {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
  }

  .siderFooter {
    padding: 8px 0;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
  }

  .unfold {
    width: 220px;

    .siderTitle {
      display: block;
    }
  }

  .fold {
    width: 60px;

    .siderTitle {
      display: none;
    }
  }

  .contentContainer {
    overflow: scroll;
    flex: 1;
    background-color: @content-bg;
    padding: 24px;
  }

  .workbenchContentContainer {
    overflow: auto;
    background-color: transparent;
    padding: 0;
  }

  .hide {
    display: none;
  }

  .collapseInfo {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 8px;
    color: rgba(255, 255, 255, 0.65);
    font-size: 12px;
    cursor: pointer;

    &:hover {
      color: #fff;
    }
  }
}
```

- [ ] **Step 2: 重构 index.tsx 添加 Logo 区和底部功能区**

文件：`NewProject/secretpad-frontend/apps/platform/src/modules/layout/management-layout/index.tsx`

在现有 `ManagementLayoutComponent` 中，在 `<div className={styles.menuContainer}>` 内部，`<Menu>` 之前添加 Logo 区，`<Menu>` 之后保留折叠按钮。

修改 `menuContainer` 内部结构为：

```tsx
import { MenuUnfoldOutlined, MenuFoldOutlined } from '@ant-design/icons';
import { useKeyPress } from 'ahooks';
import { Menu } from 'antd';
import classnames from 'classnames';
import { parse, stringify } from 'query-string';
import { useEffect, useState } from 'react';
import { history, useLocation } from 'umi';

import { ReactComponent as Logo } from '@/assets/logo-compact.svg';
import { isWindows } from '@/util/platform';

import styles from './index.less';
import { DefaultModalManager } from '@/modules/dag-modal-manager';
import { useModel } from '@/util/valtio-helper';

export enum tabComponentType {
  FLOW = 'flow',
}

type MenuItem = {
  label: string;
  icon: React.ReactNode;
  component: React.ReactNode;
  key: string;
  children?: MenuItem[];
};

type ManagementLayoutComponentProps = {
  menuItems: MenuItem[];
  defaultTabKey?: string;
};

const findMenuComponent = (
  items: MenuItem[],
  key?: string,
): React.ReactNode | undefined => {
  for (const item of items) {
    if (item.key === key) return item.component;
    if (item.children) {
      const found = findMenuComponent(item.children, key);
      if (found !== undefined) return found;
    }
  }
  return undefined;
};

export const foldHotKey = {
  key: isWindows ? 'ctrl.uparrow' : 'meta.ctrl.uparrow',
  text: isWindows ? 'Ctrl + ↑' : '⌘ + ctrl + ↑ ',
};

export const ManagementLayoutComponent = (props: ManagementLayoutComponentProps) => {
  const modalManager = useModel(DefaultModalManager);

  const { menuItems, defaultTabKey } = props;
  const [collapsed, setCollapsed] = useState(false);

  const { pathname, search } = useLocation();
  const parsedSearch = parse(search);

  const { tab, ownerId } = parsedSearch as { tab?: string; ownerId?: string };
  const [tabKey, setTabKey] = useState<string>();

  useEffect(() => {
    history.replace({
      pathname: pathname === '/' ? '/home' : pathname,
      search: stringify(
        ownerId
          ? {
              ...parsedSearch,
              ownerId,
              tab: tab || defaultTabKey,
            }
          : { tab: tab || defaultTabKey },
      ),
    });
  }, [defaultTabKey, tab]);

  useEffect(() => {
    setTabKey(tab || defaultTabKey);
  }, [tab]);

  const [collapseInfo, setCollapsedInfo] = useState(`收起/展开 ${foldHotKey.text}`);
  const toggleCollapsed = () => {
    setCollapsed(!collapsed);
  };

  useEffect(() => {
    if (!collapsed) {
      setTimeout(() => setCollapsedInfo(`收起/展开 ${foldHotKey.text}`), 250);
    } else {
      setCollapsedInfo(``);
    }
  }, [collapsed]);

  useKeyPress([foldHotKey.key], (event) => {
    event.preventDefault();
    event.stopPropagation();
    toggleCollapsed();
  });

  const closeAllModal = () => {
    modalManager.closeAllModals();
  };

  return (
    <div className={styles.layoutContainer}>
      <div
        className={classnames(
          styles.menuContainer,
          collapsed ? styles.fold : styles.unfold,
        )}
      >
        {/* Logo 区 */}
        <div className={styles.siderHeader}>
          <Logo className={styles.siderLogo} />
          {!collapsed && <span className={styles.siderTitle}>开放互联平台</span>}
        </div>

        {/* 菜单区 */}
        <div className={styles.menuWrapper}>
          <Menu
            theme="dark"
            selectedKeys={[tabKey as string]}
            mode="inline"
            inlineCollapsed={collapsed}
            items={menuItems}
            onSelect={({ key }) => {
              closeAllModal();
              history.replace({
                pathname: pathname === '/' ? '/home' : pathname,
                search: stringify(ownerId ? { ownerId, tab: key } : { tab: key }),
              });
            }}
          />
        </div>

        {/* 折叠按钮 */}
        <div className={styles.collapseInfo}>
          <div onClick={toggleCollapsed}>
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </div>
        </div>
      </div>

      <div
        className={classnames(styles.contentContainer, {
          [styles.workbenchContentContainer]: tabKey === 'workbench',
        })}
      >
        {findMenuComponent(menuItems, tabKey)}
      </div>
    </div>
  );
};
```

- [ ] **Step 3: 构建验证**

```bash
cd NewProject/secretpad-frontend
pnpm --filter platform build 2>&1 | tail -20
```
Expected: 构建成功，无报错

- [ ] **Step 4: Commit**

```bash
cd NewProject/secretpad-frontend
git add apps/platform/src/modules/layout/management-layout/
git commit -m "feat: redesign management-layout as dark SaaS sidebar with logo, dark theme menu, fold toggle"
```

---

## Task 7: 重构 home-layout 移除顶部 Header

**Files:**
- Modify: `src/modules/layout/home-layout/index.tsx`
- Modify: `src/modules/layout/home-layout/index.less`

- [ ] **Step 1: 修改 home-layout/index.tsx 移除 Header**

文件：`NewProject/secretpad-frontend/apps/platform/src/modules/layout/home-layout/index.tsx`

将 Header 组件移除，改为纯内容容器。原有的 Header 功能（Logo、用户菜单、消息、协议切换）已由 management-layout 的 Sider 承载。

```tsx
import { ShowMenuContext, Portal } from '@secretflow/dag';
import classnames from 'classnames';
import type { ReactNode } from 'react';

import { useModel } from '@/util/valtio-helper';

import { HomeLayoutService } from './home-layout.service';
import styles from './index.less';

export const HomeLayout = ({ children }: { children: ReactNode }) => {
  const layoutService = useModel(HomeLayoutService);
  const { bgClassName } = layoutService;
  const X6ReactPortalProvider = Portal.getProvider();
  return (
    <div className={classnames(styles.home, styles[bgClassName])}>
      <ShowMenuContext.Provider value={false}>
        <X6ReactPortalProvider />
      </ShowMenuContext.Provider>
      <div className={styles.content}>{children}</div>
    </div>
  );
};
```

- [ ] **Step 2: 修改 home-layout/index.less 移除 header 样式**

文件：`NewProject/secretpad-frontend/apps/platform/src/modules/layout/home-layout/index.less`

移除 `.header` 相关样式，保留 `.home` 和 `.content`。

```less
.home {
  height: 100%;

  .content {
    height: 100%;
    overflow: auto;
  }
}
```

- [ ] **Step 3: 构建验证**

```bash
cd NewProject/secretpad-frontend
pnpm --filter platform build 2>&1 | tail -20
```
Expected: 构建成功。注意：`header-view.tsx` 仍保留但不再被 `index.tsx` 引用，其功能（用户下拉、消息、协议切换）需在后续 Task 中迁移到 management-layout 或用户下拉菜单。如果构建报 unused import 警告，可忽略。

- [ ] **Step 4: Commit**

```bash
cd NewProject/secretpad-frontend
git add apps/platform/src/modules/layout/home-layout/
git commit -m "refactor: remove top header from home-layout, content now full-width"
```

---

## Task 8: 重构登录页为毛玻璃卡片

**Files:**
- Modify: `src/modules/login/index.tsx`
- Modify: `src/modules/login/index.less`
- Modify: `src/modules/login/component/login-form/index.tsx`
- Modify: `src/modules/login/component/login-form/index.less`

- [ ] **Step 1: 重构 login/index.tsx**

文件：`NewProject/secretpad-frontend/apps/platform/src/modules/login/index.tsx`

改为全屏渐变背景 + 居中毛玻璃卡片。

```tsx
import { message } from 'antd';
import React from 'react';
import { history } from 'umi';

import { ReactComponent as Logo } from '@/assets/logo-compact.svg';
import { Platform } from '@/components/platform-wrapper';
import { DefaultComponentInterpreterService } from '@/modules/component-interpreter/component-interpreter-service';
import { DefaultModalManager } from '@/modules/dag-modal-manager';
import platformConfig from '@/platform.config';
import { getModel, Model, useModel } from '@/util/valtio-helper';

import { LoginForm } from './component/login-form';
import type { UserInfo } from './component/login-form';
import styles from './index.less';
import type { User } from './login.service';
import { LoginService } from './login.service';

export const LoginComponent: React.FC = () => {
  const loginModel = useModel(LoginModel);
  return (
    <div className={styles.loginPage}>
      {/* 背景装饰 */}
      <div className={styles.bgDecorationLeft} />
      <div className={styles.bgDecorationRight} />

      {/* 毛玻璃登录卡片 */}
      <div className={styles.glassCard}>
        <div className={styles.logoArea}>
          <Logo className={styles.logo} />
        </div>
        <h1 className={styles.platformTitle}>隐私计算开放互联平台</h1>
        <p className={styles.slogan}>让隐私计算，开放互联</p>
        <LoginForm onConfirm={loginModel.loginConfirm} />
      </div>

      {/* 页脚 */}
      <div className={styles.footer}>
        Privacy Computing Open Interconnection Platform
      </div>
    </div>
  );
};

export class LoginModel extends Model {
  token = '';
  loginService = getModel(LoginService);
  interpreterService = getModel(DefaultComponentInterpreterService);
  modalManager = getModel(DefaultModalManager);

  onViewMount(): void {
    this.modalManager.closeAllModals();
  }

  loginConfirm = async (loginFields: UserInfo) => {
    const { status, data } = await this.loginService.login({
      name: loginFields.name,
      password: loginFields.password,
    });

    const notFirstTimeIn = localStorage.getItem('notFirstTimeIn');
    this.token = data?.token || '';
    this.loginService.userInfo = data as User;
    if (status?.code === 0) {
      localStorage.setItem('User-Token', this.token);
      if (this.loginService.userInfo.platformType === Platform.AUTONOMY) {
        if (this.loginService.userInfo.ownerId) {
          localStorage.setItem('neverLogined', 'true');
          history.push(`/edge?ownerId=${this.loginService.userInfo.ownerId}`);
          message.success('登录成功');
          this.interpreterService.getComponentI18n();
          return;
        }
      }

      if (this.loginService.userInfo.platformType === Platform.EDGE) {
        if (this.loginService.userInfo.ownerId) {
          localStorage.setItem('neverLogined', 'true');
          history.push(`/node?ownerId=${this.loginService.userInfo.ownerId}`);
        }
      } else {
        localStorage.setItem('neverLogined', 'true');
        if (notFirstTimeIn || !platformConfig.guide) {
          history.push('/');
        } else {
          if (
            this.loginService.userInfo.platformType === Platform.CENTER &&
            this.loginService.userInfo?.ownerType === 'EDGE'
          ) {
            history.push('/');
          } else {
            history.push('/guide');
          }
          localStorage.setItem('notFirstTimeIn', 'true');
        }
      }
      message.success('登录成功');
      this.interpreterService.getComponentI18n();
    } else {
      message.error(status?.msg || '登录失败，请检查用户名或密码');
    }
  };
}
```

- [ ] **Step 2: 重构 login/index.less**

文件：`NewProject/secretpad-frontend/apps/platform/src/modules/login/index.less`

```less
.loginPage {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  background: linear-gradient(135deg, #08979c 0%, #0050b3 100%);
  position: relative;
  overflow: hidden;
}

.bgDecorationLeft {
  position: absolute;
  bottom: -100px;
  left: -100px;
  width: 400px;
  height: 400px;
  opacity: 0.08;
  background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="20" r="12" fill="white"/><circle cx="20" cy="70" r="12" fill="white"/><circle cx="80" cy="70" r="12" fill="white"/><path d="M50 20 L20 70 M50 20 L80 70 M20 70 L80 70" stroke="white" stroke-width="2" opacity="0.6"/></svg>');
  background-repeat: no-repeat;
  background-size: contain;
}

.bgDecorationRight {
  position: absolute;
  top: -100px;
  right: -100px;
  width: 400px;
  height: 400px;
  opacity: 0.08;
  background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="20" r="12" fill="white"/><circle cx="20" cy="70" r="12" fill="white"/><circle cx="80" cy="70" r="12" fill="white"/><path d="M50 20 L20 70 M50 20 L80 70 M20 70 L80 70" stroke="white" stroke-width="2" opacity="0.6"/></svg>');
  background-repeat: no-repeat;
  background-size: contain;
}

.glassCard {
  width: 420px;
  padding: 40px;
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  z-index: 1;
}

.logoArea {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;

  .logo {
    width: 48px;
    height: 48px;
  }
}

.platformTitle {
  color: #fff;
  font-size: 18px;
  font-weight: 600;
  text-align: center;
  margin: 0 0 8px 0;
}

.slogan {
  color: rgba(255, 255, 255, 0.7);
  font-size: 13px;
  text-align: center;
  margin: 0 0 32px 0;
}

.footer {
  position: absolute;
  bottom: 24px;
  color: rgba(255, 255, 255, 0.5);
  font-size: 11px;
  text-align: center;
}
```

- [ ] **Step 3: 重构 login-form/index.tsx**

文件：`NewProject/secretpad-frontend/apps/platform/src/modules/login/component/login-form/index.tsx`

```tsx
import { Form, Button, Input } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useState } from 'react';

import styles from './index.less';

export interface UserInfo {
  name: string;
  password: string;
}

export const LoginForm = (props: {
  onConfirm: (userInfo: UserInfo) => Promise<void>;
}) => {
  const [loginState, setLoginState] = useState(false);

  const onFinish = async (values: UserInfo) => {
    setLoginState(true);
    await props.onConfirm(values);
    setLoginState(false);
  };

  return (
    <Form
      name="basic"
      initialValues={{ remember: true }}
      onFinish={onFinish}
      autoComplete="off"
    >
      <Form.Item
        label=""
        name="name"
        rules={[{ required: true, message: '请输入您的账号' }]}
      >
        <Input
          className={styles.loginInput}
          size="large"
          placeholder="请输入您的账号"
          prefix={<UserOutlined style={{ color: 'rgba(255,255,255,0.5)' }} />}
        />
      </Form.Item>

      <Form.Item
        label=""
        name="password"
        rules={[{ required: true, message: '请输入密码' }]}
      >
        <Input.Password
          className={styles.loginInput}
          size="large"
          placeholder="请输入密码"
          prefix={<LockOutlined style={{ color: 'rgba(255,255,255,0.5)' }} />}
        />
      </Form.Item>

      <Form.Item>
        <Button
          className={styles.loginBtn}
          size="large"
          htmlType="submit"
          loading={loginState}
          block
        >
          登录
        </Button>
      </Form.Item>
    </Form>
  );
};
```

- [ ] **Step 4: 重构 login-form/index.less**

文件：`NewProject/secretpad-frontend/apps/platform/src/modules/login/component/login-form/index.less`

```less
.loginInput {
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 8px;
  color: #fff;

  &::placeholder {
    color: rgba(255, 255, 255, 0.5);
  }

  &:hover,
  &:focus {
    border-color: rgba(255, 255, 255, 0.6);
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.1);
  }
}

.loginBtn {
  background: #fff;
  color: #08979c;
  font-weight: 600;
  border: none;
  border-radius: 8px;
  height: 44px;

  &:hover {
    background: #fff;
    color: #08979c;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }
}
```

- [ ] **Step 5: 构建验证**

```bash
cd NewProject/secretpad-frontend
pnpm --filter platform build 2>&1 | tail -20
```
Expected: 构建成功

- [ ] **Step 6: Commit**

```bash
cd NewProject/secretpad-frontend
git add apps/platform/src/modules/login/
git commit -m "feat: redesign login page with glassmorphism card and gradient background"
```

---

## Task 9: 构建验证和产物同步

**Files:**
- 无新文件修改，仅构建和同步

- [ ] **Step 1: 全量构建前端**

```bash
cd NewProject/secretpad-frontend
pnpm install
pnpm --filter platform build
```
Expected: 构建成功，产物在 `apps/platform/dist/`

- [ ] **Step 2: 同步构建产物到 Spring Boot static 目录**

```bash
# 清空旧产物
rm -rf NewProject/secretpad/secretpad-web/src/main/resources/static/*

# 复制新产物
cp -r NewProject/secretpad-frontend/apps/platform/dist/* NewProject/secretpad/secretpad-web/src/main/resources/static/

# 验证 index.html title 已更新
grep "隐私计算开放互联平台" NewProject/secretpad/secretpad-web/src/main/resources/static/index.html
```
Expected: 输出包含 `<title>隐私计算开放互联平台</title>`

- [ ] **Step 3: 验证 favicon 已更新**

```bash
ls -la NewProject/secretpad/secretpad-web/src/main/resources/static/favicon.ico
```
Expected: 文件存在

- [ ] **Step 4: Commit 产物同步**

```bash
cd NewProject
git add secretpad/secretpad-web/src/main/resources/static/
git commit -m "build: sync frontend build artifacts to spring boot static resources"
```

- [ ] **Step 5: 重启 Alice 服务并视觉验证**

```bash
# 重启 Alice（使用最新 JAR，static 资源已打包进 JAR）
kill $(lsof -tiTCP:18080 -sTCP:LISTEN) 2>/dev/null
cd NewProject/secretpad
nohup /usr/bin/java -jar target/secretpad.jar \
  --server.http-port=18080 --server.http-port-inner=19001 --server.port=18443 \
  --secretpad.logs.path=/tmp/secretpad-logs/alice --secretpad.node-id=alice \
  --secretpad.bfia.crossnode.enabled=true \
  --SECRETPAD_ALICE_HTTP_ADDRESS=localhost:18080 --SECRETPAD_BOB_HTTP_ADDRESS=localhost:28080 \
  --KUSCIA_API_LITE_ALICE_ADDRESS=192.168.117.2:8084 --KUSCIA_API_LITE_BOB_ADDRESS=192.168.117.3:8084 \
  > /tmp/alice-startup.log 2>&1 &
```

等待 30 秒后访问 http://127.0.0.1:18080 验证：
- 浏览器标签标题为"隐私计算开放互联平台"
- 登录页为毛玻璃卡片 + 互联青渐变背景
- 登录后侧边栏为深色 SaaS 风格
- 主色调为互联青 `#08979c`

---

## Self-Review

### Spec Coverage

| Spec 章节 | 对应 Task |
|-----------|-----------|
| 1. 品牌系统 | Task 1 (Logo) + Task 2 (品牌文案) |
| 2. 配色系统 | Task 3 (variables.less) + Task 4 (global.less) + Task 5 (批量替换) |
| 3. 布局结构 | Task 6 (management-layout Sider) + Task 7 (移除 Header) |
| 4. 登录页设计 | Task 8 (毛玻璃卡片) |
| 5. 关键页面视觉规范 | 部分在 Task 6（Sider 样式），其余依赖 antd theme token 自动继承 |
| 6. 信息架构与菜单 | Task 6（菜单 theme="dark"），菜单合并依赖现有 edge.tsx 逻辑 |
| 7. 技术实现策略 | Task 1-8 全覆盖 + Task 9 构建验证 |

### Placeholder Scan

无占位符。所有代码步骤包含完整代码。

### Type Consistency

- `@primary-color` 变量在 Task 3 定义，Task 4/5/6 使用，命名一致
- Logo import 路径 `@/assets/logo-compact.svg` 在 Task 2（platform.config.tsx）、Task 6（management-layout）、Task 8（login）使用，一致
- 深色 Menu 使用 `theme="dark"`，与 antd5 API 一致

### Gaps

- Spec 6.4 用户下拉菜单（协议切换、节点信息）迁移：当前 header-view.tsx 的用户下拉逻辑较复杂，Task 7 移除了 Header 但未完整迁移用户下拉到 Sider。这是一个已知 gap，建议作为后续迭代 Task。当前 management-layout 的 Sider 底部仅有折叠按钮，用户菜单暂通过保留的页面内组件访问。
- Spec 5.2/5.3/5.4 首页/项目列表/DAG 编辑器视觉打磨：依赖 antd theme token 自动继承主色，但卡片网格、统计卡等具体布局需后续迭代。
