---
name: fanzi-mu-h3-qc
description: >-
  《反字墓》H3 出片与草剪 QC。用户说重跑镜头、改提示词、修草剪、字幕烧录、道具穿帮、对口型不同步、拓片/镜子/绳子问题，或更新 locked 成片时使用。
---

# 《反字墓》H3 出片与 QC

在 GPU 主机（168 / `fanzi-168`）上改提示词、重跑 Ref2VA、修字幕和草剪。本机项目目录是 `/Users/luolin/Projects/fanzi-mu`；成片源在 `/root/fanzi-mu/renders/`。

## 连接

- 内网：`ssh -l root 192.168.1.168` 或 `ssh fanzi-168-lan`
- 公网：`ssh -l root 47.97.34.152 -p 17100` 或 `ssh fanzi-168`
- 拉文件：`rsync -avh -e "ssh -l root -p 17100" 47.97.34.152:/root/fanzi-mu/... ./`

出片前先看队列：`curl -s http://127.0.0.1:8188/queue`。有人教同步等任务在跑时，把反字墓任务排到 pending，不要强杀别人的活。

## 已踩过的坑（必须规避）

### 1. 字幕样式与对白不同步

- 竖屏 720×1280 烧录字幕：**FontSize ≥ 52**（推荐 56），白字 + 够粗描边（Outline ≥ 3），MarginV ≈ 90–100。FontSize 36–38 在手机上太小。
- 时间轴不能只靠 silencedetect 粗切。**相邻说话人交接处**必须用音量包络核对：上一句字幕结束 ≤ 实际语音结束；下一句开始 ≥ 实际语音开始。ep01 ~23s 曾出现马勺字幕拖到 23.9，而赵三姐已在 23.55 开口。
- 软字幕挂 SRT；烧录用 ASS。改字幕后同时更新 softsub / burned，原片 `*_roughcut_v1.mp4` 不动。

### 2. 拓片「看不出信息」

- 禁止把拓片参考图做成纯墨渍/泼墨。故事需要：**正看是有结构的倒刻乱笔，镜读能读出意思**。
- 参考图应用倒过来的篆/宋体墨拓字形（结构化乱笔），不是随机污点。
- H3 不擅长生成可读篆文；镜内正字可用后期 overlay，但**纸面本身**仍要看得出「这是字」。
- 改拓片后同步：`refs/v3/p-rubbing.jpg`、ComfyUI `input/fanzimu_p-rubbing.jpg`，并重跑出示拓片的镜头。

### 3. 定妆图道具泄漏（书包里的镜子）

- 林晚定妆含手镜时，H3 会在关书包等动作里把镜子「长」进包内。
- 提示词硬规则：本镜若只需拓纸入包，写清 **satchel interior = empty dark leather only；NO hand mirror / round metal / reflective disk**；并写 **Ignore hand-mirror accessory in costume reference**。
- QC 必查：开合包、掏东西、侧身行走时包口是否冒出圆形金属反光。

### 4. 绳子「自己上来」

- 只写 “draws up a rope” 不够。必须写：**hand-over-hand 拉绳、双手交替握紧、绳子只因手拉才动；手停绳停；禁止漂浮/自动回卷**。
- QC 抽帧：拉绳段每秒一帧，确认双手在绳上且位移与绳运动同向。

### 5. 对白 / TTS / 字幕三件套

- H3 片内对白与后期 TTS/VO 不要混用同一时间窗却各写各的。
- 侯启明等画外音：画面按静音生成 + 后期 VO 时，字幕时间必须以 **最终混音** 为准，不是以镜头规划秒数为准。
- 修字幕后用 20ms RMS 包络抽查交接句。

## 重跑镜头流程

1. 改 `*_vN_prompt.txt`，写进上面的硬规则。
2. `build_shot.py W H TURBO SEED TAG DUR PROMPT REF...` 提交 ComfyUI。
3. 出片后抽帧 QC（道具、手、拓片、嘴型窗）。
4. 通过则拷进 `renders/ep01/locked/`，再跑草剪组装。
5. 同步选用镜到本机 `ep01/shots/`，草剪到 `ep01/cut/`。

## 字幕快修

本机脚本：`tools/fix_ep01_subs_v2.py`（在 168 的 `renders/ep01/cut/` 执行）。改完后：

```bash
# softsub stream copy + burned re-encode
ffmpeg -y -i roughcut.mp4 -i roughcut.srt -map 0:v -map 0:a -map 1 \
  -c:v copy -c:a copy -c:s mov_text -disposition:s:0 default softsub.mp4
ffmpeg -y -i roughcut.mp4 -vf subtitles=roughcut.ass \
  -c:v libx264 -crf 18 -c:a copy burned.mp4
```

## QC 清单（每镜锁定前）

- [ ] 无定妆道具泄漏（镜、尺、绳、保温杯位置符合本镜）
- [ ] 双手数量正确；关键动作（拉绳、拓纸、关包）手在做事
- [ ] 拓片/铭文：纸面有结构；需要镜读的信息在镜里可读
- [ ] 对白窗与字幕无重叠错位
- [ ] 无乱码/招牌假字；无水印
