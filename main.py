import json, requests, re, os, time, random, ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
from preferences import prefs
from logger import logger

IP_LIST = {}
accounts_list = {}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Connection': 'keep-alive'
}

# ====================== Webcat 全局配置区域 ======================
WEBCAT_SIGN_URL = 'http://source.webcat.top/user/qd'
WEBCAT_REWARD_URL = 'http://source.webcat.top/source/reward'
WEBCAT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.0.0 Mobile Safari/537.36',
    'Accept-Encoding': 'gzip, deflate',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'Origin': 'http://space.webcat.top',
    'X-Requested-With': 'mark.via',
    'Referer': 'http://space.webcat.top/',
    'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
}


def validate_ip_port(ip, port):
    try:
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.is_multicast or ip_obj.is_unspecified:
            return False
    except ValueError:
        return False
    ip_parts = ip.split('.')
    for part in ip_parts:
        if not 0 <= int(part) <= 255:
            return False
    if not 1 <= int(port) <= 65535:
        return False
    return True

def verify(proxy):
    target_url = 'https://bbs.binmt.cc/forum.php?mod=guide&view=hot'
    proxies = {
        'https': f'http://{proxy}',
        'http': f'http://{proxy}'
    }
    start_time = time.time()
    try:
        response = requests.get(target_url, headers=headers, proxies=proxies, timeout=20)
        return proxy, response.ok, int((time.time() - start_time) * 1000)
    except:
        return proxy, False, -1

def is_phone_number(username):
    pattern = r'^1[3-9]\d{9}$'
    return re.match(pattern, username) is not None

def format_phone_number(phone):
    if len(phone) == 11:
        return f"{phone[:3]}****{phone[-4:]}"
    return phone

def format_username(username):
    if is_phone_number(username):
        return format_phone_number(username)
    return username

def load():
    myset = set()
    successful_proxies = []
    try:
        with open("src/ips.txt", "r", encoding="utf-8") as f:
            for line in f:
                ip = line.strip()
                if ":" not in ip or not ip: continue
                newIp, newPort = ip.split(':', 1)
                if not validate_ip_port(newIp, newPort): continue
                myset.add(ip)
    except Exception as e:
        pass
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(verify, proxy) for proxy in myset]
        for future in as_completed(futures):
            proxy, is_valid, requestTime = future.result()
            if is_valid:
                successful_proxies.append((proxy, requestTime))
    successful_proxies.sort(key=lambda x: x[1])
    logger.info("可用ip代理:")
    for index, (proxy, req_time) in enumerate(successful_proxies, 1):
        logger.info(f"{index}: {proxy} - {req_time}ms")
        IP_LIST[proxy] = True

def checkIn(user, pwd, ip):
    req = requests.session()
    req.headers.update(headers)
    proxies = {
        'http': f'http://{ip}',
        'https': f'http://{ip}'
    }
    req.proxies = proxies
    logger.info(f"{format_username(user)} 开始签到")
    try:
        url = 'https://bbs.binmt.cc/member.php?mod=logging&action=login&infloat=yes&handlekey=login&inajax=1&ajaxtarget=fwin_content_login'
        resp = req.get(url, proxies=proxies, timeout=20)
        resp.encoding = resp.apparent_encoding
        if resp.ok:
            content = resp.text
            _loginhash = loginhash(content)
            _formhash = formhash(content)
            url = f'https://bbs.binmt.cc/member.php?mod=logging&action=login&loginsubmit=yes&handlekey=login&loginhash={_loginhash}&inajax=1'
            data = {
                'formhash': _formhash,
                'referer': 'https://bbs.binmt.cc/k_misign-sign.html',
                'fastloginfield': 'username',
                'username': user,
                'password': pwd,
                'questionid': '0',
                'answer': '',
                'agreebbrule': ''
            }
            resp = req.post(url, data=data, proxies=proxies, timeout=20)
            resp.encoding = resp.apparent_encoding
            if resp.ok:
                if '失败' in resp.text:
                    del accounts_list[user]
                    logger.warning("密码错误")
                    return
                url = 'https://bbs.binmt.cc/k_misign-sign.html'
                resp = req.get(url, proxies=proxies, timeout=20)
                resp.encoding = resp.apparent_encoding
                _formhash = formhash(resp.text)
                code = resp.status_code
                if resp.ok:
                    url = f'https://bbs.binmt.cc/plugin.php?id=k_misign:sign&operation=qiandao&format=text&formhash={_formhash}'
                    resp = req.get(url, proxies=proxies, timeout=20)
                    resp.encoding = resp.apparent_encoding
                    if '已签' in resp.text:
                        del accounts_list[user]
                        logger.info(CDATA(resp.text))
                        prefs.put(user, prefs.getTime())
                        return True
                    logger.warning(CDATA(resp.text))
    except Exception as e:
        logger.warning(f"异常: {str(e)}")
        IP_LIST[ip] = False
    return False

