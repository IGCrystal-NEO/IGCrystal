@tim.command("设置定时", alias={'定时', '设置'})
async def set_timing(self, event: AstrMessageEvent, task_type: str, time_value: str, content: str):
    """
    添加定时任务并设置发送内容（一步到位）
    示例:
      tim 设置定时 interval 5 儿童节快乐
      tim 设置定时 fixed 20时30分 快到点了，该发送啦！
      tim 设置定时 once 10 临时提醒：快吃饭喵~
    任务类型：
      interval: 每隔指定分钟发送
      fixed: 每天在指定时间发送 (支持格式：HH时MM分、HHMM、HH:MM，UTC+8)
      once: 延迟指定分钟后发送一次

    注意：发送内容中的空格、换行及双引号会原样保留。如果内容中有空格，请确保整体作为一个参数传递。
    """
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
        "content": content,  # 保存发送内容
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
