@tim.command("设置定时", alias={'定时', '设置'})
async def set_timing(self, event: AstrMessageEvent, task_type: str, time_value: str, *content_parts: str):
    """
    添加定时任务并设置发送内容（一步到位）
    示例:
      tim 设置定时 interval 0.5 """Ciallo～(∠・ω< )⌒☆
      我是男的还是女的?"""
      
    任务类型：
      interval: 每隔指定分钟发送
      fixed: 每天在指定时间发送 (支持格式：HH时MM分、HHMM、HH:MM，UTC+8)
      once: 延迟指定分钟后发送一次

    注意：如果内容中包含空格、换行或双引号，
           请用三引号或单引号包裹整个发送内容，
           插件会自动去除包裹的引号，保留中间的原始格式。
    """
    # 将捕获到的所有部分拼接成一个字符串，保留中间空格
    content = " ".join(content_parts)
    # 自动去除包裹的三引号或单引号（如果存在）
    if (content.startswith('"""') and content.endswith('"""')) or \
       (content.startswith("'''") and content.endswith("'''")):
        content = content[3:-3]
    elif (content.startswith('"') and content.endswith('"')) or \
         (content.startswith("'") and content.endswith("'")):
        content = content[1:-1]

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

    if not content.strip():
        yield event.plain_result("发送内容不能为空，请输入发送内容。")
        return

    now = datetime.utcnow() + timedelta(hours=8)
    umo = event.unified_msg_origin
    if umo not in self.tasks:
        self.tasks[umo] = {}

    task_data = {
        "type": task_type,
        "time": time_value,
        "content": content,  # 保存处理后的发送内容
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
