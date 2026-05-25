#!/usr/bin/env python3
"""
Dashboard Auto-Update Script v3
每30分钟运行，收集最新数据，上传音乐到MiniMax CDN，更新 mavis-dashboard/index.html，推送到 GitHub
"""
import subprocess, json, re, os, base64
from datetime import datetime, timedelta

REPO_DIR = "/Users/liufei/Desktop/mavis-dashboard"
GITHUB_TOKEN_FILE = "/Users/liufei/.mavis/credentials/agent-37a46eb91401/github.json"
NOVEL_DIR = "/Users/liufei/Desktop/小说创作_末日领主改写/Book2_洗稿版_v2"
MUSIC_DIR = "/Users/liufei/Desktop/灵感音乐收藏"
CACHE_FILE = "/Users/liufei/.mavis/scripts/music-cdn-cache.json"
TOKEN_PLAN_CACHE = "/tmp/token_plan_cache.json"
TOKEN_PLAN_URL = "https://platform.minimaxi.com/user-center/payment/token-plan"
TODAY = datetime.now().strftime("%Y%m%d")

MAX_MUSIC_TRACKS = 6  # 最多显示6首

# ── 音乐术语翻译字典 ──
STYLE_TRANS = {
    "ambient": "氛围", "ethereal": "空灵", "dreamy": "梦幻", "cinematic": "电影感",
    "upbeat": "明快", "lo-fi": "低保真", "acoustic": "原声", "downtempo": "慢节奏",
    "darkambient": "暗氛围", "neon": "霓虹", "reverie": "遐想", "bloom": "绽放",
    "fractures": "裂痕", "starlight": "星光", "threshold": "临界", "between": "之间",
    "twomidnights": "两夜之间", "echoes": "回响", "rain": "雨", "golden": "金色",
    "lake": "湖", "morning": "清晨", "dawn": "黎明", "contemplative": "沉思",
    "instrumental": "纯音乐", "rest": "安息", "soul": "灵魂",
    "whispers": "低语", "stellar": "星辰", "drift": "漂流", "bells": "钟声",
    "abyssal": "深渊", "void": "虚空", "city": "城", "abandoned": "荒废",
    "abandonedcity": "荒城", "abandoned_city": "荒城", "fracturesofstarlight": "星光裂痕",
    "threshold_of_dreams": "梦之境", "morninggoldenglake": "晨光金湖",
    "morninggoldenlake": "晨光金湖", "morning_golden_lake": "晨光金湖",
    "morningreverie": "晨间遐想", "morning_reverie": "晨间遐想",
    "morning_bloom": "晨绽", "contemplativedawn": "沉思黎明",
    "betweentwomidnights": "午夜之间", "between_two_midnights": "午夜之间",
    "neonechoes": "霓虹回响", "neon_echoes": "霓虹回响",
    "neonechoesinrain": "雨夜霓虹", "neon_echoes_in_rain": "雨夜霓虹",
    "of": "", "in": "", "the": "", "and": "", "a": "",
}

def translate_style(name):
    """把英文曲风名翻译成中文词组"""
    # 先按空格和下划线切分
    parts = re.split(r'[\s_]+', name)
    cn = []
    for w in parts:
        wl = w.lower().strip('.,!?-/')
        if not wl or wl.isdigit():
            continue
        # 整体匹配（包括连写词如 BetweenTwoMidnights）
        if wl in STYLE_TRANS:
            cn.append(STYLE_TRANS[wl])
            continue
        # CamelCase 拆分（处理 MorningGoldenLake 这类连写）
        sub_parts = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|$)', w)
        if len(sub_parts) > 1:
            for sub in sub_parts:
                sl = sub.lower().strip('.,!?-/')
                if sl in STYLE_TRANS:
                    cn.append(STYLE_TRANS[sl])
                elif sl:
                    cn.append(sub)
        else:
            cn.append(w)
    result = "".join(cn).strip()
    return result if result else name


