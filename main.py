import os
import json
from datetime import datetime
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig, logger
from astrbot.api.message_components import Plain
from astrbot.api.event import MessageChain

# ===================== 存储位置：当前插件目录 =====================
DATA_PATH = os.path.join(os.path.dirname(__file__), "update_log.json")

def init_data():
    if not os.path.exists(DATA_PATH):
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "global": [],
                "group": {}
            }, f, ensure_ascii=False, indent=2)

def load_data():
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"global": [], "group": {}}

def save_data(data):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

init_data()

# -----------------------------------------------------------------------------
@register(
    "update_log",
    "Noeight",
    "更新日志插件（指令组+独立ID+自动群发）",
    "1.0.0"
)
class UpdateLog(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.data = load_data()
        logger.info("[更新日志插件] 初始化完成 | 存储路径：" + DATA_PATH)

    def is_admin(self, event: AstrMessageEvent):
        try:
            uid = str(event.message_obj.sender.user_id)
            admins = [str(x) for x in self.config.get("admin_ids", [])]
            return uid in admins
        except:
            return False

    # ===================== 指令组：log =====================
    @filter.command_group("log")
    def log_group(self):
        pass

    # -------------------- 帮助：分权限显示 --------------------
    @log_group.command("help")
    async def help(self, event: AstrMessageEvent):
        """
        显示更新日志插件帮助菜单
        管理员显示全部指令，普通用户仅显示基础功能
        """
        if self.is_admin(event):
            txt = """📜 更新日志插件指令（管理员）
/log help                查看帮助
/log global 内容         发布全局更新
/log group GID 内容      发布群专属更新
/log id global 1         查询全局ID=1
/log id group 1          查询本群专属ID=1
/log search 关键词       搜索公告
/log del global ID      删除全局公告
/log del group GID ID   删除群专属公告
/log list               查看所有记录"""
        else:
            txt = """📜 更新日志插件指令
/log help             查看帮助
/log id global 1      查询全局ID=1
/log id group 1       查询本群专属ID=1
/log search 关键词    搜索公告"""
        yield event.plain_result(txt)

    # -------------------- 发布全局更新 --------------------
    @log_group.command("global")
    async def add_global(self, event: AstrMessageEvent):
        """
        管理员发布全局更新，自动发送到白名单群
        """
        if not self.is_admin(event):
            yield event.plain_result("❌ 无权限")
            return
        
        parts = event.message_str.split(" ", 2)
        if len(parts) < 3:
            yield event.plain_result("格式：/log global 内容")
            return
        
        content = parts[2]
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        logs = self.data["global"]
        new_id = len(logs) + 1

        logs.append({
            "id": new_id,
            "content": content,
            "time": now
        })
        self.data["global"] = logs
        save_data(self.data)

        # 自动群发
        if self.config.get("auto_push", True):
            groups = self.config.get("global_whitelist", [])
            msg = f"📢 全局更新【ID:{new_id}】{now}\n{content}"
            chain = MessageChain([Plain(msg)])
            platform = event.unified_msg_origin.split(':')[0]
            for g in groups:
                try:
                    target = f"{platform}:GroupMessage:{g}"
                    await self.context.send_message(target, chain)
                except Exception as e:
                    logger.error(f"群发失败 {g}: {e}")

        yield event.plain_result(f"✅ 全局更新发布成功\nID：{new_id}")

    # -------------------- 发布群专属更新 --------------------
    @log_group.command("group")
    async def add_group(self, event: AstrMessageEvent):
        """
        管理员发布指定群的专属更新，自动发送到对应群
        """
        if not self.is_admin(event):
            yield event.plain_result("❌ 无权限")
            return
        
        parts = event.message_str.split(" ", 3)
        if len(parts) < 4:
            yield event.plain_result("格式：/log group 群号 内容")
            return
        
        gid = parts[2]
        content = parts[3]
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        if gid not in self.data["group"]:
            self.data["group"][gid] = []
        glog = self.data["group"][gid]
        new_id = len(glog) + 1

        glog.append({
            "id": new_id,
            "content": content,
            "time": now
        })
        self.data["group"][gid] = glog
        save_data(self.data)

        # 发送到对应群
        if self.config.get("auto_push", True):
            try:
                platform = event.unified_msg_origin.split(':')[0]
                target = f"{platform}:GroupMessage:{gid}"
                msg = f"⭐ 群专属更新【ID:{new_id}】{now}\n{content}"
                await self.context.send_message(target, MessageChain([Plain(msg)]))
            except Exception as e:
                logger.error(f"群发送失败 {gid}: {e}")

        yield event.plain_result(f"✅ 群专属更新发布成功\n群：{gid} ID：{new_id}")

    # -------------------- 按ID查询：明确区分全局/群 --------------------
    @log_group.command("id")
    async def query_id(self, event: AstrMessageEvent):
        """
        根据ID查询公告，支持查询全局更新和当前群专属更新
        """
        parts = event.message_str.split()
        current_group = str(event.message_obj.group_id) if event.message_obj.group_id else None

        # 格式：/log id global 1
        if len(parts) >= 4 and parts[2] == "global":
            target_id = parts[3]
            for item in self.data["global"]:
                if str(item["id"]) == target_id:
                    yield event.plain_result(f"📢 全局更新【ID:{item['id']}】{item['time']}\n{item['content']}")
                    return
            yield event.plain_result("❌ 全局更新中无此ID")
            return

        # 格式：/log id group 1
        if len(parts) >= 4 and parts[2] == "group":
            if not current_group:
                yield event.plain_result("❌ 请在群内使用群专属查询")
                return

            target_id = parts[3]
            group_logs = self.data["group"].get(current_group, [])
            for item in group_logs:
                if str(item["id"]) == target_id:
                    yield event.plain_result(f"⭐ 本群专属更新【ID:{item['id']}】{item['time']}\n{item['content']}")
                    return
            yield event.plain_result("❌ 本群专属更新中无此ID")
            return

        # 错误提示
        yield event.plain_result("❌ 格式错误\n使用方法：\n/log id global 1\n/log id group 1")

    # -------------------- 搜索：返回完整内容 + 多条合并 --------------------
    @log_group.command("search")
    async def search(self, event: AstrMessageEvent):
        """
        搜索包含关键词的公告，返回完整内容
        """
        parts = event.message_str.split(" ", 2)
        if len(parts) < 3:
            yield event.plain_result("格式：/log search 关键词")
            return
        kw = parts[2]
        res = []

        for item in self.data["global"]:
            if kw in item["content"] and len(res) < 5:
                res.append(f"📢 全局更新【ID:{item['id']}】{item['time']}\n{item['content']}")

        for gid, logs in self.data["group"].items():
            for item in logs:
                if kw in item["content"] and len(res) < 5:
                    res.append(f"⭐ 群专属更新【ID:{item['id']}】{item['time']}\n{item['content']}")

        if not res:
            yield event.plain_result("❌ 未找到相关公告")
            return

        yield event.plain_result("\n--------------------\n".join(res))

    # -------------------- 删除 --------------------
    @log_group.command("del")
    async def delete(self, event: AstrMessageEvent):
        """
        管理员删除全局或群专属更新
        """
        if not self.is_admin(event):
            yield event.plain_result("❌ 无权限")
            return
        parts = event.message_str.split()
        if len(parts) < 4:
            yield event.plain_result("格式：/log del global 1 或 /log del group 123 1")
            return

        typ = parts[2]
        if typ == "global":
            did = parts[3]
            new_list = [x for x in self.data["global"] if str(x["id"]) != did]
            for i, x in enumerate(new_list, 1): x["id"] = i
            self.data["global"] = new_list
            save_data(self.data)
            yield event.plain_result("✅ 已删除全局更新并重新排序")

        elif typ == "group":
            if len(parts) < 5:
                yield event.plain_result("格式：/log del group 群号 ID")
                return
            gid = parts[3]
            did = parts[4]
            if gid not in self.data["group"]:
                yield event.plain_result("❌ 群无记录")
                return
            new_list = [x for x in self.data["group"][gid] if str(x["id"]) != did]
            for i, x in enumerate(new_list, 1): x["id"] = i
            self.data["group"][gid] = new_list
            save_data(self.data)
            yield event.plain_result("✅ 已删除群更新并重新排序")

    # -------------------- 列表 --------------------
    @log_group.command("list")
    async def list_logs(self, event: AstrMessageEvent):
        """
        管理员查看所有更新数量统计
        """
        if not self.is_admin(event):
            yield event.plain_result("❌ 无权限")
            return
        txt = f"全局：{len(self.data['global'])} 条"
        for g in self.data["group"]:
            txt += f"\n群{g}：{len(self.data['group'][g])} 条"
        yield event.plain_result(txt)
