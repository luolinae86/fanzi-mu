# 反字墓（fanzi-mu）

原创盗墓短剧的轻资产仓库：设定、大纲、剧本、分镜、参考图、出图与质检脚本。
视频、成片、待选静帧（refs/pending/）和质检模型不进仓库，只留在 168 上。

## Mac 上第一次用

```bash
cd ~/Documents
git clone git@github.com:luolinae86/fanzi-mu.git 反字墓-git
```
然后用 Cursor 打开 `~/Documents/反字墓-git`。

## 日常：Mac（Cursor）写剧本

```bash
git pull                       # 先拉最新
# ……在 Cursor 里改剧本/分镜……
git add -A && git commit -m "ep03 分镜" && git push
```

## 日常：168 出图/出片前

```bash
cd /root/fanzi-mu && git pull   # 拿到最新剧本、分镜、jobs
python3 refs/bin/gen_still.py --id c-peilaojian --prompt refs/jobs/c-peilaojian.txt --ref refs/v2/s-bengzhan.jpg
# 选定的图拷进 refs/vN/ 后提交：
git add refs/ && git commit -m "定稿 c-peilaojian" && git push
```

## 媒体文件仍用 rsync 从 168 拉

```bash
rsync -avz -e "ssh -p 17100" root@47.97.34.152:/root/fanzi-mu/renders/ep01/cut/ ~/Downloads/反字墓/ep01/
```

两边改同一个文件时，先 `git pull` 再改，避免冲突。
