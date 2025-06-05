import asyncio
import re
import json
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, parse_qs
import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import astrbot.api.message_components as Comp


@register(
    "astrbot_plugin_bilibili_summary",
    "VincenttHo", 
    "Bilibili视频字幕总结插件，获取B站视频字幕并使用LLM生成内容总结",
    "1.0.1",
    "https://github.com/VincenttHo/astrbot_plugin_bilibili_summary"
)
class BilibiliSummaryPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 配置参数
        self.openai_api_key = self.config.get("openai_api_key", "")
        self.openai_api_url = self.config.get("openai_api_url", "https://api.openai.com/v1/chat/completions")
        self.openai_model = self.config.get("openai_model", "gpt-3.5-turbo")
        self.bilibili_sessdata = self.config.get("bilibili_sessdata", "")
        self.request_interval = self.config.get("request_interval", 2.0)
        self.max_subtitle_length = self.config.get("max_subtitle_length", 8000)
        self.summary_prompt = self.config.get("summary_prompt", 
            "请根据以下视频字幕和简介，生成一个简洁明了的视频内容总结。总结应该包含视频的主要内容、关键信息和要点。请用中文回答。")
        
        # 验证配置
        if not self.openai_api_key:
            logger.warning("Bilibili Summary插件: 未配置OpenAI API密钥")
        if not self.bilibili_sessdata:
            logger.warning("Bilibili Summary插件: 未配置Bilibili SESSDATA，可能无法获取字幕")
            
        logger.info("Bilibili Summary插件: 初始化完成")

    def extract_bilibili_links_from_message(self, event: AstrMessageEvent) -> List[str]:
        """从消息链中提取所有可能的bilibili链接"""
        links = []

        # 从消息链中提取链接
        for component in event.message_obj.message:
            if isinstance(component, Comp.Plain):
                text = component.text
                # 查找文本中的bilibili链接
                extracted = self.extract_links_from_text(text)
                links.extend(extracted)

            elif isinstance(component, Comp.Reply):
                # 处理引用消息
                logger.info(f"检测到引用消息: {component}")
                reply_links = self.extract_bilibili_from_reply(event, component)
                links.extend(reply_links)

            elif isinstance(component, Comp.Forward):
                # 处理转发消息
                logger.info(f"检测到转发消息: {component}")
                forward_links = self.extract_bilibili_from_forward_message(component)
                links.extend(forward_links)

            elif hasattr(component, 'type') and component.type == 'Json':
                # 处理JSON消息组件（如QQ小程序卡片）
                logger.info(f"检测到JSON消息组件: {component}")
                json_links = self.extract_bilibili_from_json_component(component)
                links.extend(json_links)

        return links

    def extract_links_from_text(self, text: str) -> List[str]:
        """从文本中提取bilibili链接"""
        links = []
        url_patterns = [
            r'https?://(?:www\.)?bilibili\.com/video/[^\s\'"<>]+',
            r'https?://m\.bilibili\.com/video/[^\s\'"<>]+',
            r'https?://b23\.tv/[^\s\'"<>]+',
            r'BV[a-zA-Z0-9]{10}',
            r'av\d+',
        ]

        for pattern in url_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            links.extend(matches)

        return links

    def extract_bilibili_from_json_component(self, json_component) -> List[str]:
        """从JSON消息组件中提取bilibili链接"""
        links = []

        try:
            # 获取JSON数据
            json_data = None
            if hasattr(json_component, 'data'):
                if isinstance(json_component.data, str):
                    json_data = json.loads(json_component.data)
                else:
                    json_data = json_component.data

            if json_data:
                # 递归搜索JSON中的所有字符串值
                def search_json_for_links(obj):
                    found_links = []
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            if isinstance(value, str):
                                # 在字符串值中查找链接
                                found_links.extend(self.extract_links_from_text(value))
                            elif isinstance(value, (dict, list)):
                                found_links.extend(search_json_for_links(value))
                    elif isinstance(obj, list):
                        for item in obj:
                            if isinstance(item, str):
                                found_links.extend(self.extract_links_from_text(item))
                            elif isinstance(item, (dict, list)):
                                found_links.extend(search_json_for_links(item))
                    return found_links

                links.extend(search_json_for_links(json_data))

                # 特别处理bilibili小程序卡片
                if isinstance(json_data, dict):
                    # 检查是否是bilibili相关的小程序
                    meta = json_data.get('meta', {})
                    if meta:
                        detail = meta.get('detail_1', {})
                        if detail:
                            # 检查应用名称
                            title = detail.get('title', '')
                            if '哔哩哔哩' in title or 'bilibili' in title.lower():
                                # 提取qqdocurl字段中的链接
                                qqdocurl = detail.get('qqdocurl', '')
                                if qqdocurl:
                                    links.extend(self.extract_links_from_text(qqdocurl))

                                # 提取url字段中的链接
                                url = detail.get('url', '')
                                if url:
                                    links.extend(self.extract_links_from_text(url))

                logger.info(f"从JSON组件中提取到链接: {links}")

        except Exception as e:
            logger.warning(f"解析JSON消息组件失败: {str(e)}")

        return links

    def extract_bilibili_from_reply(self, event: AstrMessageEvent, reply_component) -> List[str]:
        """从引用消息中提取bilibili链接"""
        links = []

        try:
            # 引用消息的处理方式取决于平台
            # 对于QQ等平台，引用消息通常包含被引用消息的ID
            logger.info(f"引用消息详情: {reply_component}")

            # 尝试从引用消息的文本内容中提取链接
            if hasattr(reply_component, 'text') and reply_component.text:
                text = reply_component.text
                url_patterns = [
                    r'https?://(?:www\.)?bilibili\.com/video/[^\s]+',
                    r'https?://m\.bilibili\.com/video/[^\s]+',
                    r'https?://b23\.tv/[^\s]+',
                    r'BV[a-zA-Z0-9]{10}',
                    r'av\d+',
                ]

                for pattern in url_patterns:
                    matches = re.findall(pattern, text, re.IGNORECASE)
                    links.extend(matches)

            # 如果引用消息本身包含消息链，递归解析
            if hasattr(reply_component, 'chain') and reply_component.chain:
                for sub_component in reply_component.chain:
                    if isinstance(sub_component, Comp.Plain):
                        text = sub_component.text
                        links.extend(self.extract_links_from_text(text))
                    elif hasattr(sub_component, 'type') and sub_component.type == 'Json':
                        # 处理引用消息中的JSON组件
                        json_links = self.extract_bilibili_from_json_component(sub_component)
                        links.extend(json_links)

            # 兼容旧的message属性
            elif hasattr(reply_component, 'message') and reply_component.message:
                for sub_component in reply_component.message:
                    if isinstance(sub_component, Comp.Plain):
                        text = sub_component.text
                        links.extend(self.extract_links_from_text(text))
                    elif hasattr(sub_component, 'type') and sub_component.type == 'Json':
                        json_links = self.extract_bilibili_from_json_component(sub_component)
                        links.extend(json_links)

        except Exception as e:
            logger.warning(f"解析引用消息失败: {str(e)}")

        return links

    def extract_bilibili_from_forward_message(self, forward_component) -> List[str]:
        """从转发消息中提取bilibili链接"""
        links = []

        try:
            # 转发消息可能包含多种格式的内容
            logger.info(f"转发消息结构: {forward_component}")

            # 尝试从转发消息的各种属性中提取链接
            content_sources = []

            if hasattr(forward_component, 'content'):
                content_sources.append(str(forward_component.content))
            if hasattr(forward_component, 'text'):
                content_sources.append(str(forward_component.text))
            if hasattr(forward_component, 'title'):
                content_sources.append(str(forward_component.title))
            if hasattr(forward_component, 'summary'):
                content_sources.append(str(forward_component.summary))

            # 如果转发消息包含节点列表
            if hasattr(forward_component, 'nodes'):
                for node in forward_component.nodes:
                    if hasattr(node, 'content'):
                        for content_item in node.content:
                            if isinstance(content_item, Comp.Plain):
                                content_sources.append(content_item.text)

            # 在所有内容中查找bilibili链接
            for content in content_sources:
                links.extend(self.extract_links_from_text(content))

            # 特殊处理：查找bilibili卡片消息的特征
            # bilibili分享卡片通常包含特定的文本模式
            for content in content_sources:
                # 查找类似 "哔哩哔哩" 或 bilibili 相关的关键词
                if any(keyword in content.lower() for keyword in ['bilibili', '哔哩哔哩', 'b站']):
                    # 在这种内容中更积极地查找BV号
                    additional_links = self.extract_links_from_text(content)
                    links.extend(additional_links)

        except Exception as e:
            logger.warning(f"解析转发消息失败: {str(e)}")

        return links

    def parse_bilibili_url(self, input_str: str) -> Optional[str]:
        """解析bilibili视频链接，提取BV号或AV号"""
        if not input_str or not input_str.strip():
            return None

        input_str = input_str.strip()

        # 如果是纯BV号或AV号
        if re.match(r'^BV[a-zA-Z0-9]{10}$', input_str):
            return input_str
        if re.match(r'^[a-zA-Z0-9]{10}$', input_str):
            return 'BV' + input_str
        if re.match(r'^av\d+$', input_str, re.IGNORECASE):
            return input_str.lower()
        if re.match(r'^\d+$', input_str):
            return 'av' + input_str

        # 如果是URL链接
        if 'bilibili.com' in input_str or 'b23.tv' in input_str:
            try:
                parsed = urlparse(input_str)

                # 处理b23.tv短链接 - 需要重定向获取真实链接
                if 'b23.tv' in parsed.netloc:
                    return input_str  # 返回原链接，后续处理重定向

                # 处理标准bilibili链接
                if 'bilibili.com' in parsed.netloc:
                    path = parsed.path

                    # 匹配 /video/BVxxxxx 或 /video/avxxxxx
                    video_match = re.search(r'/video/(BV[a-zA-Z0-9]{10}|av\d+)', path)
                    if video_match:
                        video_id = video_match.group(1)
                        if video_id.startswith('BV'):
                            return video_id
                        elif video_id.startswith('av'):
                            return video_id.lower()

                    # 处理查询参数中的bvid
                    query_params = parse_qs(parsed.query)
                    if 'bvid' in query_params:
                        bvid = query_params['bvid'][0]
                        if re.match(r'^BV[a-zA-Z0-9]{10}$', bvid):
                            return bvid

            except Exception as e:
                logger.warning(f"解析URL失败: {str(e)}")

        return None

    async def resolve_short_url(self, short_url: str) -> Optional[str]:
        """解析b23.tv短链接"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(short_url, headers=headers, allow_redirects=False) as response:
                    if response.status in [301, 302, 303, 307, 308]:
                        location = response.headers.get('Location')
                        if location:
                            return self.parse_bilibili_url(location)

            return None
        except Exception as e:
            logger.error(f"解析短链接失败: {str(e)}")
            return None

    async def convert_av_to_bv(self, av_id: str) -> Optional[str]:
        """通过AV号获取BV号"""
        try:
            # 提取AV号中的数字
            av_num = re.search(r'av(\d+)', av_id, re.IGNORECASE)
            if not av_num:
                return None

            aid = av_num.group(1)
            url = f"https://api.bilibili.com/x/web-interface/view?aid={aid}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('code') == 0:
                            bvid = data.get('data', {}).get('bvid')
                            if bvid:
                                logger.info(f"成功转换AV号到BV号: {av_id} -> {bvid}")
                                return bvid

            await asyncio.sleep(self.request_interval)
            return None
        except Exception as e:
            logger.error(f"AV号转换失败: {str(e)}")
            return None

    @filter.command("bs")
    async def bilibili_summary(self, event: AstrMessageEvent, video_input: str = None):
        """获取bilibili视频字幕总结"""

        # 如果没有提供参数，尝试从消息中自动提取链接
        if not video_input or not video_input.strip():
            # 从当前消息中提取链接
            extracted_links = self.extract_bilibili_links_from_message(event)
            logger.info(f"提取到的所有链接: {extracted_links}")

            if extracted_links:
                # 如果找到链接，使用第一个
                video_input = extracted_links[0]
                logger.info(f"从消息中自动提取到链接: {video_input}")
            else:
                # 如果没有找到链接，显示帮助信息
                yield event.plain_result(
                    "使用方法：\n"
                    "1. /bs [视频链接或BV号]\n"
                    "2. 引用包含bilibili链接的消息后发送 /bs\n"
                    "3. 转发bilibili视频卡片后发送 /bs\n\n"
                    "支持格式：\n"
                    "• BV号：BV1jv7YzJED2 或 1jv7YzJED2\n"
                    "• AV号：av123456 或 123456\n"
                    "• 完整链接：https://www.bilibili.com/video/BV1jv7YzJED2\n"
                    "• 手机链接：https://m.bilibili.com/video/BV1jv7YzJED2\n"
                    "• 短链接：https://b23.tv/xxxxx"
                )
                return

        # 解析输入的视频标识
        video_id = self.parse_bilibili_url(video_input.strip())

        # 如果是短链接，需要先解析
        if video_input.strip().startswith('https://b23.tv/'):
            video_id = await self.resolve_short_url(video_input.strip())

        if not video_id:
            yield event.plain_result("❌ 无法识别的视频链接或ID格式，请检查后重试")
            return

        # 直接使用video_id，get_video_info方法会处理AV号和BV号
            
        # 检查配置
        if not self.openai_api_key:
            yield event.plain_result("❌ 未配置OpenAI API密钥，请联系管理员配置插件")
            return
            
        yield event.plain_result(f"🔍 正在处理视频 {video_id}，请稍候...")

        try:
            # 获取视频基本信息
            video_info = await self.get_video_info(video_id)
            if not video_info:
                yield event.plain_result("❌ 获取视频信息失败，请检查BV号是否正确")
                return

            aid = video_info.get('aid')
            cid = video_info.get('cid')
            title = video_info.get('title', '未知标题')
            desc = video_info.get('desc', '')

            if not aid or not cid:
                yield event.plain_result("❌ 无法获取视频的aid或cid")
                return

            # 获取字幕
            subtitle_text = await self.get_subtitle(aid, cid)
            if not subtitle_text:
                yield event.plain_result("❌ 未找到可用的字幕")
                return

            # 生成总结
            summary = await self.generate_summary(title, desc, subtitle_text)
            if summary:
                # 构建完整的结果信息
                result_message = f"📺 视频标题：{title}\n\n📋 内容总结：\n{summary}"
                yield event.plain_result(result_message)
            else:
                yield event.plain_result("❌ 生成总结失败")

        except Exception as e:
            logger.error(f"Bilibili Summary插件: 处理请求时发生错误: {str(e)}")
            yield event.plain_result(f"❌ 处理请求时发生错误: {str(e)}")

    async def get_video_info(self, video_id: str) -> Optional[Dict[str, Any]]:
        """获取视频基本信息"""
        # 根据视频ID类型构建URL
        if video_id.startswith('av'):
            # AV号
            aid = re.search(r'av(\d+)', video_id, re.IGNORECASE).group(1)
            url = f"https://api.bilibili.com/x/web-interface/view?aid={aid}"
        else:
            # BV号
            url = f"https://api.bilibili.com/x/web-interface/view?bvid={video_id}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        code = data.get('code')
                        if code == 0:
                            video_data = data.get('data', {})
                            pages = video_data.get('pages', [])
                            if pages:
                                result = {
                                    'aid': video_data.get('aid'),
                                    'cid': pages[0].get('cid'),  # 取第一个分P
                                    'title': video_data.get('title'),
                                    'desc': video_data.get('desc')
                                }
                                logger.info(f"成功获取视频信息: {result['title']}")
                                return result
                        else:
                            message = data.get('message', '未知错误')
                            logger.warning(f"Bilibili API返回错误: code={code}, message={message}")
                    else:
                        logger.warning(f"HTTP请求失败: status={response.status}")

            await asyncio.sleep(self.request_interval)
            return None
        except Exception as e:
            logger.error(f"获取视频信息失败: {str(e)}")
            return None

    async def get_subtitle(self, aid: int, cid: int) -> Optional[str]:
        """获取视频字幕"""
        url = f"https://api.bilibili.com/x/player/wbi/v2?aid={aid}&cid={cid}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.bilibili.com/'
        }

        # 如果有SESSDATA，添加到Cookie中
        if self.bilibili_sessdata:
            headers['Cookie'] = f'SESSDATA={self.bilibili_sessdata}'

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        code = data.get('code')
                        if code == 0:
                            subtitle_data = data.get('data', {}).get('subtitle', {})
                            subtitles = subtitle_data.get('subtitles', [])

                            if not subtitles:
                                # 检查是否需要登录
                                need_login = data.get('data', {}).get('need_login_subtitle', False)
                                if need_login:
                                    logger.warning("获取字幕需要登录，请检查SESSDATA配置")
                                else:
                                    logger.warning("该视频没有可用的字幕")
                                return None

                            # 优先选择中文字幕
                            selected_subtitle = None
                            for subtitle in subtitles:
                                lan_doc = subtitle.get('lan_doc', '')
                                if '中文' in lan_doc:
                                    selected_subtitle = subtitle
                                    logger.info(f"选择中文字幕: {lan_doc}")
                                    break

                            # 如果没有中文字幕，选择第一个
                            if not selected_subtitle and subtitles:
                                selected_subtitle = subtitles[0]
                                lan_doc = selected_subtitle.get('lan_doc', '未知语言')
                                logger.info(f"未找到中文字幕，选择: {lan_doc}")

                            if selected_subtitle:
                                subtitle_url = selected_subtitle.get('subtitle_url')
                                if subtitle_url:
                                    # 确保URL是完整的
                                    if subtitle_url.startswith('//'):
                                        subtitle_url = 'https:' + subtitle_url
                                    elif not subtitle_url.startswith('http'):
                                        subtitle_url = 'https://' + subtitle_url

                                    return await self.download_subtitle(subtitle_url)
                        else:
                            message = data.get('message', '未知错误')
                            logger.warning(f"获取字幕API返回错误: code={code}, message={message}")
                    else:
                        logger.warning(f"获取字幕HTTP请求失败: status={response.status}")

            await asyncio.sleep(self.request_interval)
            return None
        except Exception as e:
            logger.error(f"获取字幕失败: {str(e)}")
            return None

    async def download_subtitle(self, subtitle_url: str) -> Optional[str]:
        """下载字幕文件并提取文本"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.bilibili.com/'
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(subtitle_url, headers=headers) as response:
                    if response.status == 200:
                        subtitle_data = await response.json()
                        body = subtitle_data.get('body', [])

                        if not body:
                            logger.warning("字幕文件为空")
                            return None

                        # 提取所有字幕文本
                        subtitle_texts = []
                        for item in body:
                            content = item.get('content', '').strip()
                            if content:
                                subtitle_texts.append(content)

                        if not subtitle_texts:
                            logger.warning("字幕内容为空")
                            return None

                        full_text = ' '.join(subtitle_texts)
                        original_length = len(full_text)

                        # 限制长度
                        if original_length > self.max_subtitle_length:
                            full_text = full_text[:self.max_subtitle_length] + "..."
                            logger.info(f"字幕文本过长({original_length}字符)，已截断到{self.max_subtitle_length}字符")
                        else:
                            logger.info(f"成功获取字幕文本({original_length}字符)")

                        return full_text
                    else:
                        logger.warning(f"下载字幕HTTP请求失败: status={response.status}")

            await asyncio.sleep(self.request_interval)
            return None
        except Exception as e:
            logger.error(f"下载字幕失败: {str(e)}")
            return None

    async def generate_summary(self, title: str, desc: str, subtitle_text: str) -> Optional[str]:
        """使用LLM生成视频总结"""
        # 构建提示词
        content = f"视频标题：{title}\n\n"
        if desc and desc.strip():
            content += f"视频简介：{desc}\n\n"
        content += f"视频字幕：\n{subtitle_text}"

        messages = [
            {"role": "system", "content": self.summary_prompt},
            {"role": "user", "content": content}
        ]

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.openai_api_key}'
        }

        payload = {
            "model": self.openai_model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1000
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.openai_api_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        choices = data.get('choices', [])
                        if choices:
                            content = choices[0].get('message', {}).get('content', '').strip()
                            if content:
                                logger.info(f"成功生成总结({len(content)}字符)")
                                return content
                            else:
                                logger.warning("LLM返回空内容")
                                return None
                        else:
                            logger.warning("LLM响应中没有choices")
                            return None
                    else:
                        error_text = await response.text()
                        logger.error(f"LLM API请求失败: {response.status} - {error_text}")
                        return None
        except Exception as e:
            logger.error(f"调用LLM API失败: {str(e)}")
            return None

    async def terminate(self):
        """插件卸载时调用"""
        logger.info("Bilibili Summary插件: 已卸载")
