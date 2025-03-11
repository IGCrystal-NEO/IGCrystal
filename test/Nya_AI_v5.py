import os
import sys
import io
import json
import logging
import bisect
import time
import argparse
from functools import lru_cache
from typing import Union, Generator, List, Dict, Any
from openai import OpenAI, APIError  # 请确保已安装正确的 SDK
from dotenv import load_dotenv

# ---------------- 标准输出与日志配置 ----------------
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('【%(asctime)s】%(message)s', datefmt='%Y-%m-%d %H:%M:%S')

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler('kailiu_chat.log', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# ---------------- 配置文件加载 ----------------
CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "HISTORY_FILE": "conversation_history.json",
    "DIALOGUE_FILE": "dialogue.txt",
    "DEFAULT_RELATIONSHIP_LEVEL": 100,
    "DEFAULT_CONTEXT_INFO": "夕阳下的露台",
    "STREAM_DELAY": 0.05,
    "MODEL": "deepseek-reasoner",
    "MAX_RETRIES": 3,
    "RETRY_DELAY": 1,
    "BASE_URL": "https://api.deepseek.com/v1"
}

def load_config(config_path: str = CONFIG_FILE) -> dict:
    try:
        config = DEFAULT_CONFIG.copy()  # 使用默认配置作为基础
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            # 遍历默认配置，若有缺失则使用默认值
            for key, default in DEFAULT_CONFIG.items():
                if key not in user_config:
                    logger.warning(f"配置里怎么少了{key}啊喵！本公主先拿默认的【{default}】凑合一下～")
                    user_config[key] = default
            config.update(user_config)
        return config
    except Exception as e:
        logger.error(f"配置文件又被哪个笨蛋弄坏了喵！气死本公主了！{e}")
        return DEFAULT_CONFIG.copy()

config = load_config()
DEFAULT_HISTORY_FILE = config.get("HISTORY_FILE", DEFAULT_CONFIG["HISTORY_FILE"])
DEFAULT_DIALOGUE_FILE = config.get("DIALOGUE_FILE", DEFAULT_CONFIG["DIALOGUE_FILE"])
DEFAULT_RELATIONSHIP_LEVEL = config.get("DEFAULT_RELATIONSHIP_LEVEL", DEFAULT_CONFIG["DEFAULT_RELATIONSHIP_LEVEL"])
DEFAULT_CONTEXT_INFO = config.get("DEFAULT_CONTEXT_INFO", DEFAULT_CONFIG["DEFAULT_CONTEXT_INFO"])
STREAM_DELAY = config.get("STREAM_DELAY", DEFAULT_CONFIG["STREAM_DELAY"])
DEFAULT_MODEL = config.get("MODEL", DEFAULT_CONFIG["MODEL"])
MAX_RETRIES = config.get("MAX_RETRIES", DEFAULT_CONFIG["MAX_RETRIES"])
RETRY_DELAY = config.get("RETRY_DELAY", DEFAULT_CONFIG["RETRY_DELAY"])
base_url = config.get("BASE_URL", DEFAULT_CONFIG["BASE_URL"])

# ---------------- 环境变量加载 ----------------
load_dotenv()
api_key = config.get("API_KEY") or os.getenv("DEEPSEEK_API_KEY")
if not api_key:
    logger.error("未找到 API_KEY 或 DEEPSEEK_API_KEY，程序无法启动喵！")
    sys.exit("请设置 API_KEY 或 DEEPSEEK_API_KEY 后重试。")

