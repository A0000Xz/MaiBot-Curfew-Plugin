import asyncio
import toml
import tomlkit # type: ignore
import os
import re
from datetime import datetime
from typing import Tuple, Optional, Dict, Any, List, Type
from src.common.logger import get_logger
from src.plugin_system.base.config_types import ConfigField
from src.plugin_system.base.base_plugin import BasePlugin, register_plugin
from src.plugin_system.base.base_command import BaseCommand
from src.plugin_system.apis import send_api
from src.plugin_system.base.component_types import ComponentInfo

logger = get_logger("curfew")

class CurfewCommand(BaseCommand):
    command_name = "curfew"
    command_description = "启用或者禁用宵禁"
    command_pattern = r"^/curfew\s+(?P<operation_type>\w+)(?:\s+(?P<action_type>\w+))?(?:\s+(?P<value>.+))?$"
    command_help = "使用方法: /curfew <true|false> - 设置宵禁功能开或者关"
    command_examples = [
        "/curfew true - 开启宵禁",
        "/curfew false - 关闭宵禁"
    ]
    enable_command = True
    
    _curfew_task: Optional[asyncio.Task] = None
    _is_curfew_active: bool = False

    def __init__(self, message, plugin_config: dict = None):
        super().__init__(message,plugin_config)
        self._services = {}
        self.log_prefix = f"[Command:{self.command_name}]"
        self.send_api = send_api
    
    async def execute(self) -> Tuple[bool, Optional[str]]:
        try:
            sender = self.message.message_info.user_info
            group = self.message.message_info.group_info
            operation_type = self.matched_groups.get("operation_type")
            action_type = self.matched_groups.get("action_type")
            value = self.matched_groups.get("value")
            
            if group == None:  #首先确定是不是群聊环境
                target = None
                isgroup = False
                target_id = sender.user_id  # 不是群聊环境就把id换成私聊的QQ号
            else:
                target = group.group_id
                target_id = group.group_id  # 是群聊就把id设置为QQ群号

            if not self._check_group_permission(target) and not group == None: # 检查在不在生效群聊里，当然，必须是群聊环境，但也能透传私聊
                return False,""

            if group == None and (operation_type == "true" or operation_type == "false"):
                await self.send_message("抱歉，私聊情况下，'true'或者'false'参数都是被禁用的",sender.user_id,False) # 做一个提醒，告诉私聊的人用不了/curfew true或者false
                return False,""
            
            if not self._check_person_permission(sender.user_id): # 检查个人权限，不是管理用户就直接截断命令
                await self.send_message(
                    "权限不足，你无权使用此命令", 
                    target_id,
                    isgroup
                )
                return False,""
        
            # 使用字典映射替代长串if-elif判断
            operation_map = {
                "true": lambda: self._start_curfew_task(target_id),
                "false": lambda: self._handle_disable(target_id),
                "time": lambda: self._handle_time_list(target_id, action_type, isgroup),
                "start_time": lambda: self._handle_time_config(operation_type, action_type, value, target_id, isgroup),
                "end_time": lambda: self._handle_time_config(operation_type, action_type, value, target_id, isgroup),
                "permission_group": lambda: self._handle_permission_group(action_type, value, target_id, isgroup)
            }
            
            if operation_type in operation_map:
                await operation_map[operation_type]()
                return True, ""
            else:
                await self.send_message(
                    "别乱填参数啊，可以用的有'true'，'false'，'time'，'start_time'，'end_time'，'permission_group'", 
                    target_id,
                    isgroup
                )
                logger.error(f"{self.log_prefix} 参数错误")
                return False, ""
            
        except Exception as e:
            logger.error(f"{self.log_prefix} 执行错误: {e}")
            return False, f"执行失败: {str(e)}"

    async def _handle_disable(self, group_id: str) -> Tuple[bool, str]:
        """处理禁用宵禁"""
        await self._stop_curfew_task(group_id)
        await self._apply_curfew_state(False, self._load_config(), send_message=False)
        return True, ""

    async def _handle_time_list(self, group_id: str, action_type: str, isgroup:bool = True) -> Tuple[bool, str]:
        """列出权限组列表"""
        if action_type == "list":
            config = self._load_config()
            start_time = config["curfew"].get("start_time", "23:00")
            end_time = config["curfew"].get("end_time", "6:00")
            await self.send_message(f"当前设置的宵禁时间是{start_time}~{end_time}哦", group_id, isgroup)
            logger.info(f"{self.log_prefix} 已列出宵禁时段")
            return True, ""
        else:
            await self.send_message(f"{action_type}不是可用的参数，目前只有'list'这一个参数哦", group_id, isgroup)
            return False, ""

    async def _handle_time_config(self, operation_type, action_type: str, value: str, group_id: str, isgroup:bool = True) -> Tuple[bool, str]:
        """处理时间配置"""
        if action_type != "set":
            await self.send_message(f"{action_type}不是可用的参数，目前只有'set'这一个参数哦", group_id, isgroup)
            return False, ""
        
        if value == None:
            await self.send_message("别什么都不填啊，这里填时间啊", group_id, isgroup)
            return False, ""

        if not re.match(r"^([01]?[0-9]|2[0-3]):([0-5][0-9])$", value) and not value == "24:00":
            await self.send_message(f"{value}不是可用的参数，要填0:00到23:59之间这种格式的参数哦", group_id, isgroup)
            return False, ""
        
        # 处理24:00特殊情况
        if value == "24:00":
            value = "00:00"
        
        set_text = "宵禁开始时间" if operation_type == "start_time" else "宵禁结束时间"
        
        await self.set_config(operation_type, action_type, value, group_id, isgroup)
        message = f"不能识别24:00哦，已经给你改好了，将{set_text}变更为{value}" if value == "00:00" else f"已将{set_text}变更为{value}"
        await self.send_message(message, group_id, isgroup)
        logger.info(f"{self.log_prefix} 已将{set_text}变更为{value}")
        return True, ""

    async def _handle_permission_group(self, action_type: str, value: str, group_id: str, isgroup:bool = True) -> Tuple[bool, str]:
        """处理权限组配置"""
        action_handlers = {
            "add": self._handle_group_add,
            "remove": self._handle_group_remove,
            "list": self._handle_group_list
        }
        
        handler = action_handlers.get(action_type)
        if handler:
            return await handler(group_id, value, isgroup)
        else:
            await self.send_message(f"{action_type}不是可用的参数，目前只有'add','remove','list'三个参数哦", group_id, isgroup)
            return False, ""

    async def _handle_group_add(self, group_id: str, value: str, isgroup:bool = True) -> Tuple[bool, str]:
        """添加群组到权限列表"""
        if value == None:
            await self.send_message("别什么都不填啊，这里填群号啊", group_id, isgroup)
            return False, ""
        
        if not re.match(r"^[1-9]\d{4,10}$", value):
            await self.send_message(f"不对，你确定{value}是一个群号吗？", group_id, isgroup)
            return False, ""
        
        await self.set_config("permission_group", "add", value, group_id, isgroup)
        return True, ""

    async def _handle_group_remove(self, group_id: str, value: str, isgroup:bool = True) -> Tuple[bool, str]:
        """从权限列表移除群组"""
        if value == None:
            await self.send_message("别什么都不填啊，这里填群号啊", group_id, isgroup)
            return False, ""
        
        if not re.match(r"^[1-9]\d{4,10}$", value):
            await self.send_message(f"不对，你确定{value}是一个群号吗？", group_id, isgroup)
            return False, ""
        
        await self.set_config("permission_group", "remove", value, group_id, isgroup)
        return True, ""

    async def _handle_group_list(self, group_id: str, value: str, isgroup:bool = True) -> Tuple[bool, str]:
        """列出权限组列表"""
        config = self._load_config()
        allowed_groups = config["permissions"].get("groups", [])
        result = "宵禁插件生效的QQ群列表：\n" + "\n".join(allowed_groups)
        await self.send_message(result, group_id, isgroup)
        logger.info(f"{self.log_prefix} 已列出所有生效群聊")
        return True, ""

    def _check_group_permission(self, group_id: str) -> bool:
        """权限检查逻辑"""
        config = self._load_config()
        allowed_groups = config["permissions"].get("groups", [])
        return group_id in allowed_groups

    def _check_person_permission(self, user_id: str) -> bool:
        """权限检查逻辑"""
        config = self._load_config()
        admin_users = config["permissions"].get("admin_users", [])
        return user_id in admin_users
    
    def _load_config(self) -> Dict[str, Any]:
        """从同级目录的config.toml文件直接加载配置"""
        try:
            # 获取当前文件所在目录
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "config.toml")
            
            # 读取并解析TOML配置文件
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = toml.load(f)
            
            # 构建配置字典，使用get方法安全访问嵌套值
            config = {
                "curfew": {
                    "start_time": config_data.get("curfew", {}).get("start_time", "23:00"),
                    "end_time": config_data.get("curfew", {}).get("end_time", "06:00"),
                    "check_interval": config_data.get("curfew", {}).get("check_interval", 60)
                },
                "messages": {
                    "mute_message": config_data.get("messages", {}).get("mute_message", "宵禁时间到咯"),
                    "unmute_message": config_data.get("messages", {}).get("unmute_message", "宵禁时间结束咯")
                },
                "permissions": {
                    "admin_users": config_data.get("permissions", {}).get("admin_users", []),
                    "groups": config_data.get("permissions", {}).get("groups", [])
                }
            }
            return config
        except Exception as e:
            logger.error(f"{self.log_prefix} 加载配置失败: {e}")
            raise

    async def set_config(self, operation_type: str, action_type: str, value: str, group_id: str, isgroup: bool = True):
        """使用tomlkit修改配置文件，保持注释和格式"""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "config.toml")
            
            # 使用tomlkit读取，保持格式和注释
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = tomlkit.load(f)
            
            if operation_type in ["start_time", "end_time"]:
                config_data["curfew"][operation_type] = value
            elif operation_type == "permission_group":
                groups_list = config_data["permissions"]["groups"]
                if action_type == "add" and value not in groups_list:
                    groups_list.append(value)
                    await self.send_message(f"已将群聊{value}添加到生效群聊中", group_id, isgroup)
                    logger.info(f"{self.log_prefix} 已将群聊{value}添加到生效群聊中")
                elif action_type == "remove" and value in groups_list:
                    groups_list.remove(value)
                    await self.send_message(f"已将群聊{value}从生效群聊中移除", group_id, isgroup)
                    logger.info(f"{self.log_prefix} 已将群聊{value}从生效群聊中移除")
                else:
                    message = "这个群已经在生效群聊里了。" if action_type == "add" else "这个群压根不在生效群聊里！"
                    await self.send_message(message, group_id, isgroup)
                    logger.info(f"{self.log_prefix} {message}")
                    return
            
            # 使用tomlkit写入，保持格式和注释
            with open(config_path, 'w', encoding='utf-8') as f:
                tomlkit.dump(config_data, f)
                
        except Exception as e:
            logger.error(f"{self.log_prefix} 更新配置文件失败: {e}")
            raise
            
    async def send_message(self,content,target_id, isgroup:bool = True):
        """单独构建的的一个发消息方法"""
        if isgroup:
            await send_api.text_to_group(content,target_id)
        else:
            await send_api.text_to_user(content,target_id)        

    def _is_in_curfew_time(self, config: Dict[str, Any]) -> bool:
        """检查是否在宵禁时间"""
        try:
            now = datetime.now().time()
            curfew_config = config["curfew"]
            start_time = datetime.strptime(curfew_config["start_time"], "%H:%M").time()
            end_time = datetime.strptime(curfew_config["end_time"], "%H:%M").time()
            
            if start_time <= end_time:
                # 当天内的时间段
                return start_time <= now <= end_time
            else:
                # 跨天的时间段
                return now >= start_time or now <= end_time
        except Exception as e:
            logger.error(f"{self.log_prefix} 解析时间配置失败: {e}")
            return False

    async def _apply_curfew_state(self, should_mute: bool, config: Dict[str, Any], send_message: bool = True, first: bool=True):
        """对指定的群聊开始应用宵禁"""
        target_groups = config["permissions"]["groups"]
        if not target_groups:
            logger.warning(f"{self.log_prefix} 未配置目标群组，跳过操作")
            return

        messages = config["messages"]
        message = messages["mute_message" if should_mute else "unmute_message"]
        action = "宵禁" if should_mute else "解除宵禁"

        for group_id in target_groups:
            try:
                if (first or should_mute) and send_message:
                    await send_api.text_to_group(message, group_id)
                await send_api.command_to_group(
                    {"name": "GROUP_WHOLE_BAN", "args": {"enable": should_mute}},
                    group_id
                )
                logger.info(f"{self.log_prefix} {action}操作成功: {group_id}")
            except Exception as e:
                logger.error(f"{self.log_prefix} {action}操作失败: {group_id} - {e}")

    async def _curfew_monitor_task(self, first_run:bool):
        """宵禁监控任务"""
        logger.info(f"{self.log_prefix} 监控任务启动")
        last_state = None
        
        try:
            while True:
                config = self._load_config()
                current_state = self._is_in_curfew_time(config)
                
                if current_state != last_state:
                    await self._apply_curfew_state(current_state, config, first=first_run)
                    last_state = current_state
                    first_run = True
                    logger.info(f"{self.log_prefix} 宵禁功能状态变更: {'启用' if current_state else '禁用'}")
                
                await asyncio.sleep(config["curfew"]["check_interval"])
        
        except asyncio.CancelledError:
            logger.info(f"{self.log_prefix} 监控任务已取消")
            raise

    @classmethod
    async def _send_notification(cls, message: str, group_id: str):
        """发送通知消息的辅助方法"""
        try:
            # 创建临时实例仅用于发送消息
            temp_instance = cls.__new__(cls)
            temp_instance.message = None
            temp_instance._services = {}
            temp_instance.log_prefix = f"[Command:curfew]"
            temp_instance.send_api = send_api
            
            await temp_instance.send_api.text_to_group(message, group_id)
            # temp_instance 在这里会自动被回收
        except Exception as e:
            logger.error(f"[Command:curfew] 发送通知失败: {e}")

    @classmethod
    async def _start_curfew_task(cls, group_id: str):
        """启动定时任务"""
        if cls._curfew_task is None or cls._curfew_task.done():
            await cls._send_notification("宵禁功能启用成功", group_id)
            
            # 创建监控任务实例（这个实例会持续存在直到任务结束）
            task_instance = cls.__new__(cls)
            task_instance.message = None
            task_instance._services = {}
            task_instance.log_prefix = f"[Command:curfew]"
            first_run=False
            
            cls._curfew_task = asyncio.create_task(task_instance._curfew_monitor_task(first_run))
            cls._is_curfew_active = True
            logger.info(f"[Command:curfew] 定时任务已启动")
        else:
            await cls._send_notification("宵禁功能已经启用啦", group_id)
            logger.info(f"[Command:curfew] 任务已在运行中")

    @classmethod
    async def _stop_curfew_task(cls, group_id: str):
        """停止定时任务"""
        if cls._curfew_task and not cls._curfew_task.done():
            await cls._send_notification("宵禁功能关闭中，正在解除禁言", group_id)
            
            cls._curfew_task.cancel()
            try:
                await cls._curfew_task
            except asyncio.CancelledError:
                pass
            cls._curfew_task = None
            cls._is_curfew_active = False
            logger.info(f"[Command:curfew] 定时任务已停止")
        else:
            await cls._send_notification("宵禁功能已经关啦", group_id)
            logger.info(f"[Command:curfew] 没有运行中的任务")

    @classmethod
    async def cleanup_on_shutdown(cls):
        """关闭时清理任务"""
        logger.info(f"[Command:curfew] 正在清理...")
        if cls._curfew_task and not cls._curfew_task.done():
            cls._curfew_task.cancel()
            try:
                await cls._curfew_task
            except asyncio.CancelledError:
                pass
            cls._curfew_task = None
            cls._is_curfew_active = False
            logger.info(f"[Command:curfew] 清理完成")