def loginhash(data):
    pattern = r'loginhash.*?=(.*?)[\'"\]>'
    match = re.search(pattern, data, re.IGNORECASE | re.UNICODE)
    if match and match.group(1):
        return match.group(1).strip()
    return ''

def formhash(data):
    pattern = r'formhash[\'"].*?value=[\'"](.*?)[\'"].*?/>'
    match = re.search(pattern, data, re.IGNORECASE | re.UNICODE)
    if match and match.group(1):
        return match.group(1).strip()
    return ''

def CDATA(data):
    pattern = r'CDATA.*?(.*?)\]>'
    match = re.search(pattern, data, re.IGNORECASE | re.UNICODE)
    if match and match.group(1):
        return match.group(1).strip('[]')
    return ''

# ====================== Webcat 签到与领取奖励 ======================

def extract_coin_amount(response_text):
    """
    尝试从签到返回结果中解析获取的牛币数量。
    优先尝试 JSON 中的常见字段名，若无法解析则返回 None。
    """
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        # 尝试从文本中提取数字（如"获得10牛币"）
        match = re.search(r'(获得|得到|奖励|签到成功).*?(\d+)', response_text)
        if match:
            return int(match.group(2))
        return None

    # 可能的字段路径（按优先级排序）
    possible_paths = [
        ['data', 'reward'],
        ['data', 'amount'],
        ['data', 'coin'],
        ['data', 'coins'],
        ['data', 'nb'],
        ['data', 'niubi'],
        ['data', 'money'],
        ['data', 'point'],
        ['data', 'points'],
        ['data', 'score'],
        ['reward'],
        ['amount'],
        ['coin'],
        ['coins'],
        ['nb'],
        ['niubi'],
        ['money'],
        ['point'],
        ['points'],
        ['score'],
    ]

    for path in possible_paths:
        current = data
        try:
            for key in path:
                current = current[key]
            if isinstance(current, (int, float)) and current > 0:
                return int(current)
            if isinstance(current, str):
                num_match = re.search(r'\d+', current)
                if num_match:
                    return int(num_match.group())
        except (KeyError, TypeError):
            continue

    return None


def webcat_request(token, url, extra_data=None):
    """
    Webcat 公共请求函数，仿照 PHP 中的 doRequest 逻辑
    """
    post_data = {'token': token}
    if extra_data:
        post_data.update(extra_data)

    try:
        resp = requests.post(
            url,
            data=post_data,
            headers=WEBCAT_HEADERS,
            timeout=30,
            verify=False
        )
        return {
            'http_code': resp.status_code,
            'response': resp.text,
            'json_data': None
        }
    except requests.RequestException as e:
        return {
            'http_code': 0,
            'response': '',
            'json_data': None,
            'error': str(e)
        }


