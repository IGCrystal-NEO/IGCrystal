@tim.command("编辑信息", alias={'编辑', 'edit'})
async def edit_info(self, event: AstrMessageEvent, task_id: int, *new_content_parts: str):
    """
    编辑指定任务的发送内容
    示例:
      tim 编辑信息 1 """新的发送信息
      多行内容也可以这样写"""
    注意：如果发送内容用引号（单引号、双引号或三引号）包裹，
           插件会自动去除包裹的引号，保留中间的原始格式。
    """
    # 将捕获到的所有部分拼接成一个字符串
    new_content = " ".join(new_content_parts)
    # 自动去除包裹的引号（支持三引号或单/双引号）
    if (new_content.startswith('"""') and new_content.endswith('"""')) or \
       (new_content.startswith("'''") and new_content.endswith("'''")):
        new_content = new_content[3:-3]
    elif (new_content.startswith('"') and new_content.endswith('"')) or \
         (new_content.startswith("'") and new_content.endswith("'")):
        new_content = new_content[1:-1]

    if not str(task_id).strip():
        yield event.plain_result("任务编号不能为空，请输入任务编号。")
        return
    if not new_content.strip():
        yield event.plain_result("发送信息不能为空，请输入新的发送信息。")
        return

    umo = event.unified_msg_origin
    tid = str(task_id)
    if umo in self.tasks and tid in self.tasks[umo]:
        self.tasks[umo][tid]["content"] = new_content
        self.__class__.save_tasks(self.tasks)
        logging.debug("编辑任务 %s 的内容为: %s", tid, new_content)
        yield event.plain_result(f"任务 {tid} 的发送内容已更新为:\n{new_content}")
    else:
        yield event.plain_result(f"任务 {tid} 在当前会话中不存在。")
