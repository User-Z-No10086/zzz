# 用 GitHub Desktop 发布本仓库

## 0. 先决条件

- 安装 GitHub Desktop：https://desktop.github.com/download/
- 有一个 GitHub 账号（**请用浏览器授权登录，不要在任何地方输入密码给我们**）

## 1. 把本目录加进 GitHub Desktop

1. 解压 `下山的人-本体代码.zip` 到任意位置，例如 `D:\code\xiashan-code`
2. 打开 GitHub Desktop → 菜单 **File → Add local repository…**
3. 选择上面那个目录（**选文件夹，不要选 zip**）
4. 如果提示“这不是一个 Git 仓库”，点 **create a repository** → 确认路径 → Create
   - 仓库名建议：`xiashan`（小写、无空格）
   - Description 可填：把知识讲给 AI 娘听的教学视觉小说

## 2. 首次发布

1. 右上角 **Publish repository**
2. 取消勾选 **Keep this code private**（想公开的话）
3. 点 **Publish repository**

之后仓库地址会出现在 Repository → Repository menu → "View on GitHub"。

## 3. 以后改了代码

```
Changes（左侧）→ 填一句 summary → Commit to main → Push origin
```

`.gitignore` 已经把运行时产物挡掉了（`game/saves/`、`*.rpyc`、`log.txt`、`shots/` 等），
所以左侧 Changes 里只会出现你真正改过的文件。

> 注意：`game/gui/`、`game/fonts/`、`game/images/` 是被忽略的——它们是运行
> `tools/bootstrap.py` 从 SDK 复制/生成的二进制素材，不该进仓库。

## 4. 别人 clone 下来怎么跑

见 README 的「三步跑起来」：装 Ren'Py SDK → `python tools/bootstrap.py --sdk <SDK路径>` → 启动。

## 5. 如果推送时要求登录

GitHub 不接受账号密码推送，只接受：

- **浏览器授权**（GitHub Desktop 默认走这个，最省事）
- **Personal Access Token**：GitHub → Settings → Developer settings → Personal access tokens → 生成 `repo` 权限的 token，粘贴到密码框
- **SSH 密钥**：`git remote set-url origin git@github.com:<你>/<仓库>.git`

**强烈建议开启两步验证（2FA）**：Settings → Password and authentication。
