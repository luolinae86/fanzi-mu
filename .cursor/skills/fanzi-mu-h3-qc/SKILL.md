---
name: fanzi-mu-h3-qc
description: >-
  《反字墓》H3 出片与草剪 QC。用户说重跑镜头、改提示词、修草剪、字幕烧录、道具穿帮、对口型不同步、拓片/镜子/绳子问题，或更新 locked 成片时使用。借鉴开源短剧管线：镜头状态机、资产版本、QC 门禁。
---

# 《反字墓》H3 出片与 QC

在 GPU 主机（168 / `fanzi-168`）上改提示词、重跑 Ref2VA、修字幕和草剪。

**路径分工（GitHub 同步后）：**

| 内容 | 位置 |
|------|------|
| 剧本 / 分镜 / skill / 定稿参考图 jobs | Mac `~/Documents/反字墓-git` → GitHub → 168 `git pull` |
| 成片 / locked 镜 / 草剪 | 168 `/root/fanzi-mu/renders/`；Mac 用 rsync 拉到 `~/Projects/fanzi-mu/ep01/` 或 `~/Downloads/反字墓/` |

出片前先看队列：`curl -s http://127.0.0.1:8188/queue`。有人教同步等任务在跑时，把反字墓任务排到 pending，不要强杀别人的活。

## 连接

- 内网：`ssh -l root 192.168.1.168` 或 `ssh fanzi-168-lan`
- 公网：`ssh -l root 47.97.34.152 -p 17100` 或 `ssh fanzi-168`
- 拉文件：`rsync -avh -e "ssh -l root -p 17100" 47.97.34.152:/root/fanzi-mu/... ./`

## 镜头流水线（状态机）

借鉴 Jellyfish 类「剧本→分镜→一致→出片→导出」，每镜只处在一个状态；**未过门禁不得锁进草剪**。

```
board     →  prompt    →  queued   →  rendered  →  qc
（分镜事实）   （H3 提示词）   （Comfy 排队）   （output 成片）   （抽帧+声画）
                                                      ↓ fail → 改 prompt / 换 seed → 重 queued
                                                      ↓ pass
                                                   locked →  roughcut →  softsub/burned
```

| 状态 | 产物位置 | 可进入下一态的条件 |
|------|----------|-------------------|
| board | `ep*-script-board.json` / 分镜 md | 用户确认分镜 |
| prompt | `renders/ep01/shNN_*_prompt.txt` | 含资产 ref id + 解剖学锁 + 本镜硬规则 |
| queued | ComfyUI queue | `build_shot.py` 提交成功 |
| rendered | `ComfyUI/output/video/fanzimu_ep01_sh…` | 文件完整且 mtime 新于本次 QUEUE_EPOCH |
| qc | `qc_*/` 抽帧 | 见下方 **QC 门禁** 全过 |
| locked | `renders/ep01/locked/` 活动名 | 人工或脚本选定 winner |
| roughcut | `cut/fanzimu_ep01_roughcut_v1.mp4` | 本集全部必出镜均 locked |
| softsub | `*_softsub.mp4` / `*_burned.mp4` | 字幕与 RMS 对齐后 remux |

进度汇报时按上表说清：**哪几镜卡在哪一态**，不要只说「在跑」。

## 一致性资产库

- **定稿图**只认 `refs/vN/`（或 ComfyUI `input/fanzimu_*.jpg` 从该版本拷入）。`refs/pending/` 不进成片。
- 定稿图变更走 Git：168 选定 → 拷入 `refs/vN/` → `git commit && git push`；Mac / bot `git pull`。
- 每镜 prompt 的 Picture 顺序与 `build_shot.py` 的 REF 参数一一对应；缺图标缺，禁止 silently 用错版本。
- 英雄道具尺度见 `pipeline/PROP_MIRROR_SCALE.txt`；解剖学硬句见 `pipeline/PROMPT_ANATOMY_LOCK.txt`（须粘进相关镜）。

## QC 门禁（不过 = 整镜作废重跑）

锁定前必须过完；**禁止**用静帧 hold、单纯禁音、打码遮第三只手当成片方案。

