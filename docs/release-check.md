# 授权、首次安装与窗口边界验收

日期：2026-10-25。采用源码发布方案，不声称取得了 PotPlayer 默认皮肤的再分发授权。

## 发布内容

- 原创生成器、窗口管理和安装代码、文档、Logo、放大镜按 MIT 许可提供。
- Lucide 原始 SVG 及 ISC 许可、版权说明完整保留。
- 公开 ZIP 和干净目录由 tools/package_source.py 按允许清单导出，附 source-manifest.json 的文件 SHA256。
- 默认皮肤、派生 src/、生成的 DSF、EXE/DLL、Windows 字体、.runtime、.venv、参考资料和旧 .git 均未带入。
- 旧开发历史只保留在本地。公开时使用新的干净源码目录，不推送旧开发仓库。
- 2 项源码导出测试通过，包括文件/许可清单、历史隔离及拒绝覆盖已有非空目录。

## 安装验证

安装器通过显式路径、保存记录、注册表 App Paths/卸载信息、PATH、已运行播放器和常见路径发现 x64 PotPlayer，并验证 EXE 的 x64 PE 类型；Python 要求 3.10+、64 位。首次创建本地环境并安装 requirements.txt，构建默认资源来自本机。

3 项安装 CLI 回归通过。干净源码测试没有预置 .venv、src 或 dist，使用含空格的项目路径和播放器路径，验证真实 venv、依赖安装和本地构建。连续安装验证不重复构建、保留用户 INI、从保存路径重新发现播放器，改变 SVG 内容后正确重建。无效显式路径给出可执行的纠正提示。

另从公开导出的源码建立全新测试目录，不传入播放器或 Python 路径，实际自动找到本机播放器及 Python 3.14，完成环境创建、Pillow/resvg-py 安装、DSF 构建和 GUI 启动。原开发环境 Python 为 3.13。

更新时仅在预览关闭后同步运行文件，运行期间提示重启，避免覆盖锁定文件和用户设置。毛玻璃与 NoGlass 模式双向切换时均提示关闭重启；已实际验证 NoGlass 会话中请求普通模式时保留当前进程并给出提示。

## 窗口边界验证

修复前，在工作区 0,0–2560,1380 中把面板移动至右下方后，播放列表保持在 2520,1345–2970,1753，控制面板保持在 2520,1345–3040,1850；2 秒后仍未恢复，测试失败。

修复后，5 项原生 Win32 测试在普通和 NoGlass 模式均通过：

1. 模拟媒体调整导致的越界后，两面板恢复至最近工作区内并保留原尺寸。
2. 超过工作区的可调整播放列表缩小到工作区范围。
3. 已在工作区内的用户位置保持不变。
4. 原生 move/size 开始到结束之间不抢位置，结束后再恢复。
5. 同名、属于其他进程的窗口不被移动。

恢复结果示例：播放列表 2110,972–2560,1380；控制面板 2040,875–2560,1380。超大播放列表最终为 0,0–2560,1380。NoGlass 状态的 host 为 0，不创建材质窗，主窗口透明样式保持不变。

实现使用 Win32 显示器工作区和最近显示器 API，计算不假定坐标为正，并检测工作区变化。物理多屏拔插、负坐标显示器及多 DPI 切换尚未逐一实机验证。

## 界面回归与复查

干净导出的源码在 Python 3.14 下通过 6 项皮肤图像/布局测试、1 项 DSF 资源与命令完整性测试、10 项原生界面回归。播放列表三种尺寸均无黑条，文字、搜索框、按钮边框与行居中保持正确，拖动后毛玻璃恢复、音量悬停和全屏铺满通过。旧原生效果检查脚本同步使用当前 Alpha 200，并通过空闲状态检查。

首次干净测试发现旧工具默认 qa 目录已存在，现已让截图接口自动创建输出目录。全屏回归结束会恢复普通模式，减少连续运行的状态干扰。

独立代码复查未发现源码允许清单或许可边界的发布阻塞项；发现的双向 NoGlass 切换提示问题已修复并实测。

## 复验入口

```powershell
.\安装皮肤.cmd -PrepareOnly
.\.venv\Scripts\python.exe tests\source_release.py
.\.venv\Scripts\python.exe tests\installer_regressions.py
.\.venv\Scripts\python.exe -m unittest tests.skin_regressions -v
.\.venv\Scripts\python.exe tests\secondary_artifacts.py
# 开启本项目预览，使用对应 PID，空闲页运行：
.\.venv\Scripts\python.exe tests\native_regressions.py <PID> all
.\.venv\Scripts\python.exe tests\window_bounds.py <PID>
# 关闭后用 -NoGlass 重启，再运行 window_bounds.py 验证无毛玻璃模式。
```
