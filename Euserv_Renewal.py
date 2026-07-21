import os
import time
import requests
import traceback
import html
import re
import base64
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

def apply_stealth(page):
    try:
        from playwright_stealth import Stealth
        Stealth().apply_stealth_sync(page)
    except ImportError:
        from playwright_stealth import stealth_sync
        stealth_sync(page)

# ==========================================
# 电报推送小助手 (强制锁定中国北京时间)
# ==========================================
def send_tg_msg(message, process_logs=None):
    token = os.environ.get('TG_BOT_TOKEN')
    chat_id = os.environ.get('TG_CHAT_ID')
    
    # 严谨校验：如果没有配置电报密钥，直接跳过推送，绝不阻断主程序运行
    if not token or not chat_id:
        return
        
    # 如果有收集到的执行过程日志，拼接到消息最下方
    if process_logs:
        log_content = "\n".join([f"<code>{html.escape(l)}</code>" for l in process_logs])
        message += f"\n\n<b>[执行过程详情]</b>\n{log_content}"
        
    # 强制将推送时间格式化为北京时间 UTC+8
    bj_time = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"{message}\n\n[时间] 巡检时间: {bj_time} (北京时间)"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    try:
        requests.post(url, json={"chat_id": chat_id, "text": full_message, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        # 严谨处理：推送就算失败也绝不抛出异常导致脚本崩溃，默默吞下错误
        print(f"[警告] TG推送失败: {e}")
        pass

# ==========================================
# 核心灵魂：动态时区转换与 Github 规则篡改 (锁定日本13:27)
# ==========================================
def update_github_cron(target_date_str, log_step):
    pat = os.environ.get('PAT_WITH_WORKFLOW_SCOPE')
    repo = os.environ.get('GITHUB_REPOSITORY') 
    
    if not pat or not repo:
        log_step("[警告] 未检测到 PAT_WITH_WORKFLOW_SCOPE，放弃修改调度时间。")
        return

    try:
        # 日本时间 -> UTC 时间的精准降维打击
        jst = timezone(timedelta(hours=9))
        
        # 核心修改：解析目标日期，并设定为日本时间下午 13:27 执行
        target_dt_jst = datetime.strptime(target_date_str, "%Y-%m-%d").replace(hour=13, minute=27, tzinfo=jst)
        
        # 转换为 Github 唯一能看懂的 UTC 时间 (13:27 JST = 04:27 UTC)
        target_dt_utc = target_dt_jst.astimezone(timezone.utc)

        # 提取转换后的 UTC 月、日、时、分，构造全新的 cron 表达式
        new_cron = f"{target_dt_utc.minute} {target_dt_utc.hour} {target_dt_utc.day} {target_dt_utc.month} *"

        api_url = f"https://api.github.com/repos/{repo}/contents/.github/workflows/run.yml"
        headers = {
            "Authorization": f"token {pat}",
            "Accept": "application/vnd.github.v3+json"
        }

        # 1. 获取当前的 run.yml 源码
        resp = requests.get(api_url, headers=headers)
        if resp.status_code != 200:
            log_step(f"[警告] 无法读取 YAML 文件: {resp.text}")
            return
            
        data = resp.json()
        content = base64.b64decode(data['content']).decode('utf-8')
        sha = data['sha']

        # 2. 用正则精准替换旧的 cron 为新的 cron
        new_content = re.sub(r"cron:\s*['\"].*?['\"]", f"cron: '{new_cron}'", content)

        if new_content == content:
            log_step(f"[成功] 定时任务已是最新状态。下一次将在日本时间 {target_date_str} 13:27 准时苏醒！ (内部UTC Cron: {new_cron})")
            return

        # 3. 提交修改，篡改历史！
        commit_data = {
            "message": f"[自动调度] 下次唤醒锁定于日本时间 {target_date_str} 13:27",
            "content": base64.b64encode(new_content.encode('utf-8')).decode('utf-8'),
            "sha": sha
        }
        
        put_resp = requests.put(api_url, headers=headers, json=commit_data)
        if put_resp.status_code in [200, 201]:
            log_step(f"[成功] 篡改 Github 规则完成！已产生新 Commit。下次启动时间: 日本时间 {target_date_str} 13:27 (底层Cron: {new_cron})")
        else:
            log_step(f"[错误] 修改 YAML 失败: {put_resp.text}")
            
    except Exception as e:
        log_step(f"[错误] Cron 更新报错: {e}")

# ==========================================
# 核心自动化逻辑 (代理穿透 + 阶梯打码)
# ==========================================
def run():
    # 过程收集器
    process_logs = []
    def log_step(msg):
        clean_msg = msg.strip("\n")
        print(clean_msg)
        process_logs.append(clean_msg)

    EMAIL = os.environ.get('XSERVER_EMAIL')
    PASSWORD = os.environ.get('XSERVER_PASSWORD')
    YES_KEY = os.environ.get('YESCAPTCHA_KEY')
    GEMINI_KEYS_STR = os.environ.get('GEMINI_API_KEYS')
    gemini_keys = [k.strip() for k in GEMINI_KEYS_STR.split(',')] if GEMINI_KEYS_STR else []
    
    PROXY_IP = os.environ.get('PROXY_IP')
    PROXY_PORT = os.environ.get('PROXY_PORT')
    PROXY_USER = os.environ.get('PROXY_USER')
    PROXY_PASS = os.environ.get('PROXY_PASS')

    if not all([EMAIL, PASSWORD, YES_KEY, PROXY_IP, PROXY_PORT, PROXY_USER, PROXY_PASS]) or not gemini_keys:
        msg = "[失败] <b>脚本运行失败</b>\n环境变量缺失（请检查代理配置或 API Keys）！"
        log_step("运行失败: 环境变量缺失")
        send_tg_msg(msg, process_logs)
        return

    # 全局时间基准：锁定日本时间 (UTC+9)
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    today_str = now_jst.strftime("%Y-%m-%d")
    tomorrow_str = (now_jst + timedelta(days=1)).strftime("%Y-%m-%d")

    playwright_proxy = {
        "server": f"http://{PROXY_IP}:{PROXY_PORT}",
        "username": PROXY_USER,
        "password": PROXY_PASS
    }

    with sync_playwright() as p:
        log_step(f"正在通过私人代理 {PROXY_IP} 启动隐身浏览器...")
        browser = p.chromium.launch(
            headless=False,
            proxy=playwright_proxy,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--start-maximized'
            ]
        )
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        apply_stealth(page)

        try:
            log_step("[1] 正在登录 Xserver...")
            page.goto("https://secure.xserver.ne.jp/xapanel/login/xvps/")
            page.fill("input[name='memberid']", EMAIL)
            page.fill("input[name='user_password']", PASSWORD)
            
            with page.expect_navigation():
                page.evaluate("""() => {
                    let submitBtn = document.querySelector('button[type="submit"], input[type="submit"]');
                    if (submitBtn) submitBtn.click();
                    else document.forms[0].submit();
                }""")
            
            log_step("[2] 检查 VPS 到期时间...")
            page.wait_for_timeout(5000)
            
            row = page.locator("tr:has(.freeServerIco)")
            if row.count() == 0:
                raise Exception("未找到免费 VPS 实例。")

            expire_text = row.locator(".contract__term").inner_text().strip()
            
            try:
                # 提取面板上的日本到期日，计算计划续期日
                expire_dt = datetime.strptime(expire_text, "%Y-%m-%d")
                renew_date_str = (expire_dt - timedelta(days=1)).strftime("%Y-%m-%d")
            except:
                renew_date_str = "未知"

            log_step(f"    日本今天: {today_str} | 计划续期: {renew_date_str} | 彻底到期: {expire_text}")

            # 情景 1：今天不需要续期 (或者刚刚完成续期后的第二天复查)
            if expire_text != tomorrow_str:
                log_step("    还没到续期时间，脚本收工。")
                
                # 安排休眠：一直睡到要续期的那天下午 13:27 再醒来
                if renew_date_str != "未知":
                    update_github_cron(renew_date_str, log_step)
                    
                msg = f"[播报] <b>Github xserver-auto:状态播报 (暂无需操作)</b>\n\n[今日] <b>今天是:</b> {today_str} (JST)\n[计划] <b>要续期是:</b> {renew_date_str} (JST)\n[到期] <b>到期是:</b> {expire_text} (JST)"
                send_tg_msg(msg, process_logs)
                browser.close()
                return

            log_step("[3] 获取续期链接...")
            detail_link = row.locator("a[href^='/xapanel/xvps/server/detail?id=']").first.get_attribute("href")
            extend_url = "https://secure.xserver.ne.jp" + detail_link.replace("detail?id", "freevps/extend/index?id_vps")

            max_attempts = 15
            log_step(f"[4] 处理验证码与 CF 防御 (梯队战术，最高重试 {max_attempts} 次)...")
            is_success = False
            
            for attempt in range(1, max_attempts + 1):
                page.goto(extend_url)
                page.wait_for_timeout(1000)
                
                with page.expect_navigation():
                    page.locator("[formaction='/xapanel/xvps/server/freevps/extend/conf']").click()
                
                page.wait_for_timeout(2000)
                
                img_locator = page.locator("img[src^='data:image'], img[src^='data:']")
                if img_locator.count() == 0:
                    raise Exception("页面上找不到验证码图片！")
                    
                img_b64_full = img_locator.first.get_attribute("src")
                mime_type = img_b64_full.split(";")[0].replace("data:", "")
                b64_data = img_b64_full.split(",")[1]
                captcha_code = None

                if attempt <= 3:
                    log_step(f"    >>> 开始第 {attempt} 次尝试 (先锋营：私人 run.app 接口) <<<")
                    try:
                        ocr_res = requests.post('https://captcha-120546510085.asia-northeast1.run.app', data=img_b64_full, headers={'Content-Type': 'text/plain'})
                        if len(ocr_res.text.strip()) >= 4:
                            captcha_code = ocr_res.text.strip()
                            log_step(f"    私人 API 识别成功: {captcha_code}")
                    except Exception as e:
                        log_step(f"    私人 API 报错或已失效: {e}")
                else:
                    gemini_attempt = attempt - 3 
                    key_index = (gemini_attempt - 1) % len(gemini_keys)
                    current_gemini_key = gemini_keys[key_index]
                    
                    log_step(f"    >>> 开始第 {attempt} 次尝试 (主力军：Gemini 3.1 Flash Lite | Key: {key_index + 1}) <<<")
                    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={current_gemini_key}"
                    gemini_prompt = "这是一张包含日文平假名的验证码图片，上面有很重的黑色干扰划线。请你忽略干扰线，仔细辨认图片中的平假名，并将它们逐个转换为对应的 6 位半角阿拉伯数字。例如：如果图片里写着「いちななきゅうぜろはちろく」，你就输出「179086」。绝对不要包含解题过程，只能输出 6 位连续数字！如果你看不清，尽最大努力猜测！"
                    
                    try:
                        gemini_res = requests.post(gemini_url, json={"contents": [{"parts": [{"text": gemini_prompt}, {"inline_data": {"mime_type": mime_type, "data": b64_data}}]}]}).json()
                        if 'candidates' in gemini_res:
                            raw_text = gemini_res['candidates'][0]['content']['parts'][0]['text'].strip()
                            match = re.search(r'\d{6}', raw_text)
                            if match: 
                                captcha_code = match.group(0)
                                log_step(f"    Gemini 提取成功: {captcha_code}")
                    except Exception as e:
                        log_step(f"    Gemini 请求报错: {e}")

                if not captcha_code: captcha_code = "000000" 
                page.evaluate(f"""(code) => {{ let input = document.querySelector('[placeholder*="上の画像"]'); if (input) {{ input.value = code; input.dispatchEvent(new Event('input', {{ bubbles: true }})); }} }}""", captcha_code)

                cf_container = page.locator(".cf-turnstile")
                if cf_container.count() > 0:
                    site_key = cf_container.first.get_attribute("data-sitekey")
                    action = cf_container.first.get_attribute("data-action")
                    cdata = cf_container.first.get_attribute("data-cdata")
                    
                    log_step("    呼叫 YesCaptcha 破解护盾...")
                    task_params = {
                        "type": "TurnstileTask",
                        "websiteURL": page.url,
                        "websiteKey": site_key,
                        "proxyType": "http",
                        "proxyAddress": PROXY_IP,
                        "proxyPort": int(PROXY_PORT),
                        "proxyLogin": PROXY_USER,
                        "proxyPassword": PROXY_PASS
                    }
                    if action: task_params["pageAction"] = action
                    if cdata: task_params["pageData"] = cdata
                    
                    create_res = requests.post("https://api.yescaptcha.com/createTask", json={"clientKey": YES_KEY, "task": task_params}).json()
                    if create_res.get("errorId") != 0: raise Exception(f"YesCaptcha 创建失败: {create_res}")
                    task_id = create_res["taskId"]
                    cf_token = None
                    
                    for i in range(20):
                        time.sleep(3)
                        res = requests.post("https://api.yescaptcha.com/getTaskResult", json={"clientKey": YES_KEY, "taskId": task_id}).json()
                        if res.get("status") == "ready":
                            cf_token = res["solution"]["token"]
                            break
                    
                    if not cf_token: raise Exception("YesCaptcha Token 超时！")
                    
                    log_step("    获取 CF 令牌成功，注入...")
                    page.evaluate(f"""(token) => {{
                        document.querySelectorAll('input[name="cf-turnstile-response"]').forEach(el => el.remove());
                        let cfInput = document.createElement('input'); cfInput.type = 'hidden'; cfInput.name = 'cf-turnstile-response'; cfInput.value = token; document.forms[0].appendChild(cfInput);
                        let cfContainer = document.querySelector('.cf-turnstile');
                        if (cfContainer) {{
                            cfContainer.style.border = "3px solid #2ECC71"; let cbName = cfContainer.getAttribute('data-callback');
                            if (cbName && typeof window[cbName] === 'function') {{ window[cbName](token); }} 
                            else {{ let btn = document.querySelector('input[type="submit"], button[type="submit"], #submit_button'); if (btn) {{ btn.removeAttribute('disabled'); btn.classList.remove('btn--disabled', 'btn--loading'); }} }}
                        }}
                    }}""", cf_token)
                
                log_step("    [5] 执行原生表单提交！")
                time.sleep(1) 
                page.evaluate("""() => { const submitBtn = document.querySelector('input[type="submit"], button[type="submit"], #submit_button'); if (submitBtn) submitBtn.click(); else document.forms[0].submit(); }""")
                log_step("    等待服务器处理 (8秒)...")
                page.wait_for_timeout(8000)
                
                error_msgs = page.locator(".errorMessage, .alert-danger, .error-text, [class*='error']")
                err_text = ""
                if error_msgs.count() > 0:
                    for i in range(error_msgs.count()):
                        txt = error_msgs.nth(i).inner_text().strip()
                        if txt: err_text += txt + " "
                
                if err_text:
                    log_step(f"    网页报错：{err_text}")
                    if attempt < max_attempts: continue
                    else: raise Exception(f"重试 {max_attempts} 次均失败: {err_text}")
                elif "extend/conf" in page.url or "extend/do" in page.url:
                    log_step("    页面未跳转，可能被静默拦截。")
                    if attempt < max_attempts: continue
                    else: raise Exception(f"连续 {max_attempts} 次被服务器拦截。")
                else:
                    is_success = True
                    break

            # 情景 2：冲塔续期成功！
            if is_success:
                log_step("续期成功！")
                update_github_cron(tomorrow_str, log_step)
                
                success_msg = f"[成功] <b>Github xserver-auto:恭喜！</b>\nVPS 续期大功告成！阶梯战术通关！\n\n[执行] <b>续期执行日:</b> {today_str}\n[原到期] <b>续期前到期日:</b> {expire_text}\n\n<i>(系统已安排明天 13:27 自动醒来复查状态，并进入深睡眠~)</i>"
                send_tg_msg(success_msg, process_logs)
                
                browser.close()
            else:
                raise Exception("未知原因退出循环。")

        except Exception as e:
            # 情景 3：任何报错卡死
            safe_e = html.escape(str(e))
            error_trace = traceback.format_exc()
            log_step(f"运行异常：{str(e)}")
            
            # 报错强制修改代码明天继续干它！
            update_github_cron(tomorrow_str, log_step)
            
            error_msg = f"[错误] <b>续期脚本出错了！</b>\n已安排明天重试。\n\n<b>错误详情:</b>\n<pre>{safe_e}</pre>"
            send_tg_msg(error_msg, process_logs)
            browser.close()

if __name__ == "__main__":
    run()