@register_plugin
class CurfewPlugin(BasePlugin):
    """宵禁插件
    - 支持配置宵禁时间
    - 支持配置生效的群聊
    - 支持配置管理者QQ号
    - 完整的错误处理
    - 防误操作设计
    """

    # 插件基本信息
    plugin_name = "curfew_plugin"
    enable_plugin = True
    config_file_name = "config.toml"

    # 配置节描述
    config_section_descriptions = {
        "plugin": "插件基本配置",
        "components": "组件启用控制",
        "curfew":"宵禁时间配置（支持热重载）",
        "messages":"宵禁前后的消息内容（支持热重载）",
        "permissions": "管理者用户配置（支持热重载）",
        "logging": "日志记录配置",
    }

    # 配置Schema定义
    config_schema = {
        "plugin": {
            "config_version": ConfigField(type=str, default="0.8.0", description="插件配置文件版本号"),
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
        },
        "components": {
            "enable_curfew": ConfigField(type=bool, default=True, description="是否启用宵禁本体组件"),
        },
        "curfew": {
            "start_time": ConfigField(type=str, default="23:00", description="宵禁开始时间（注意，不存在24:00，请使用0:00）"),
            "end_time": ConfigField(type=str, default="6:00", description="宵禁结束时间（同上，请注意不存在24:00）"),
            "check_interval": ConfigField(type=int, default=60, description="每隔多长时间检查一次当前时间，如果不懂的话不要乱动这个数值"),
        },
        "messages": {
            "mute_message": ConfigField(type=str, default="宵禁时间到咯", description="宵禁开始时麦麦会说的话"),
            "unmute_message": ConfigField(type=str, default="宵禁时间结束咯", description="宵禁结束时麦麦会说的话"),
        },
        "permissions": {
            "groups": ConfigField(type=List, default=["123456789"], description="宵禁插件将会生效的群聊，记得用英文单引号包裹并使用逗号分隔"),
            "admin_users": ConfigField(type=List, default=["123456789"], description="请写入被许可用户的QQ号，记得用英文单引号包裹并使用逗号分隔。这个配置会决定谁被允许使用宵禁状态调整指令"),
        },
        "logging": {
            "level": ConfigField(
                type=str, default="INFO", description="日志级别", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
            ),
            "prefix": ConfigField(type=str, default="[Curfew]", description="日志前缀"),
        },
    }


    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表"""

        components = []

        if self.get_config("components.enable_curfew", True):
            components.append((CurfewCommand.get_command_info(), CurfewCommand))

        return components