1. **解剖**：在场每人 exactly 2 hands / 2 arms；持物 ECU 触镜手数 = 2 且同属一人；≥3 只手 → fail。优先结构规避（中段起幅 / MCU 已持物），不要只写 NO third hand。
2. **道具一致**：铜镜 14–16cm 跨镜同尺；夜市只用 `s-yeshi_nomirror`；无定妆泄漏（林晚包内手镜用 `c-linwan_nomirror`）。
3. **声画**：摔/抛/落地声必须对齐接触帧；无字幕 orphan 重击声；禁音消不掉口型 → 重跑。
4. **对白**：邻镜台词不重复；字幕起止 vs RMS；FontSize≥52。
5. **画面**：无水印、无招牌假字；拓片有结构乱笔；拉绳手停绳停。

自动检查（草剪后必跑）：

```bash
python3 tools/check_ep01_audio_subs.py \
  --video ep01/cut/fanzimu_ep01_roughcut_v1.mp4 \
  --srt   ep01/cut/fanzimu_ep01_roughcut_v1.srt \
  --board ep01/board/ep01-script-board.json \
  --prompts-glob 'renders_staging/sh*_prompt.txt'
```

## 已踩过的坑（必须规避）

### 字幕 / 对白

- 竖屏烧录：**FontSize ≥ 52**（推荐 56），Outline ≥ 3，MarginV ≈ 90–100。
- 相邻说话人交接用音量包络：上一句字幕结束 ≤ 实际语音结束；下一句开始 ≥ 实际语音开始。
- 软字幕挂 SRT；烧录用 ASS；改字幕后同时更新 softsub / burned。
- 邻镜台词不重复（ep01「正看是乱笔」曾进 sh03 又进 sh04）。
- 禁音消不掉口型 → 必须重跑；**禁止闭口静帧 hold**。

### 拓片

- 正看是有结构的倒刻乱笔，不是泼墨；镜读才顺。同步 `refs/v3/p-rubbing.jpg` 与 ComfyUI input。

### 定妆泄漏

- 本镜不需要手镜时用 `fanzimu_c-linwan_nomirror.jpg`；提示词写 satchel 无圆形金属、Ignore costume accessory。

### 绳子

- hand-over-hand；手停绳停；禁止漂浮/自动回卷。

### 铜镜 / 夜市 / 递接

- 尺度 14–16cm；场景用 `s-yeshi_nomirror`；抛镜优先「镜已在桌上」起幅；验镜 ECU 禁止拍递接瞬间。

## 重跑镜头流程

1. `git pull`（168）拿到最新 prompt / board / refs。
2. 改 `*_vN_prompt.txt`，粘贴解剖学锁与本镜硬规则。
3. `build_shot.py W H TURBO SEED TAG DUR PROMPT REF...`；设 `QUEUE_EPOCH`。
4. 出片后抽帧 QC → 不过则换 seed / 改结构再 queued。
5. 通过则拷进 `locked/` 活动名（`build_roughcut.py` 的 SHOTS 表），再 `build_roughcut.py`。
6. `fix_ep01_subs_v2.py` + softsub/burned；跑 `check_ep01_audio_subs.py`。
7. rsync 草剪到 Mac；打开 softsub 给人审。

## 字幕快修

```bash
ffmpeg -y -i roughcut.mp4 -i roughcut.srt -map 0:v -map 0:a -map 1 \
  -c:v copy -c:a copy -c:s mov_text -disposition:s:0 default softsub.mp4
ffmpeg -y -i roughcut.mp4 -vf subtitles=roughcut.ass \
  -c:v libx264 -crf 18 -c:a copy burned.mp4
```

远程单行命令，避免 SSH heredoc 把 `ffmpeg \` 折行弄断。

## QC 清单（每镜锁定前）

- [ ] 状态：本镜已从 rendered → qc → 准备 locked
- [ ] 资产：ref 均为定稿 `vN`，无 pending / 错版本
- [ ] 无定妆道具泄漏
- [ ] 双手数量正确（ECU 触镜手 = 2）；关键动作手在做事
- [ ] 英雄道具尺度跨镜一致；夜市无多镜摊
- [ ] 声画：落地/撞击与画面对齐；无错误 orphan 重击
- [ ] 拓片/铭文有结构；对白窗与字幕无错位
- [ ] 无乱码/招牌假字；无水印