def translate_lyrics(lyrics_text):
    """把英文歌词翻译成中文，保留段落标记"""
    # 段标记映射
    section_trans = {
        "[verse 1]": "[主歌1]", "[verse 2]": "[主歌2]", "[verse 3]": "[主歌3]",
        "[chorus]": "[副歌]", "[bridge]": "[桥段]",
        "[intro]": "[前奏]", "[outro]": "[尾声]", "[pre-chorus]": "[预副歌]",
        "[instrumental]": "[纯音乐]", "[interlude]": "[间奏]",
        "[verse]": "[主歌]", "[hook]": "[Hook]",
    }
    # 简单词级翻译
    word_trans = {
        "stars": "星辰", "silence": "寂静", "falls": "降临", "cold": "寒冷",
        "constellations": "星群", "watch": "凝视", "walls": "城墙", "trace": "追寻",
        "cracks": "裂缝", "light": "光芒", "bleeds": "渗透", "through": "穿过",
        "universe": "宇宙", "shades": "光影", "blue": "湛蓝",
        "fractures": "碎裂", "starlight": "星光", "breaking": "崩裂", "healing": "愈合",
        "dawn": "黎明", "rewrites": "重写", "sky": "天空",
        "dreams": "梦境", "silver": "银色", "tide": "潮汐", "streams": "流淌",
        "shadow": "暗影", "meets": "相遇", "fading": "消逝", "drift": "漂泊",
        "beyond": "超越", "edge": "边缘", "sleep": "沉睡", "whisper": "低语",
        "floating": "漂浮", "soft": "轻柔", "bright": "明亮",
        "between": "之间", "waking": "清醒", "time": "时间", "dissolves": "消融",
        "night": "夜",
    }
    lines = lyrics_text.split('\n')
    result_lines = []
    for line in lines:
        orig = line.strip()
        if not orig:
            result_lines.append("")
            continue
        # 翻译段落标记
        lower = orig.lower()
        for tag, cn_tag in section_trans.items():
            if lower.startswith(tag):
                result_lines.append(cn_tag)
                orig = orig[len(tag):].strip()
                lower = orig.lower()
                break
        # 逐词翻译
        words_out = []
        for word in re.split(r'(\s+|,)', orig):
            wl = word.lower().rstrip('.,!?;:\"\'（）()「」')
            if wl in word_trans:
                words_out.append(word_trans[wl])
            else:
                words_out.append(word)
        result_lines.append("".join(words_out))
    return "\n".join(result_lines)

def run(cmd, timeout=60):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip(), r.returncode, r.stderr[:200] if r.stderr else ""


