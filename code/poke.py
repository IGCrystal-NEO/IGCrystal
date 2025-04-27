import os
import random
import shutil
import time
import yaml
from astrbot.api.all import (
    AstrMessageEvent,
    Context,
    EventMessageType,
    Star,
    event_message_type,
    register,
)

@register("poke_monitor", "Your Name", "监控戳一戳事件插件", "1.3.0")
class PokeMonitorPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.user_poke_timestamps = {}
        # 构建配置文件路径
        config_dir = os.path.join("data", "plugins", "astrbot_plugin_pock")
        config_path = os.path.join(config_dir, "config.yml")

        # 检查配置文件是否存在，若不存在则创建并写入默认值
        if not os.path.exists(config_path):
            self._create_default_config(config_path)

        try:
            # 读取配置文件
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            self.poke_responses = self.config.get('poke_responses', [])
            self.feature_switches = self.config.get('feature_switches', {})
            self.poke_back_probability = self.config['poke_back_probability']
            self.super_poke_probability = self.config['super_poke_probability']
        except FileNotFoundError:
            pass
        except Exception as e:
            pass

        self._clean_legacy_directories()

    def _create_default_config(self, config_path):
        """创建默认配置文件"""
        default_config = {
            # 戳一戳回复消息
            "poke_responses": [
                "别戳啦！",
                "哎呀，还戳呀，别闹啦！",
                "别戳我啦  你要做什么  不理你了",
                "戳你大坝！",
                "煞笔玩意，成天就知道戳戳！"
            ],
            # 功能开关
            "feature_switches": {
                "poke_response_enabled": True,
                "poke_back_enabled": True
            },
            # 戳 Bot 反击相关概率
            "poke_back_probability": 0.3,
            "super_poke_probability": 0.1
        }
        # 创建配置文件所在目录
        config_dir = os.path.dirname(config_path)
        os.makedirs(config_dir, exist_ok=True)
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            pass

    def _clean_legacy_directories(self):
        """安全清理旧目录（仅删除特定目录）"""
        legacy_dirs = [
            os.path.abspath("./data/plugins/poke_monitor"),  # 旧版本目录
            os.path.abspath("./data/plugins/plugins/poke_monitor")  # 防止误删其他插件
        ]

        for path in legacy_dirs:
            try:
                if os.path.exists(path):
                    shutil.rmtree(path)
            except Exception as e:
                pass

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        message_obj = event.message_obj
        raw_message = message_obj.raw_message
        is_super = False  # 超级加倍标志

        if raw_message.get('post_type') == 'notice' and \
                raw_message.get('notice_type') == 'notify' and \
                raw_message.get('sub_type') == 'poke':
            bot_id = raw_message.get('self_id')
            sender_id = raw_message.get('user_id')
            target_id = raw_message.get('target_id')

            now = time.time()
            three_minutes_ago = now - 3 * 60

            # 清理旧记录
            if sender_id in self.user_poke_timestamps:
                self.user_poke_timestamps[sender_id] = [
                    t for t in self.user_poke_timestamps[sender_id] if t > three_minutes_ago
                ]

            if bot_id and sender_id and target_id:
                # 用户戳机器人
                if str(target_id) == str(bot_id):
                    # 记录戳一戳
                    if sender_id not in self.user_poke_timestamps:
                        self.user_poke_timestamps[sender_id] = []
                    self.user_poke_timestamps[sender_id].append(now)

                    # 文本回复
                    if self.feature_switches.get('poke_response_enabled', True):
                        poke_count = len(self.user_poke_timestamps[sender_id])
                        if poke_count < 4:
                            response = self.poke_responses[poke_count - 1] if poke_count <= len(self.poke_responses) else self.poke_responses[-1]
                            yield event.plain_result(response)

                    # 概率戳回
                    if self.feature_switches.get('poke_back_enabled', True) and random.random() < self.poke_back_probability:
                        if random.random() < self.super_poke_probability:
                            poke_times = 10
                            yield event.plain_result("喜欢戳是吧")
                            is_super = True
                        else:
                            poke_times = 1
                            yield event.plain_result("戳回去")

                        # 发送戳一戳
                        if event.get_platform_name() == "aiocqhttp":
                            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                            assert isinstance(event, AiocqhttpMessageEvent)
                            client = event.bot
                            group_id = raw_message.get('group_id')
                            payloads = {"user_id": sender_id}
                            if group_id:
                                payloads["group_id"] = group_id
                            for _ in range(poke_times):
                                try:
                                    await client.api.call_action('send_poke', **payloads)
                                except Exception as e:
                                    pass
