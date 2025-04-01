import os
import re
import json
import asyncio
import logging
import sys
from datetime import datetime, timedelta
from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp  # 包含 Plain、Image 等组件

# 日志文件路径
log_file = "./data/plugins/astrbot_plugin_timtip/bot.log"

# 配置日志：同时写入文件和输出到控制台
logging.basicConfig(
    level=logging.DEBUG,  # 记录 DEBUG 及以上级别的日志
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),  # 写入日志文件
        logging.StreamHandler(sys.stdout)  # 输出到控制台，方便调试
    ]
)

logging.info("日志系统初始化完成，日志文件路径: %s", log_file)


@register("astrbot_plugin_timtip", "IGCrystal", "定时发送消息的插件喵~", "1.1.1",
          "https://github.com/IGCrystal/astrbot_plugin_timtip")
class TimPlugin(Star):
    # 使用 __file__ 的目录作为基准路径，并转换为绝对路径
    TIM_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "tim.json"))

    def __init__(self, context: Context):
        super().__init__(context)
        # 按会话存储任务：{umo: {task_id(str): task_data(dict), ...}, ...}
        self.tasks = self.__class__.load_tasks()
        # 全局任务编号从 1 开始
        self.next_id = 1
        for task_dict in self.tasks.values():
            for tid in task_dict.keys():
                try:
                    tid_int = int(tid)
                    if tid_int >= self.next_id:
                        self.next_id = tid_int + 1
                except Exception:
                    continue
        # 记录已执行 fixed 任务标识，格式: "{umo}_{task_id}_{day}_{hour}_{minute}"
        self.executed_tasks = set()
        self.last_day = (datetime.utcnow() + timedelta(hours=8)).day
        # 启动后台调度器
        self.scheduler_task = asyncio.create_task(self.scheduler_loop())
        logging.debug("TimPlugin 初始化完成，定时任务调度器已启动")

    async def terminate(self):
        """
        插件卸载时调用，取消后台调度器任务，防止重载后产生多个调度器。
        """
        if hasattr(self, "scheduler_task"):
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                logging.debug("调度器任务已成功取消")

    @staticmethod
    def load_tasks() -> dict:
        if not os.path.exists(TimPlugin.TIM_FILE):
            try:
                os.makedirs(os.path.dirname(TimPlugin.TIM_FILE), exist_ok=True)
                with open(TimPlugin.TIM_FILE, "w", encoding="utf-8") as f:
                    # 按会话存储任务：{umo: {task_id: task_data, ...}, ...}
                    json.dump({}, f, ensure_ascii=False, indent=4)
                logging.debug("tim.json 文件不存在，已创建空任务文件。")
            except Exception as e:
                logging.error("创建 tim.json 文件失败：%s", e)
            return {}
        try:
            with open(TimPlugin.TIM_FILE, "r", encoding="utf-8") as f:
                tasks = json.load(f)
                logging.debug("加载任务成功，任务数：%d", sum(len(v) for v in tasks.values()))
                return tasks
        except Exception as e:
            logging.error("读取 tim.json 文件失败：%s", e)
            return {}

    @staticmethod
    def save_tasks(tasks: dict):
        try:
            with open(TimPlugin.TIM_FILE, "w", encoding="utf-8") as f:
                json.dump(tasks, f, ensure_ascii=False, indent=4)
            logging.debug("任务保存成功。")
        except Exception as e:
            logging.error("保存 tim.json 失败：%s", e)

