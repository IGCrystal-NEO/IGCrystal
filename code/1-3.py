@tim.command("编辑信息", alias={'编辑', 'edit'})
async def edit_info(self, event: AstrMessageEvent, task_id: int, new_content: str):
    """
    编辑指定任务的发送内容
    示例: tim 编辑信息 1 '新的发送信息'
    注意：请用单引号或三引号包裹发送内容，确保空格、换行及双引号能原样保留。
    """
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
