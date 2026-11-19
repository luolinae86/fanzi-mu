# 《反字墓》在 Cursor 里继续做

Grok Bot 额度不够时，剧本和分镜改在 Cursor 里写；参考图和镜头在 168 显卡机（GPU 主机）上生成。成片不要经 Grok Bot 中转。

## 1. 把项目拉到这台 Mac

只要文字、设定、参考图和脚本，不要把 `renders/` 整包拉下来：

```bash
mkdir -p ~/Documents/反字墓 && rsync -avz -e 'ssh -p 17100' \
  --exclude 'renders/' --exclude 'qc/.venv/' \
  'root@47.97.34.152:/root/fanzi-mu/' ~/Documents/反字墓/
```

用 Cursor 打开 `~/Documents/反字墓`。项目里已经有 `.cursor/skills/fanzi-mu-scripts` 和 `.cursor/rules/fanzi-mu.mdc`。

写完剧本后，再同步回 168：

```bash
rsync -avz -e 'ssh -p 17100' \
  --exclude 'renders/' --exclude 'qc/.venv/' --exclude '.DS_Store' \
  ~/Documents/反字墓/ 'root@47.97.34.152:/root/fanzi-mu/'
```

不要覆盖 168 上 `renders/` 里已经出好的镜头。

## 2. 在 Cursor 里写剧本

对 Cursor 说：「按本项目的剧本 skill，写第 N 集」或「把第 N 集拆成分镜」。它应先读 `series-bible.md`、`series-outline.md` 和已有的 `vol1-scripts.md` / `vol2-scripts.md`。用户确认之前不要当作可以出片。

## 3. 在 168 上出参考图

168 目前装着 H3 的视频权重。出图脚本会排一条 5 秒、无对白的短镜头，再抽出静帧到 `refs/pending/`。不要用 Grok Bot 的画图功能。

在 168 本机（或从这台 Mac SSH 过去）执行，一次一张，队列没空就等：

```bash
ssh -l root 47.97.34.152 -p 17100
cd /root/fanzi-mu

# 第 2 集缺的六张，可按这个顺序跑
python3 refs/bin/gen_still.py --id c-peilaojian --prompt refs/jobs/c-peilaojian.txt --ref refs/v2/s-bengzhan.jpg
python3 refs/bin/gen_still.py --id c-huoshuan   --prompt refs/jobs/c-huoshuan.txt   --ref refs/v2/s-bengzhan.jpg --ref refs/v2/c-guchen.jpg
python3 refs/bin/gen_still.py --id p-luoyangchan --prompt refs/jobs/p-luoyangchan.txt --ref refs/v2/s-bengzhan.jpg
python3 refs/bin/gen_still.py --id p-wuhuatu    --prompt refs/jobs/p-wuhuatu.txt    --ref refs/v2/s-bengzhan.jpg
python3 refs/bin/gen_still.py --id s-jiudaodong --prompt refs/jobs/s-jiudaodong.txt --ref refs/v2/s-bengzhan.jpg
python3 refs/bin/gen_still.py --id p-chibiao    --prompt refs/jobs/p-chibiao.txt    --ref refs/v2/s-bengzhan.jpg
```

看 `refs/pending/` 里的静帧和接触表，选中的复制到 `refs/v2/` 或新的 `refs/v3/`，文件名用资产 id，例如 `c-peilaojian.jpg`。定妆没拍板之前不要开 H3 出第 2 集。

## 4. 审片和成片

镜头、草剪、字幕仍在 168 的 `renders/<集次>/`。从这台电脑拉 `locked/` 或 `cut/`：

```bash
mkdir -p ~/Downloads/反字墓/ep01 && rsync -avz -e 'ssh -p 17100' \
  'root@47.97.34.152:/root/fanzi-mu/renders/ep01/cut/' ~/Downloads/反字墓/ep01/
```