@staticmethod
def parse_time(time_str: str) -> tuple:
    """
    解析固定时间格式，支持以下格式：
      1. "HH时MM分"（例如 20时30分）
      2. "HHMM"（例如 2030）
      3. "HH:MM"（例如 20:30）
    返回 (hour, minute)
    """
    patterns = [
        r'^(\d{1,2})时(\d{1,2})分$',
        r'^(\d{2})(\d{2})$',
        r'^(\d{1,2}):(\d{1,2})$'
    ]
    
    for pattern in patterns:
        match = re.match(pattern, time_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            if 0 <= hour < 24 and 0 <= minute < 60:
                return hour, minute
            else:
                raise ValueError("时间范围错误，小时应在 0-23 之间，分钟应在 0-59 之间。")
    raise ValueError("时间格式错误，请使用 'HH时MM分'、'HHMM' 或 'HH:MM' 格式，例如 20时30分, 2030, 或 20:30。")

    @staticmethod
    def parse_message(content: str):
        """
        将用户输入内容解析为消息链，只发送纯文本消息，不处理 [img] 标签。
        """
        # 直接将整个内容作为 Plain 消息段发送
        return [Comp.Plain(content)]

    async def scheduler_loop(self):
        """后台调度器，每 1 秒检查一次所有会话中的任务条件"""
        while True:
            now = datetime.utcnow() + timedelta(hours=8)
            current_day = now.day
            logging.debug("调度器循环运行中，当前时间: %s", now.isoformat())
            if current_day != self.last_day:
                self.executed_tasks.clear()
                self.last_day = current_day
                logging.debug("新的一天，清空固定任务执行记录。")

            # 遍历每个会话的任务
            for umo, task_dict in self.tasks.items():
                logging.debug("检查会话 %s 下的任务: %s", umo, task_dict)
                for tid, task in list(task_dict.items()):
                    # 仅处理状态为 active 且内容非空的任务
                    if task.get("status", "active") != "active" or not task.get("content", "").strip():
                        continue

                    task_type = task.get("type")
                    last_run = task.get("last_run")
                    last_run_dt = datetime.fromisoformat(last_run) if last_run else None

                    if task_type == "interval":
                        try:
                            interval = float(task.get("time"))
                        except ValueError:
                            logging.error("任务 %s 时间参数解析失败。", tid)
                            continue
                        diff = (now - last_run_dt).total_seconds() if last_run_dt else None
                        logging.debug("检查任务 %s: 当前时间差 = %s秒, 要求 %s秒", tid, diff, interval * 60)
                        if last_run_dt is None or (now - last_run_dt).total_seconds() >= interval * 60:
                            logging.debug("任务 %s 满足条件，准备发送消息。", tid)
                            await self.send_task_message(task)
                            task["last_run"] = now.isoformat()
                    elif task_type == "once":
                        try:
                            delay = float(task.get("time"))
                        except ValueError:
                            logging.error("任务 %s 时间参数解析失败。", tid)
                            continue
                        create_time = datetime.fromisoformat(task.get("create_time"))
                        if now >= create_time + timedelta(minutes=delay):
                            logging.debug("一次性任务 %s 到达发送时间，准备发送消息。", tid)
                            await self.send_task_message(task)
                            logging.debug("一次性任务 %s 执行后将被删除。", tid)
                            del task_dict[tid]
                    elif task_type == "fixed":
                        try:
                            hour, minute = self.__class__.parse_time(task.get("time"))
                        except ValueError as e:
                            logging.error("任务 %s 时间格式错误: %s", tid, e)
                            continue
                        exec_id = f"{umo}_{tid}_{current_day}_{hour}_{minute}"
                        if now.hour == hour and now.minute == minute and exec_id not in self.executed_tasks:
                            logging.debug("固定任务 %s 满足条件，准备发送消息。", tid)
                            await self.send_task_message(task)
                            task["last_run"] = now.isoformat()
                            self.executed_tasks.add(exec_id)
            self.__class__.save_tasks(self.tasks)
            await asyncio.sleep(1)

    async def send_task_message(self, task: dict):
        """构造消息链并发送任务消息"""
        target = task.get("target")
        content = task.get("content")
        if target and content:
            # 使用 MessageChain 的 message() 方法构造消息链
            chain = MessageChain().message(content)
            logging.debug("准备发送任务消息到目标 %s，内容: %s", target, content)
            try:
                await self.context.send_message(target, chain)
                logging.debug("消息发送成功")
            except Exception as e:
                logging.error("发送消息时出错: %s", e)
        else:
            logging.error("任务内容或目标为空，无法发送消息。")

    # 指令组 "tim"
    @filter.command_group("tim")
    def tim(self):
        pass
        
@tim.command("设置定时", alias={'定时', '设置'})
async def set_timing(self, event: AstrMessageEvent, task_type: str, time_value: str, *content: str):
    """
    添加定时任务并设置发送内容（一步到位）
    示例:
      tim 设置定时 interval 5 二二 儿童节快乐
      tim 设置定时 fixed 20时30分 快到点了，该发送啦！
      tim 设置定时 once 10 临时提醒：快吃饭喵~
    任务类型：
      interval: 每隔指定分钟发送
      fixed: 每天在指定时间发送 (支持格式：HH时MM分、HHMM、HH:MM，UTC+8)
      once: 延迟指定分钟后发送一次

    注意：发送内容中的空格、换行及双引号会原样保留。用户在输入内容时，
    如果内部需要出现双引号，则可以用转义字符 \" 来输入。
    """
    # 将捕获到的所有内容参数合并成一个字符串，并处理转义的双引号
    content_str = " ".join(content).replace('\\"', '"')
    
    # 参数验证
    if not task_type.strip():
        yield event.plain_result("任务类型不能为空，请输入任务类型。")
        return
    if not time_value.strip():
        yield event.plain_result("时间参数不能为空，请输入时间参数。")
        return
    if task_type == "fixed":
        try:
            self.__class__.parse_time(time_value)
        except ValueError as e:
            yield event.plain_result(str(e))
            return
    elif task_type in ("interval", "once"):
        try:
            float(time_value)
        except ValueError:
            yield event.plain_result(f"{task_type} 类型任务的时间参数应为数字（单位：分钟）。")
            return
    else:
        yield event.plain_result("未知的任务类型，请使用 interval, fixed 或 once。")
        return

    if not content_str.strip():
        yield event.plain_result("发送内容不能为空，请输入发送内容。")
        return

    now = datetime.utcnow() + timedelta(hours=8)
    umo = event.unified_msg_origin
    if umo not in self.tasks:
        self.tasks[umo] = {}

    task_data = {
        "type": task_type,
        "time": time_value,
        "content": content_str,  # 保存用户原始输入的发送内容
        "status": "active",
        "create_time": now.isoformat(),
        "last_run": None,
        "target": umo
    }
    task_id = str(self.next_id)
    self.next_id += 1
    self.tasks[umo][task_id] = task_data
    self.__class__.save_tasks(self.tasks)
    logging.debug("添加任务 %s: %s", task_id, task_data)
    msg = (f"任务 {task_id} 已添加（会话: {umo}），类型: {task_type}，时间参数: {time_value}。\n"
           "发送内容已设定，无需再单独设置。")
    yield event.plain_result(msg)


@tim.command("编辑信息", alias={'编辑', 'edit'})
async def edit_info(self, event: AstrMessageEvent, task_id: int, *new_content: str):
    """
    编辑指定任务的发送内容
    示例: tim 编辑信息 1 新的发送信息
    注意：编辑时，请将任务编号后面的所有内容作为新的发送内容，支持空格、换行和双引号。
    """
    new_content_str = " ".join(new_content).replace('\\"', '"')
    if not str(task_id).strip():
        yield event.plain_result("任务编号不能为空，请输入任务编号。")
        return
    if not new_content_str.strip():
        yield event.plain_result("发送信息不能为空，请输入新的发送信息。")
        return

    umo = event.unified_msg_origin
    tid = str(task_id)
    if umo in self.tasks and tid in self.tasks[umo]:
        self.tasks[umo][tid]["content"] = new_content_str
        self.__class__.save_tasks(self.tasks)
        logging.debug("编辑任务 %s 的内容为: %s", tid, new_content_str)
        yield event.plain_result(f"任务 {tid} 的发送内容已更新为:\n{new_content_str}")
    else:
        yield event.plain_result(f"任务 {tid} 在当前会话中不存在。")

    @tim.command("取消", alias={'取消任务'})
    async def cancel_task(self, event: AstrMessageEvent, task_id: int):
        """
        取消指定任务
        示例: tim 取消 1
        """
        umo = event.unified_msg_origin
        tid = str(task_id)
        if umo in self.tasks and tid in self.tasks[umo]:
            del self.tasks[umo][tid]
            self.__class__.save_tasks(self.tasks)
            logging.debug("取消任务 %s", tid)
            yield event.plain_result(f"任务 {tid} 已取消。")
        else:
            yield event.plain_result(f"任务 {tid} 在当前会话中不存在。")

    @tim.command("暂停", alias={'暂停任务'})
    async def pause_task(self, event: AstrMessageEvent, task_id: int):
        """
        暂停指定任务
        示例: tim 暂停 1
        """
        umo = event.unified_msg_origin
        tid = str(task_id)
        if umo in self.tasks and tid in self.tasks[umo]:
            self.tasks[umo][tid]["status"] = "paused"
            self.__class__.save_tasks(self.tasks)
            logging.debug("暂停任务 %s", tid)
            yield event.plain_result(f"任务 {tid} 已暂停。")
        else:
            yield event.plain_result(f"任务 {tid} 在当前会话中不存在。")

    @tim.command("启用", alias={'启用任务'})
    async def enable_task(self, event: AstrMessageEvent, task_id: int):
        """
        启用被暂停的任务
        示例: tim 启用 1
        """
        umo = event.unified_msg_origin
        tid = str(task_id)
        if umo in self.tasks and tid in self.tasks[umo]:
            self.tasks[umo][tid]["status"] = "active"
            self.__class__.save_tasks(self.tasks)
            logging.debug("启用任务 %s", tid)
            yield event.plain_result(f"任务 {tid} 已启用。")
        else:
            yield event.plain_result(f"任务 {tid} 在当前会话中不存在。")

    @tim.command("清空", alias={'清空信息'})
    async def clear_content(self, event: AstrMessageEvent, task_id: int):
        """
        清空指定任务的发送内容
        示例: tim 清空 1
        """
        umo = event.unified_msg_origin
        tid = str(task_id)
        if umo in self.tasks and tid in self.tasks[umo]:
            self.tasks[umo][tid]["content"] = ""
            self.__class__.save_tasks(self.tasks)
            logging.debug("清空任务 %s 的内容", tid)
            yield event.plain_result(f"任务 {tid} 的发送内容已清空。")
        else:
            yield event.plain_result(f"任务 {tid} 在当前会话中不存在。")

    @tim.command("列出任务", alias={'列表', 'list', '队列', '当前任务', '任务', '任务列表'})
    async def list_tasks(self, event: AstrMessageEvent):
        """
        列出当前会话中所有已创建的任务
        示例: tim 列出任务
        """
        umo = event.unified_msg_origin
        if umo not in self.tasks or not self.tasks[umo]:
            yield event.plain_result("当前会话中没有设置任何任务。")
            return
        msg = "当前会话任务列表：\n"
        for tid, task in self.tasks[umo].items():
            msg += f"任务 {tid} - 类型: {task['type']}, 时间参数: {task['time']}, 状态: {task['status']}\n"
            if task["content"]:
                msg += f"    内容: {task['content']}\n"
        logging.debug("列出任务：\n%s", msg)
        yield event.plain_result(msg)

    @tim.command("help", alias={'帮助', '帮助信息'})
    async def show_help(self, event: AstrMessageEvent):
        """
        显示定时任务插件的帮助信息
        示例: tim help
        """
        help_msg = (
            "定时任务插件帮助信息：\n"
            "1. tim 设置定时 <任务种类> <时间> <发送内容>\n"
            "   - interval: 每隔指定分钟发送 (示例: tim 设置定时 interval 5 第一行\\n第二行)\n"
            "   - fixed: 每天在指定时间发送，格式 HH时MM分 (示例: tim 设置定时 fixed 20时30分 快到点了，该发送啦！)\n"
            "   - once: 延迟指定分钟后发送一次 (示例: tim 设置定时 once 10 临时提醒：快吃饭喵~)\n"
            "2. tim 取消 <任务编号>              -- 取消任务\n"
            "3. tim 暂停 <任务编号>              -- 暂停任务\n"
            "4. tim 启用 <任务编号>              -- 启用被暂停的任务\n"
            "5. tim 清空 <任务编号>              -- 清空任务发送内容\n"
            "6. tim 列出任务                   -- 列出当前会话中所有任务\n"
            "7. tim 编辑信息 <任务编号> <发送信息>  -- 编辑指定任务的发送内容\n"
            "8. tim help                       -- 显示此帮助信息\n"
            "更多用法请访问 https://github.com/IGCrystal/astrbot_plugin_timtip \n"
        )
        yield event.plain_result(help_msg)