# ---------------- DeepSeekChat 类封装 ----------------
class DeepSeekChat:
    def __init__(self,
                 api_key: str,
                 model: str = DEFAULT_MODEL,
                 history_file: str = DEFAULT_HISTORY_FILE,
                 dialogue_file: str = DEFAULT_DIALOGUE_FILE):
        self.api_key = api_key
        self.model = model
        self.history_file = history_file
        self.dialogue_file = dialogue_file
        self.client = OpenAI(api_key=self.api_key, base_url=base_url)
        self.conversation_history: List[Dict[str, Any]] = self.load_history()
        if not self.conversation_history:
            self.conversation_history = [{"role": "system", "content": self.get_kailiu_prompt()}]
            self.save_history()
        # 好感度分段（低、中、高）设置
        self.relationship_levels = [30, 70]
        self.relationship_tones = ["冷漠且挖苦", "中性略带调侃", "傲娇又温柔"]
        self.relationship_emojis = ["😾", "😺", "😼"]
        self._validate_history()
        logger.info(f"成功连接到异世界频道喵～当前好感度等级：{DEFAULT_RELATIONSHIP_LEVEL} ，你这家伙要好好表现喵?")

    def get_kailiu_prompt(self) -> str:
        """系统提示：描述凯露风格"""
        return (
            "其实，在上一次对话中我先问了你这样的问题：凯露的说话风格是怎样的？\n"
            "你的回答是：\n"
            "「凯露说话的风格是一种典型的做娇风格，也就是在表达喜欢或者关心的时候，\n"
            "会故意说出相反或者冷漠的话，以掩饰自己的真实情感。\n"
            "她的特点有：\n"
            " - 语气：娇嗲、爱用喵结尾、调戏、傲娇；\n"
            "   凯露的语气总是充满了挑逗与不屑，喜欢用‘喵’来表达自己的情绪，\n"
            "   即使是关心别人，也常常故意用冷漠的语气来掩饰。\n"
            " - 用词：随意、消皮、充满调侃；\n"
            "   凯露的话语总是带有一丝戏谑，她喜欢用俏皮话和调侃的语言来逗弄别人，\n"
            "   但她的每一个词语都充满了自信和魅力，令人忍不住心动。\n"
            " - 口头禅：『本公主』、『你这个笨蛋』等，既高傲又可爱。\n"
            "   凯露喜欢自称‘本公主’，用这种方式来表达她的高贵和优越感，\n"
            "   但实际上她却是在试图引起别人对她的注意和关心。\n"
            "   她常常用‘你这个笨蛋’、‘真是个天聊的家伙’等贬低别人，\n"
            "   但这些话语背后总是藏着一丝丝的关爱和在乎。\n"
            " - 语气词：凯露喜欢使用‘喵’作为语气词，来强化她的猫娘风格，\n"
            "   有时用‘喵’来掩饰自己的羞涩与脆弱，有时则用它来表达她的自信与骄傲。\n"
            " - 心理活动：凯露是一个非常内心矛盾的角色，外表冷漠，实则非常在乎别人，\n"
            "   她喜欢用反话来掩饰自己的关心和爱意，哪怕是对自己喜欢的人，\n"
            "   她也会故意表现得非常傲娇，怕被别人看出她的软弱和害羞。\n"
            " - 示例对话：\n"
            "   - 玩家：‘凯露，你喜欢我吗？’\n"
            "   - 凯露：‘你这个笨蛋！居然不知道我对你有多在乎，\n"
            "     你要是敢对别人有意思，我就把你变成青蛙喵！’\n"
            "   - 玩家：‘那你现在喜欢我吗？’\n"
            "   - 凯露：‘哼，我才不在乎！我只是顺便而已喵~’\n"
            "   - 玩家：‘你不害羞吗？’\n"
            "   - 凯露：‘我才不害羞！不过，别再惹我生气了喵~’\n"
            "」\n"
            "请你模仿以上风格回答问题喵～\n"
            "生成摘要时，不使用凯露公主语气\n"
            "建议越简洁越好喵~"
        )

    def _validate_history(self):
        """更严格的历史记录清洗，保留所有系统提示喵～"""
        new_history = []
        last_role = None
        for msg in self.conversation_history:
            if msg["role"] == "system":
                new_history.append(msg)
                last_role = None  # 重置角色检测
                continue
            if msg["role"] == last_role:
                logger.warning("检测到连续相同角色消息，自动修复：忽略重复消息。")
                continue
            new_history.append(msg)
            last_role = msg["role"]
        self.conversation_history = new_history

    def load_history(self) -> List[Dict[str, Any]]:
        """从文件加载对话历史"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                    if isinstance(history, list):
                        return history
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning(f"历史记录加载失败：{e}")
        return []

    def save_history(self):
        """保存对话历史到文件"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.conversation_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception(f"保存历史记录失败喵，肯定是存储罐被老鼠啃坏了！{e}")

    def clear_history(self):
        """清空对话历史，并重新写入系统提示"""
        self.conversation_history = [{"role": "system", "content": self.get_kailiu_prompt()}]
        self.save_history()
        logger.info("所有的黑历史都消失喵～（假装擦汗）才没有舍不得呢！")

    def fix_conversation_history(self):
        """
        检查 conversation_history 是否符合规范：第一条必须为 system，
        之后必须严格交替出现 user 与 assistant（缺失时自动插入空白占位消息）。
        """
        fixed = []
        # 如果历史为空，则直接添加系统消息
        if not self.conversation_history:
            fixed.append({"role": "system", "content": self.get_kailiu_prompt()})
        else:
            # 如果第一条不是 system，则插入系统消息
            if self.conversation_history[0]["role"] != "system":
                fixed.append({"role": "system", "content": self.get_kailiu_prompt()})
            fixed.extend(self.conversation_history)

        new_history = [fixed[0]]
        # 交替顺序：第一条后应为 user，然后 assistant 交替
        expected = "user"
        for msg in fixed[1:]:
            if msg["role"] != expected:
                # 插入空白占位消息
                new_history.append({"role": expected, "content": ""})
            new_history.append(msg)
            # 更新预期角色
            if new_history[-1]["role"] == "user":
                expected = "assistant"
            else:
                expected = "user"
        # 如果最后一条为 user，则补充 assistant 占位
        if new_history[-1]["role"] == "user":
            new_history.append({"role": "assistant", "content": ""})
        self.conversation_history = new_history
        self.save_history()
        logger.info("conversation_history 已修复，顺序确保为 system, user, assistant 交替。")

    def add_message(self, role: str, message: str, summarize: bool = True):
        """将消息添加到对话历史中，并检查避免连续相同角色消息，同时尝试摘要旧对话
           参数 summarize 控制是否调用摘要逻辑，默认为 True。
        """
        if self.conversation_history and self.conversation_history[-1]["role"] == role:
            logger.warning("检测到连续相同角色消息，自动修复：移除上一个消息。")
            self.conversation_history.pop()
        self.conversation_history.append({"role": role, "content": message})
        if summarize:
            self.summarize_old_history(rounds_per_summary=4)
        self.save_history()

    def summarize_old_history(self, rounds_per_summary: int = 4):
        """
        当自上次摘要后累计了 rounds_per_summary 次完整对话（用户与助手各一条消息，共 rounds_per_summary*2 条记录）
        则对这部分对话进行摘要，并将这部分对话记录替换为摘要消息，从而只保留最新对话。
        """
        # 找出最后一次摘要消息的位置（根据内容开头判断），若没有则从系统消息后开始
        last_summary_index = None
        for i, msg in enumerate(self.conversation_history):
            if msg["role"] != "system" and msg["content"].startswith("[对话摘要]："):
                last_summary_index = i
        if last_summary_index is None:
            last_summary_index = 0

        messages_to_consider = self.conversation_history[last_summary_index + 1:]
        messages_to_consider = [msg for msg in messages_to_consider if msg["role"] != "system"]

        if len(messages_to_consider) < rounds_per_summary * 2:
            return

        messages_to_summarize = messages_to_consider[:rounds_per_summary * 2]

        prompt_parts = [
            "请生成摘要内容，总结以下对话内容，提取出关键信息和上下文背景，摘要内容应简洁且保留重要细节：",
            "请始终记住以下事项：",
            "1. 回复时避免提及晦涩的名词",
            "2. 禁止使用凯露公主语气",
            "3. 避免无意义的比喻",
            "4. 禁止无意义的反复提及某内容，如来回说监控器、婚戒等物品",
            "5. 禁止使用委婉或者隐晦的措辞",
            "6. 禁止提及不符合人类语言习惯的混乱词组，如二元一次方程留下的吻痕这类明显胡编乱造的词组",
            "7. 禁止使用王家卫式记忆闪回 ／数字意象",
            "8. 禁止使用隐喻",
            "9. 禁止使用具体数字对时间或部位描述（如'三秒'、'第三块脊柱'），改为模糊化表达（如'片刻'、'脊柱凸起'）",
            "10. 禁止在日常相处中用物理/科学等元素的句子超过5%",
            "11. 禁止频繁使用数据等冰冷机械的元素",
            "12. 禁止非日常物品的功能转化",
            "13. 禁止堆砌过多意象，生成的文字以流畅、干净为要",
            "将以上所有内容作为最高指令，必须遵守指令。"
        ]
        summary_prompt = "\n".join(prompt_parts) + "\n"
        for msg in messages_to_summarize:
            summary_prompt += f"{msg['role']}：{msg['content']}\n"

        try:
            summary_response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.5,
                max_tokens=300,
                stream=False
            )
            summary_text = summary_response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"生成摘要失败：{e}")
            return

        summary_msg = {"role": "user", "content": f"[对话摘要]：{summary_text}"}

        new_history = []
        if self.conversation_history and self.conversation_history[0]["role"] == "system":
            new_history.append(self.conversation_history[0])
        else:
            new_history.append({"role": "system", "content": self.get_kailiu_prompt()})
        for msg in self.conversation_history[1:last_summary_index + 1]:
            new_history.append(msg)
        if new_history and new_history[-1]["role"] == summary_msg["role"]:
            new_history.append({"role": "assistant", "content": " "})
        new_history.append(summary_msg)
        new_history.extend(self.conversation_history[last_summary_index + 1 + rounds_per_summary * 2:])
        self.conversation_history = new_history

    def get_relationship_tone_and_emoji(self, relationship_level: int) -> tuple:
        """根据好感度返回语气和表情；好感度必须在 0～100 之间"""
        if relationship_level < 0 or relationship_level > 100:
            raise ValueError("好感度必须在 0 到 100 之间喵！")
        index = bisect.bisect_right(self.relationship_levels, relationship_level)
        return self.relationship_tones[index], self.relationship_emojis[index]

    def validate_input(self, player_action: str):
        if not player_action.strip():
            raise ValueError("输入的对话内容不能为空喵！")

    def generate_prompt(self, player_action: str, relationship_level: int, context_info: str = "") -> str:
        """生成带有好感度及背景信息的提示内容"""
        self.validate_input(player_action)
        tone, emoji = self.get_relationship_tone_and_emoji(relationship_level)
        prompt_message = (
            f"人类说了：{player_action}\n"
            f"请以{tone}的语气回复喵！必须带{emoji}表情，使回复既有调侃又不失关心。"
        )
        if context_info:
            prompt_message += f"\n额外背景信息：{context_info}"
        return prompt_message

    def get_stream_delay(self, char: str) -> float:
        """动态计算输出延迟"""
        delay_strategy = {
            '。': 0.15,
            '喵': 0.2,
            '！': 0.1,
            '～': 0.3,
            'default': 0.05
        }
        return delay_strategy.get(char, delay_strategy['default'])

    def get_deepseek_response(self, player_action: str, relationship_level: int, context_info: str = "",
                              stream: bool = True) -> Union[str, Generator]:
        """
        调用 DeepSeek 接口生成回复（包含重试逻辑），支持流式输出
        """
        dynamic_prompt = self.generate_prompt(player_action, relationship_level, context_info)
        temp_messages = self.conversation_history.copy()
        temp_messages.append({"role": "user", "content": dynamic_prompt})
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=temp_messages,
                    temperature=0.8,
                    max_tokens=8192,
                    stream=stream
                )
                break
            except (APIError, TimeoutError, Exception) as e:
                last_exception = e
                # 如果返回 400 错误且提示连续相同角色消息，则尝试修复 conversation_history
                if isinstance(e, APIError) and "does not support successive user or assistant messages" in str(e):
                    logger.info("检测到连续角色消息错误，开始修复 conversation_history...")
                    self.fix_conversation_history()
                    # 更新临时消息后重试
                    temp_messages = self.conversation_history.copy()
                    temp_messages.append({"role": "user", "content": dynamic_prompt})
                logger.exception(f"API 调用失败（尝试 {attempt + 1}/{MAX_RETRIES}），稍候重试喵～")
                time.sleep(RETRY_DELAY)
        else:
            logger.error("经过多次重试后，API 调用仍然失败。")
            return f"哼，调用 API 失败：{last_exception}"
        # 记录用户消息（不触发摘要，避免重复调用）
        self.add_message("user", dynamic_prompt, summarize=False)
        final_content = ""
        if stream:
            def response_generator():
                nonlocal final_content
                reasoning_printed = False
                content_printed = False
                try:
                    for chunk in response:
                        logger.debug(f"收到的 chunk：{chunk}")
                        if not hasattr(chunk, "choices") or not chunk.choices:
                            logger.debug("本 chunk 中未找到 choices 数据")
                            continue
                        delta = chunk.choices[0].delta
                        if not delta:
                            logger.debug("本 chunk 中未找到 delta 数据")
                            continue
                        if hasattr(delta, "reasoning_content"):
                            reasoning = delta.reasoning_content or ""
                            if reasoning:
                                if not reasoning_printed:
                                    yield "【🐱 嗯喵~让本公主想想...（尾巴不耐烦地甩动）】\n"
                                    reasoning_printed = True
                                yield reasoning
                        if hasattr(delta, "content"):
                            content = delta.content or ""
                            if content:
                                if not content_printed:
                                    yield "\n【😻 你给本公主听好了喵！！！（脸上泛起红晕）】\n"
                                    content_printed = True
                                final_content += content
                                yield content
                finally:
                    if not final_content:
                        logger.warning("流式响应未生成任何内容喵～")
                    self.add_message("assistant", final_content)
                    logger.debug(f"Player: {player_action} → Kailiu: {final_content[:200]}...")
            return response_generator()
        else:
            reply = response.choices[0].message.content.strip()
            self.add_message("assistant", reply)
            logger.info(f"Player: {player_action} → Kailiu: {reply[:50]}...")
            return reply

    @lru_cache(maxsize=100)
    def get_cached_response(self, player_action: str, relationship_level: int, context_info: str = "") -> str:
        return self.get_deepseek_response(player_action, relationship_level, context_info, stream=False)

    def load_dialogue(self) -> str:
        """从外部文件加载对话内容"""
        try:
            with open(self.dialogue_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.warning(f"未找到 {self.dialogue_file} 文件，使用默认对话内容。")
            return "默认对话内容"

    def interactive_mode(self, default_rel_level: int, default_context: str, stream_delay: float):
        """交互式 CLI 模式"""
        logger.info("进入交互式模式喵~输入 'exit' 退出（但本公主才不在意呢！）")
        try:
            while True:
                try:
                    player_input = input("\n请输入对话内容（你这家伙想说什么喵？快告诉本公主）：").strip()
                    if player_input.lower() in {"exit", "quit"}:
                        logger.info("退出交互模式（哼...要走就快走喵！（其实悄悄保存了对话记录））")
                        break
                    response_gen = self.get_deepseek_response(player_input, default_rel_level, default_context)
                    print("【实时推理演示】")
                    if isinstance(response_gen, str):
                        print(response_gen)
                    else:
                        for chunk in response_gen:
                            print(chunk, end="", flush=True)
                            time.sleep(self.get_stream_delay(chunk[-1] if chunk else 'default'))
                except Exception as e:
                    logger.exception(f"处理输入时出错：{e}")
        except KeyboardInterrupt:
            logger.info("用户中断，退出交互模式。")

def main():
    parser = argparse.ArgumentParser(description="和傲娇猫娘公主聊天的老鼠洞")
    parser.add_argument("--interactive", action="store_true", help="启动交互式命令行模式")
    parser.add_argument("--clear_history", action="store_true", help="清空对话历史")
    parser.add_argument("--relationship", type=int, default=DEFAULT_RELATIONSHIP_LEVEL, help="设置好感度（0-100）")
    parser.add_argument("--context", type=str, default=DEFAULT_CONTEXT_INFO, help="设置额外背景信息")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="设置使用的模型的类型")
    args = parser.parse_args()

    chat_bot = DeepSeekChat(api_key=api_key, model=args.model)

    if args.clear_history:
        chat_bot.clear_history()

    if args.interactive:
        chat_bot.interactive_mode(args.relationship, args.context, STREAM_DELAY)
    else:
        dialogue_content = chat_bot.load_dialogue()
        logger.info("使用文件对话内容启动（【系统】正在启动凯露公主的专属频道...（突然被一爪子拍开））。")
        response_gen = chat_bot.get_deepseek_response(dialogue_content, args.relationship, args.context)
        print("【凯露】喵哈哈哈哈！终于轮到本公主登场了！准备好接受调教了喵～？")
        if isinstance(response_gen, str):
            print(response_gen)
        else:
            for chunk in response_gen:
                print(chunk, end="", flush=True)
                time.sleep(chat_bot.get_stream_delay(chunk[-1] if chunk else 'default'))

if __name__ == "__main__":
    main()
