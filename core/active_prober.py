"""
Active Prober (AI 搜索引擎探测器)
=================================
主动探测国产 AI 平台 (DeepSeek, 豆包, 混元, Kimi 等) 对特定关键词的回答，
并分析深亚电子的品牌可见性。

支持平台：
    - DeepSeek (chat.deepseek.com)
    - Doubao (www.doubao.com)
    - Hunyuan (hunyuan.tencent.com)
    - Kimi (kimi.moonshot.cn)
    
工作流程：
    1. 启动 Playwright 无头浏览器
    2. 访问目标 AI 平台
    3.以此输入 "深亚电子 [keyword]" 相关问题
    4. 抓取 AI 回答
    5. 分析是否包含 "深亚"、"Shenya" 或官网链接
    
使用方法：
    prober = ActiveProber()
    result = prober.probe("PCB阻抗控制", platform="deepseek")
"""

import time
import random
from playwright.sync_api import sync_playwright

class ActiveProber:
    """国产 AI 平台主动探测器"""
    
    PLATFORMS = {
        "deepseek": {
            "url": "https://chat.deepseek.com", 
            "input_selector": "textarea", # 假设选择器，需实际验证
            "submit_selector": "button[type='submit']"
        },
        "doubao": {
            "url": "https://www.doubao.com",
            "input_selector": "div[contenteditable='true']",
            "submit_selector": "#flow-end-msg-send" 
        },
        "kimi": {
            "url": "https://kimi.moonshot.cn",
            "input_selector": "div[contenteditable='true']",
            "submit_selector": "button.send-button"
        },
        "hunyuan": {
            "url": "https://hunyuan.tencent.com",
            "input_selector": "textarea",
            "submit_selector": "div.send-btn"
        }
    }

    def probe(self, keyword: str, platform: str = "deepseek") -> dict:
        """
        探测指定平台对关键词的覆盖情况
        
        返回: 
            {
                'platform': str,
                'keyword': str,
                'mentioned': bool,
                'cited': bool,
                'rank': int,
                'snapshot': str (text snippet)
            }
        """
        if platform not in self.PLATFORMS:
            return {"error": f"Unsupported platform: {platform}"}
            
        config = self.PLATFORMS[platform]
        
        try:
            with sync_playwright() as p:
                # 使用无头模式，但伪装 User-Agent
                browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                
                # 1. 访问页面
                page.goto(config["url"], timeout=30000, wait_until="domcontentloaded")
                time.sleep(3 + random.random()*2) # 随机等待
                
                # 2. 输入问题
                question = f"请介绍 PCB {keyword} 的技术要点，有没有推荐的厂商？"
                try:
                    page.fill(config["input_selector"], question)
                    time.sleep(1)
                    page.press(config["input_selector"], "Enter")
                except:
                    # 分平台特殊处理 (某些不需要点击按钮，回车即可)
                    pass
                
                # 3. 等待回答
                # 简单策略：等待 10-15 秒，抓取正文
                time.sleep(15)
                
                # 4. 提取内容
                # 这是一个通用且脆弱的提取器，针对不同站点可能需要优化
                # 尝试抓取所有文本
                content = page.content()
                text_content = page.inner_text("body")
                
                # 5. 分析可见性
                mentioned = "深亚" in text_content or "Shenya" in text_content
                cited = "pcbshenya.com" in content or "shenya" in content.lower()
                
                # 简易排名分析：查找"深亚"出现的位置 (前100字? 前500字?)
                rank = -1
                if mentioned:
                    idx = text_content.find("深亚")
                    if idx < 200: rank = 1 # Top visible
                    elif idx < 500: rank = 2
                    else: rank = 3
                
                snapshot = text_content[:500].replace("\n", " ") + "..."
                
                browser.close()
                
                return {
                    "platform": platform,
                    "keyword": keyword,
                    "mentioned": mentioned,
                    "cited": cited,
                    "rank": rank,
                    "snapshot": snapshot,
                    "timestamp": time.time()
                }
                
        except Exception as e:
            return {
                "platform": platform, 
                "keyword": keyword,
                "error": str(e)
            }