def webcat_sign_and_reward(token, source_id, loop_times, interval):
    """
    对单个 token 执行签到，并根据签到结果自动领取相同数量的牛币奖励
    """
    for i in range(1, loop_times + 1):
        logger.info(f"Token {mask_token(token)} 第 {i}/{loop_times} 次签到")

        # 1. 签到请求
        sign_res = webcat_request(token, WEBCAT_SIGN_URL)

        if sign_res.get('error'):
            logger.warning(f"签到请求异常: {sign_res['error']}")
            continue

        logger.info(f"签到 HTTP 状态码: {sign_res['http_code']}")
        logger.info(f"签到返回: {sign_res['response']}")

        # 2. 解析牛币数量
        coin_amount = extract_coin_amount(sign_res['response'])

        if coin_amount is None:
            logger.warning("未能从签到结果中解析牛币数量，默认使用 1")
            coin_amount = 1
        else:
            logger.info(f"签到获得牛币: {coin_amount}")

        # 3. 自动领取奖励（amount = 签到获得的牛币数）
        reward_res = webcat_request(token, WEBCAT_REWARD_URL, {
            'sourceId': source_id,
            'amount': coin_amount
        })

        if reward_res.get('error'):
            logger.warning(f"领取奖励请求异常: {reward_res['error']}")
        else:
            logger.info(f"领取奖励 HTTP 状态码: {reward_res['http_code']}")
            logger.info(f"领取奖励返回: {reward_res['response']}")

        if i < loop_times:
            time.sleep(interval)


def mask_token(token):
    """对 token 进行脱敏显示"""
    if len(token) <= 8:
        return token[:2] + '****'
    return token[:4] + '****' + token[-4:]


def start_mt():
    """原有 MT 论坛签到入口"""
    ACCOUNTS = os.environ.get("ACCOUNTS", "")
    if not ACCOUNTS:
        logger.warning('github ACCOUNTS变量未设置，跳过MT论坛签到')
        return
    for duo in ACCOUNTS.split("\n"):
        if ':' not in duo:
            continue
        username, password = duo.split(':', 1)
        username = username.strip()
        password = password.strip()
        YiQianDao = prefs.get(username, "") == prefs.getTime()
        if username and password and not YiQianDao:
            accounts_list[username] = password
        elif YiQianDao:
            logger.info(f"{format_username(username)} 今日已签, 跳过签到")
    if accounts_list:
        load()
    if IP_LIST:
        keys = list(accounts_list.keys())
        total = len(keys)
        for i, username in enumerate(keys):
            for proxy, status in IP_LIST.items():
                if not status: continue
                try:
                    if checkIn(username, accounts_list[username], proxy): break
                except:
                    pass
            if i < total - 1:
                time.sleep(3)


def start_webcat():
    """新增 Webcat 签到与自动领取奖励入口"""
    tokens_env = os.environ.get("WEBCAT_TOKENS", "")
    source_id_env = os.environ.get("WEBCAT_SOURCE_ID", "")
    loop_times = int(os.environ.get("WEBCAT_LOOP_TIMES", "1"))
    interval = int(os.environ.get("WEBCAT_INTERVAL", "1"))

    if not tokens_env:
        logger.info('WEBCAT_TOKENS 未设置，跳过 Webcat 签到')
        return

    if not source_id_env:
        logger.warning('WEBCAT_SOURCE_ID 未设置，请填写领取奖励的 sourceId')
        return

    try:
        source_id = int(source_id_env)
    except ValueError:
        logger.warning('WEBCAT_SOURCE_ID 必须是整数')
        return

    token_list = [t.strip() for t in tokens_env.split("\n") if t.strip()]
    if not token_list:
        logger.info('WEBCAT_TOKENS 为空，跳过 Webcat 签到')
        return

    logger.info(f"===== Webcat 签到开始，共 {len(token_list)} 个 Token，每个执行 {loop_times} 次 =====")
    for idx, token in enumerate(token_list, 1):
        logger.info(f"--- 第 {idx}/{len(token_list)} 个账号 ---")
        try:
            webcat_sign_and_reward(token, source_id, loop_times, interval)
        except Exception as e:
            logger.warning(f"Token {mask_token(token)} 处理异常: {str(e)}")
        if idx < len(token_list):
            time.sleep(2)
    logger.info("===== Webcat 签到结束 =====")


if __name__ == '__main__':
    start_mt()
    start_webcat()
    prefs.save()
