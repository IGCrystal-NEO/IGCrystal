from astrbot.api.all import *
import re
import aiohttp
import json

@register("nodetest", "Jason.Joestar", "一个伪造转发消息的插件", "1.0.0", "插件仓库URL")
class NodeTestPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
    
    async def get_qq_nickname(self, qq_number):
        """获取QQ昵称"""
        # 使用新的API
        url = f"http://api.mmp.cc/api/qqname?qq={qq_number}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    try:
                        # 解析JSON响应
                        data = await response.json()
                        logger.debug(f"QQ昵称API返回: {data}")
                        
                        # 检查返回码并获取昵称
                        if data.get("code") == 200 and "data" in data and "name" in data["data"]:
                            nickname = data["data"]["name"]
                            logger.debug(f"成功提取昵称: {nickname}")
                            if nickname:  # 确保昵称不为空
                                return nickname
                    except Exception as e:
                        logger.debug(f"解析昵称出错: {str(e)}")
        
        # 如果获取失败，返回QQ号作为昵称
        return f"用户{qq_number}"
    
    @event_message_type(EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        '''监听所有消息并检测伪造消息请求'''
        from astrbot.api.message_components import Node, Plain, Nodes
        
        message_text = event.message_str
        
        # 仅在消息中包含"伪造消息"时进行处理
        if "伪造消息" not in message_text:
            return
        
        # 新的正则表达式匹配格式: 伪造消息 QQ号 内容 | QQ号 内容 | ...
        pattern = r'伪造消息((?:\s+\d+\s+[^|]+\|)+)'
        match = re.search(pattern, message_text)
        
        if not match:
            yield event.plain_result("格式错误，请使用：伪造消息 QQ号 内容 | QQ号 内容 | ...")
            return
        
        content = match.group(1).strip()
        segments = content.split('|')
        nodes_list = []
        
        for segment in segments:
            if not segment.strip():
                continue
                
            # 分离每个用户的QQ号和content
            parts = segment.strip().split(maxsplit=1)
            if len(parts) < 2:
                continue
                
            qq_number, content = parts
            
            # 获取QQ昵称
            nickname = await self.get_qq_nickname(qq_number)
            
            # 创建节点
            node = Node(
                uin=int(qq_number),
                name=nickname,
                content=[Plain(content)]
            )
            nodes_list.append(node)
        
        if nodes_list:
            # 创建Nodes对象并发送
            nodes = Nodes(nodes=nodes_list)
            yield event.chain_result([nodes])
        else:
            yield event.plain_result("未能解析出任何有效的消息节点")
            
    async def terminate(self):
        '''插件被卸载/停用时调用'''
        pass