def fetch_token_plan():
    """从 MiniMax Token Plan 页面抓取实时用量数据（浏览器 DOM 读取）"""
    # ── Step 1: 检查文件缓存（30分钟有效期） ──
    if os.path.exists(TOKEN_PLAN_CACHE):
        try:
            with open(TOKEN_PLAN_CACHE) as f:
                cached = json.load(f)
            age = (datetime.now() - datetime.fromisoformat(cached["_cached_at"])).total_seconds()
            if age < 1800:  # 30分钟
                print(f"  [TokenPlan] 使用缓存（{int(age)}秒前）")
                return cached
        except Exception:
            pass

    # ── Step 2: 打开后台 tab，导航到 Token Plan 页面 ──
    print("  [TokenPlan] 打开后台 tab 抓取 Token Plan...")
    # 用 open_tab 创建后台 tab（active:false）
    tab_result, _, _ = run(
        'mavis browser tool open_tab --url "https://platform.minimaxi.com/user-center/payment/token-plan" --active false',
        timeout=30000
    )
    tab_id = None
    try:
        parsed = json.loads(tab_result)
        tab_id = parsed.get("tab_id") or parsed.get("id")
    except Exception:
        # 回退：直接用 navigate
        pass

    if tab_id:
        # 后台 tab 已打开，等页面加载
        run('mavis browser tool wait --seconds 3', timeout=10000)
    else:
        # 直接 navigate（可能在现有 tab 上）
        run(
            'mavis browser tool navigate --url "https://platform.minimaxi.com/user-center/payment/token-plan"',
            timeout=30000
        )
        run('mavis browser tool wait --seconds 4', timeout=10000)

    # ── Step 3: snapshot 获取页面文本 ──
    snapshot_result, _, _ = run('mavis browser tool snapshot', timeout=30000)

    # ── Step 4: 关闭 tab（如果是后台 tab） ──
    if tab_id:
        run(f'mavis browser tool close_tab --tab_id {tab_id}', timeout=5000)

    # ── Step 5: 解析页面文本 ──
    result = {
        "text": {"used": 0, "limit": 0, "pct": 0},
        "music": {"used": 0, "limit": 0, "pct": 0},
        "image_gen": {"used": 0, "limit": 0, "pct": 0},
        "image_understand": {"used": 0, "limit": 0, "pct": 0},
        "_cached_at": datetime.now().isoformat()
    }

    # 合并多行文本（页面文本可能含换行）
    raw_text = snapshot_result

    # 匹配模式：支持 "文本生成：已使用 13336 / 15000 (89%)" 或 "已使用 X / Y"
    patterns = [
        # 文本生成 / 文本 / Text
        (r"文本生成[：:]\s*已使用\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "text", "used", "limit", "pct"),
        (r"文本[：:]\s*已使用\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "text", "used", "limit", "pct"),
        (r"Text[：:]\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "text", "used", "limit", "pct"),
        # 音乐生成 / 音乐
        (r"音乐生成[：:]\s*已使用\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "music", "used", "limit", "pct"),
        (r"音乐[：:]\s*已使用\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "music", "used", "limit", "pct"),
        (r"Music[：:]\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "music", "used", "limit", "pct"),
        # 图像生成 / 图片生成
        (r"图像生成[：:]\s*已使用\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "image_gen", "used", "limit", "pct"),
        (r"图片生成[：:]\s*已使用\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "image_gen", "used", "limit", "pct"),
        (r"Image Gen[：:]\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "image_gen", "used", "limit", "pct"),
        # 图片理解 / 图像理解
        (r"图片理解[：:]\s*已使用\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "image_understand", "used", "limit", "pct"),
        (r"图像理解[：:]\s*已使用\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "image_understand", "used", "limit", "pct"),
        (r"Image Understand[：:]\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "image_understand", "used", "limit", "pct"),
        # 语音合成
        (r"语音合成[：:]\s*已使用\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "speech", "used", "limit", "pct"),
        # 歌词生成
        (r"歌词生成[：:]\s*已使用\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "lyrics", "used", "limit", "pct"),
        # 网络搜索
        (r"网络搜索[：:]\s*已使用\s*([0-9,]+)\s*/\s*([0-9,]+)\s*\(([0-9.]+)%\)",
         "websearch", "used", "limit", "pct"),
    ]

    matched = {}
    for pat, key, u_key, l_key, p_key in patterns:
        m = re.search(pat, raw_text)
        if m:
            used = int(m.group(1).replace(",", ""))
            limit = int(m.group(2).replace(",", ""))
            pct = float(m.group(3))
            if key not in matched:
                matched[key] = {"used": used, "limit": limit, "pct": pct}
                result[key] = {"used": used, "limit": limit, "pct": pct}
            print(f"  [TokenPlan] {key}: {used}/{limit} ({pct}%)")

    # ── Step 6: 写缓存文件 ──
    try:
        with open(TOKEN_PLAN_CACHE, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"  [TokenPlan] 缓存已写入（{TOKEN_PLAN_CACHE}）")
    except Exception as e:
        print(f"  [TokenPlan] 缓存写入失败: {e}")

    return result


def get_github_token():
    with open(GITHUB_TOKEN_FILE) as f:
        return json.load(f)["github"]


def load_cdn_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_cdn_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, ensure_ascii=False)


def upload_to_cdn(file_path):
    """上传文件到 MiniMax CDN，返回 CDN URL"""
    if not os.path.exists(file_path):
        return None
    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode()

    # 写 JSON 到临时文件，绕过命令行长度限制
    args_file = "/tmp/cdn_upload_args.json"
    with open(args_file, "w") as f:
        json.dump({"data": data}, f)

    result, code, err = run(
        f'mavis mcp call matrix matrix_upload_to_cdn --file {args_file} --timeout 90000',
        timeout=120
    )
    try:
        parsed = json.loads(result)
        if parsed.get("code") == 0:
            return parsed.get("cdn_url")
        else:
            print(f"    CDN upload failed: {parsed.get('message', err)}")
            return None
    except:
        print(f"    CDN upload parse error: {err[:100]}")
        return None


def get_music_tracks():
    """获取最新音乐（今天+昨天），上传CDN，返回tracks列表"""
    cache = load_cdn_cache()
    tracks = []

    # 扫描今天和昨天的目录
    dates = [TODAY, (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")]
    all_folders = []

    for date in dates:
        date_dir = f"{MUSIC_DIR}/{date}"
        if not os.path.isdir(date_dir):
            continue
        for item in sorted(os.listdir(date_dir)):
            item_path = os.path.join(date_dir, item)
            if os.path.isdir(item_path):
                mp3_file = os.path.join(item_path, "music.mp3")
                if os.path.exists(mp3_file):
                    all_folders.append((date, item, mp3_file))

    # 只取最新的 MAX_MUSIC_TRACKS 首
    all_folders = all_folders[-MAX_MUSIC_TRACKS:]

    for date, folder_name, mp3_file in all_folders:
        cache_key = mp3_file  # 用本地路径做缓存key
        mp3_cdn = cache.get(cache_key, {}).get("mp3")
        cover_cdn = cache.get(cache_key, {}).get("cover")
        folder_time = cache.get(cache_key, {}).get("time", "")

        # 上传MP3
        if not mp3_cdn:
            print(f"    Uploading MP3: {folder_name}")
            mp3_cdn = upload_to_cdn(mp3_file)
            if mp3_cdn:
                cache[cache_key] = cache.get(cache_key, {})
                cache[cache_key]["mp3"] = mp3_cdn

        # 上传封面图（查找同目录图片）
        if not cover_cdn:
            img_exts = [".png", ".jpg", ".jpeg", ".webp"]
            for fname in os.listdir(os.path.dirname(mp3_file)):
                fext = os.path.splitext(fname)[1].lower()
                if fext in img_exts:
                    cover_path = os.path.join(os.path.dirname(mp3_file), fname)
                    print(f"    Uploading cover: {fname}")
                    cover_cdn = upload_to_cdn(cover_path)
                    if cover_cdn:
                        cache[cache_key]["cover"] = cover_cdn
                    break

        if mp3_cdn:
            # 中文名（去掉序号前缀，翻译曲风）
            name_clean = re.sub(r"^\d+_", "", folder_name)
            chinese_name = translate_style(name_clean)
            if not chinese_name:
                chinese_name = name_clean.replace("_", " ")

            # 读取歌词并翻译
            lyrics = ""
            lyrics_file = os.path.join(os.path.dirname(mp3_file), "lyrics.txt")
            if os.path.exists(lyrics_file):
                try:
                    raw_lyrics = open(lyrics_file, encoding="utf-8").read().strip()
                    if raw_lyrics and raw_lyrics.lower() != "instrumental":
                        lyrics = translate_lyrics(raw_lyrics)
                except:
                    pass

            # 时间信息
            time_str = folder_time
            if not time_str:
                parts = folder_name.split("_")
                if parts[0].isdigit():
                    time_str = date[-2:] + ":" + parts[0].zfill(2)

            tracks.append({
                "name": chinese_name,
                "name_en": name_clean.replace("_", " "),
                "url": mp3_cdn,
                "cover": cover_cdn or "",
                "time": time_str,
                "lyrics": lyrics
            })
            # 更新缓存时间
            if time_str:
                cache[cache_key]["time"] = time_str

    save_cdn_cache(cache)
    return tracks


def get_novel_progress():
    """统计已完成章节数（从 batch*/深度改写_Ch*.txt）"""
    count = 0
    for batch in range(1, 50):
        d = f"{NOVEL_DIR}/batch{batch}"
        if os.path.isdir(d):
            files = [f for f in os.listdir(d) if f.startswith("深度改写_Ch") and f.endswith(".txt")]
            count += len(files)
    return count


def get_music_today():
    """统计今日音乐产出"""
    music_path = f"{MUSIC_DIR}/{TODAY}"
    if not os.path.isdir(music_path):
        return 0
    count = 0
    for item in os.listdir(music_path):
        item_path = os.path.join(music_path, item)
        if os.path.isdir(item_path):
            count += len([f for f in os.listdir(item_path) if f.endswith(".mp3")])
    return count


def get_fav_count():
    """精选库收录数"""
    fav_file = f"{MUSIC_DIR}/精选库/精选库.md"
    if not os.path.isfile(fav_file):
        return 0
    return open(fav_file).read().count("---") // 2


def validate_html_js_syntax(html_path):
    """校验 index.html 的 JS 语法，防止 IIFE 结构错误导致播放器失效

    典型 bug：Dashboard 有两个脚本结构：
    1. 正常的 IIFE 闭合 (});\\n})();  或同一行  }););)
    2. 损坏状态：renderMusic() 定义在 IIFE 外部

    校验逻辑：
    - '});});' 出现 >1 次 → 重复 IIFE 结束符（脚本重复）
    - renderMusic() 定义在最后一个 '})();' 之后 → 播放器无法工作
    """
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. 检查是否存在重复的 IIFE 结束符
    # 正常：'});\n})();' 拆成两行 或 '}););' 同一行出现一次
    # 损坏：'});});' 同一行出现多次 = 脚本块重复
    double_close_count = html.count('});});')
    if double_close_count > 1:
        print(f"  [VALIDATION ERROR] 重复的 IIFE 结束符 '}});}});'：发现 {double_close_count} 次")
        return False
    elif double_close_count == 1:
        print("  [VALIDATION ERROR] 单个 '});});' 出现说明 IIFE 结构可能损坏（期望拆分成两行）")
        return False

    # 2. 检查 renderMusic() 是否在最后一个 IIFE 闭合之后才出现
    # 正确结构：renderMusic 定义在 IIFE 内部，能被 init() 调用
    # 损坏结构：renderMusic 定义在 IIFE 外部，无法被 IIFE 内的 init() 调用
    iiife_closer_count = html.count('})();')
    if iiife_closer_count == 0:
        print("  [VALIDATION ERROR] 未找到 IIFE 结束符 '})();'，脚本缺少闭合")
        return False

    last_iiife_pos = html.rfind('})();')
    render_pos = html.find('function renderMusic()')
    if render_pos == -1:
        render_pos = html.find('function renderMusic ')  # 兼容 function renderMusic =

    if render_pos != -1 and render_pos > last_iiife_pos:
        print(f"  [VALIDATION ERROR] renderMusic() 定义在 IIFE 结束符之后 (pos={render_pos} > {last_iiife_pos})，播放器将无法工作")
        return False

    print(f"  [VALIDATION OK] IIFE 结构正确（renderMusic pos={render_pos}, IIFE结束 pos={last_iiife_pos}）")
    return True


def update_html(chapters, music_today, fav_count, music_tracks, token_plan_data=None):
    """Update dashboard HTML"""
    html_path = f"{REPO_DIR}/index.html"
    with open(html_path) as f:
        html = f.read()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── Update header timestamp ──
    html = re.sub(r'id="update-time">[^<]+', f'id="update-time">更新于 {now_str}', html)

    # ── Progress ring ──
    circumference = 251.327
    pct = round(chapters / 300 * 100, 1) if chapters <= 300 else 100.0
    offset = circumference * (1 - chapters / 300) if chapters <= 300 else 0

    html = re.sub(r'stroke-dashoffset="[\d.]+"', f'stroke-dashoffset="{offset:.3f}"', html)
    html = re.sub(r'<div class="ring-pct">[\d.]+%?', f'<div class="ring-pct">{pct}%', html)
    html = re.sub(r'class="hstat"><div class="n">(\d+)</div><div class="l">已完成',
                  f'class="hstat"><div class="n">{chapters}</div><div class="l">已完成', html)
    remaining = max(0, 300 - chapters)
    html = re.sub(r'class="hstat"><div class="n">(\d+)</div><div class="l">剩余',
                  f'class="hstat"><div class="n">{remaining}</div><div class="l">剩余', html)

    # ── Today stats ──
    html = re.sub(r'id="stat-music">(\d+)', f'id="stat-music">{music_today}', html)
    html = re.sub(r'id="stat-fav">(\d+)', f'id="stat-fav">{fav_count}', html)

    # ── Token Plan real data ──
    # 优先用 fetch_token_plan() 传入的实时数据，否则读缓存文件
    if token_plan_data is None:
        token_file = "/Users/liufei/.mavis/scripts/token-plan-live.json"
        if os.path.exists(token_file):
            with open(token_file) as f:
                token_plan_data = json.load(f)

    if token_plan_data:

        def bar_cls(pct):
            if pct >= 80: return "red"
            elif pct >= 50: return "amber"
            else: return "green"

        items = [
            ("text", token_plan_data.get("text", {})),
            ("music", token_plan_data.get("music", {})),
            ("img", token_plan_data.get("image_gen", {})),
            ("img-under", token_plan_data.get("image_understand", {})),
        ]
        for key, item in items:
            used = item.get("used", 0)
            limit = item.get("limit", 0)
            pct_val = item.get("pct", 0)
            label_id = f"token-{key}-label"
            bar_id = f"token-{key}-bar"
            # 文本的 stat-token 单独更新
            if key == "text":
                html = re.sub(r'id="stat-token">\d+', f'id="stat-token">{pct_val}', html)
            if used is not None and limit:
                html = re.sub(
                    rf'id="{label_id}">[^<]+',
                    f'id="{label_id}">{used} / {limit:,}',
                    html
                )
                # 替换整个 bar div，包括 class 和 style
                # 替换 bar div 的 class 和 style
                # 用 data 属性标记唯一的 bar
                marker = 'XBAR' + bar_id.replace('-', '').upper() + 'X'
                html = html.replace(f'id="{bar_id}"', f'id="{bar_id}" data-x="{marker}"')
                # 正则替换整个 bar div
                pat = r'<div class="token-fill [^"]*" id="' + bar_id + r'"[^>]*></div>'
                repl = f'<div class="token-fill {bar_cls(pct_val)}" id="{bar_id}" style="width:{pct_val}%"></div>'
                new_html, n = re.subn(pat, repl, html)
                if n > 0:
                    html = new_html
                html = html.replace(f' data-x="{marker}"', '')

# ── Music data ──
    # 写独立 JSON 文件，HTML 里用 fetch 加载
    music_json_path = f"{REPO_DIR}/music-data.json"
    with open(music_json_path, 'w', encoding='utf-8') as f:
        json.dump(music_tracks, f, ensure_ascii=False, indent=2)

    # ── 更新 HTML music data ──
    # 清理旧的损坏状态（可能残留旧数据）
    def clean_music_section(html):
        # 检查当前状态：是否有 fetch 和无旧数据
        has_fetch = 'fetch' in html
        has_morning = 'Morning 光芒' in html
        if has_fetch and not has_morning:
            # 干净的 fetch 模式：只确保 IIFE 闭合正确，不做其他修改
            # 找 fetch IIFE 的状态
            fetch_start = html.find('window.__MUSIC_DATA__ = [];')
            # 检查是否有 })(); 闭合 IIFE
            iiife_close = html.find('})();', fetch_start)
            # 检查是否有 }); 闭合 .then().then()
            callback_close = html.find('  });', fetch_start)

            if iiife_close < 0 and callback_close >= 0:
                # 有 }); 但无 })();：插入 })(); 闭合 IIFE
                html = html[:callback_close+4] + '\n})();' + html[callback_close+4:]
            elif iiife_close >= 0 and callback_close < 0:
                # 有 })(); 但无 });：在 })(); 前插入 });
                html = html[:iiife_close] + '});\n' + html[iiife_close:]
            elif iiife_close < 0 and callback_close < 0:
                # 两者都缺失：找 fetch callback 结束位置
                # 通常是 `    renderMusic();\n  }` 后面缺少闭合
                render_pos = html.find('renderMusic();', fetch_start)
                if render_pos >= 0:
                    after_render = html.find('\n  }', render_pos)
                    if after_render >= 0:
                        html = html[:after_render+4] + '\n  });\n})();' + html[after_render+4:]

            return html

        # 有旧数据需要清理
        fetch_occ = html.find("window.__MUSIC_DATA__ = [];\n(function(){")
        if fetch_occ == -1:
            # 没有 fetch 模式，替换内嵌数据
            m_start = html.find('window.__MUSIC_DATA__ = [')
            if m_start != -1:
                arr_start = html.find('[', m_start + len('window.__MUSIC_DATA__ = '))
                depth = 0
                arr_end = arr_start
                for i in range(arr_start, len(html)):
                    c = html[i]
                    if c == '[': depth += 1
                    elif c == ']':
                        depth -= 1
                        if depth == 0:
                            arr_end = i + 1
                            break
                fetch_code = "window.__MUSIC_DATA__ = [];\n(function(){\n  fetch('music-data.json').then(function(r){return r.json();}).then(function(d){\n    window.__MUSIC_DATA__ = d;\n    renderMusic();\n  });\n});\n})();\n\n";
                return html[:m_start] + fetch_code + html[arr_end:]
            return html

        # 有 fetch 但有旧数据：清理旧数据，保留 fetch 代码
        player_ref = html.find('function renderMusic()', fetch_occ)
        if player_ref == -1:
            return html
        # 提取干净的内容
        clean = html[:fetch_occ] + "window.__MUSIC_DATA__ = [];\n(function(){\n  fetch('music-data.json').then(function(r){return r.json();}).then(function(d){\n    window.__MUSIC_DATA__ = d;\n    renderMusic();\n  });\n});\n})();\n\n" + html[player_ref:]
        return clean

    html = clean_music_section(html)

    with open(html_path, "w") as f:
        f.write(html)
    return html_path


def push_file_to_github(token, file_path, repo_path=None):
    """推送单个文件到 GitHub"""
    if repo_path is None:
        repo_path = file_path
    import base64
    with open(file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    filename = file_path.split("/")[-1]
    repo_name = "njafei/mavis-dashboard"
    # 提取相对路径
    if "mavis-dashboard" in file_path:
        rel_path = file_path.split("mavis-dashboard/")[-1]
    else:
        rel_path = filename
    url = f"https://api.github.com/repos/{repo_name}/contents/{rel_path}"

    GITHUB_PROXY = "http://127.0.0.1:1082"
    sha_result, _, _ = run(f'curl -s --proxy {GITHUB_PROXY} -H "Authorization: token {token}" {url}')
    try:
        sha_data = json.loads(sha_result)
        sha = sha_data.get("sha", "")
    except:
        sha = ""

    payload = json.dumps({
        "message": f"Auto-update {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "sha": sha,
        "content": content
    })
    GITHUB_PROXY = "http://127.0.0.1:1082"
    r = subprocess.run(
        f'curl -s --proxy {GITHUB_PROXY} -H "Authorization: token {token}" -H "Accept: application/vnd.github+json" '
        f'-H "X-GitHub-Api-Version: 2022-11-28" -X PUT {url} -d @-',
        shell=True, capture_output=True, text=True, input=payload
    )
    print(f"  GitHub response: {r.stdout[:100]}")
    try:
        result = json.loads(r.stdout)
    except json.JSONDecodeError:
        return f"err: JSON decode failed, stdout={r.stdout[:100]}"
    return result.get("commit", {}).get("sha", "")[:8] if "commit" in result else f"err: {result.get('message','')}"


def main():
    print(f"[{datetime.now().strftime('%H:%M')}] Dashboard update starting...")

    chapters = get_novel_progress()
    music_today = get_music_today()
    fav_count = get_fav_count()

    print(f"  Novel: {chapters} chapters done")
    print(f"  Music: {music_today} tracks today")

    # 上传音乐到CDN（已缓存的跳过）
    print("  Checking/uploading music CDN...")
    music_tracks = get_music_tracks()
    print(f"  Music CDN: {len(music_tracks)} tracks ready")

    # ── 抓取 MiniMax Token Plan 实时数据（浏览器 DOM） ──
    print("  Fetching MiniMax Token Plan...")
    token_plan_data = fetch_token_plan()
    print(f"  Token Plan: text={token_plan_data.get('text', {}).get('pct', 0)}% "
          f"music={token_plan_data.get('music', {}).get('pct', 0)}%")

    html_path = update_html(chapters, music_today, fav_count, music_tracks, token_plan_data)
    print(f"  HTML updated: {html_path}")

    # 校验 JS 语法，防止 IIFE 结构错误
    if not validate_html_js_syntax(html_path):
        print("  [ABORT] JS 语法校验失败，停止推送！")
        return

    token = get_github_token()
    sha1 = push_file_to_github(token, html_path)
    print(f"  Pushed index.html: {sha1}")

    music_json_path = f"{REPO_DIR}/music-data.json"
    if os.path.exists(music_json_path):
        sha2 = push_file_to_github(token, music_json_path)
        print(f"  Pushed music-data.json: {sha2}")

    print(f"[{datetime.now().strftime('%H:%M')}] Done!")


if __name__ == "__main__":
    main()
