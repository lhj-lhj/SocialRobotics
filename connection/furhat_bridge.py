"""Furhat 连接桥接模块"""
import asyncio
import signal
from typing import Optional
from furhat_realtime_api import AsyncFurhatClient, Events

from plan.orchestrator import Orchestrator
from plan.behavior_generator import BehaviorGenerator
from utils.print_utils import cprint


class FurhatBridge:
    """Furhat 机器人连接桥接器"""

    def __init__(self, host: str = "192.168.1.114", auth_key: Optional[str] = None):
        self.host = host
        self.auth_key = auth_key
        self.conversation_starter = "Hello, I am Furhat. How are you today?"
        self.stop_event: Optional[asyncio.Event] = None
        self.shutting_down = False
        
        # 连接 Furhat
        self.furhat = AsyncFurhatClient(host, auth_key=auth_key)
        
        # 创建行为生成器，传入 furhat 客户端
        self.behavior_generator = BehaviorGenerator(furhat_client=self.furhat)
        
        # 对话历史
        self.dialog_history = []
        self.current_user_utt: Optional[str] = None
        self.orchestrator_task: Optional[asyncio.Task] = None

    def setup_signal_handlers(self):
        """设置信号处理器，用于优雅关闭"""
        def signal_handler(signum, frame):
            # 信号 2 = SIGINT (Ctrl+C), 信号 15 = SIGTERM
            signal_name = "SIGINT" if signum == 2 else f"SIGTERM ({signum})"
            cprint(f"\nReceived {signal_name}, shutting down gracefully...")
            # 设置停止事件，让主循环处理关闭
            if self.stop_event is not None:
                self.stop_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)

    async def shutdown(self):
        """优雅关闭"""
        if self.shutting_down:
            return
        
        self.shutting_down = True
        cprint("Shutting down...")
        
        try:
            # 取消正在进行的请求
            self.cancel_request()
            # 停止听和说
            await self.furhat.request_listen_stop()
            await self.furhat.request_speak_stop()
        except Exception as e:
            cprint(f"Error during shutdown: {e}")
        
        if self.stop_event is not None:
            self.stop_event.set()

    def commit_user(self):
        """提交用户输入到历史记录"""
        if self.current_user_utt is None:
            return
        self.dialog_history.append({"role": "user", "content": self.current_user_utt})
        self.current_user_utt = None

    def commit_robot(self, message: str):
        """提交机器人回复到历史记录"""
        self.dialog_history.append({"role": "assistant", "content": message})

    def cancel_request(self):
        """取消正在进行的请求"""
        self.current_user_utt = None
        if self.orchestrator_task and not self.orchestrator_task.done():
            cprint("[System] Cancelling request...")
            self.orchestrator_task.cancel()

    async def on_hear_start(self, event):
        """用户开始说话时的事件处理"""
        if not self.shutting_down:
            cprint("\n[User] Started speaking...")
            self.cancel_request()

    async def on_hear_end(self, event):
        """用户停止说话时的事件处理"""
        if self.shutting_down:
            return
        
        # 防止重复处理：如果已有任务在运行且未完成，则不处理新输入
        if self.orchestrator_task and not self.orchestrator_task.done():
            cprint("[System] Previous request still processing, ignoring new input")
            return
        
        user_text = event.get("text", "").strip()
        if not user_text:
            return
        
        cprint(f"[User] Speech content: {user_text}")
        self.current_user_utt = user_text
        self.orchestrator_task = asyncio.create_task(self._process_user_input(user_text))

    async def on_hear_partial(self, event):
        """用户说话过程中的部分识别结果"""
        if not self.shutting_down:
            partial_text = event.get("text", "")
            cprint(f"[User] Recognizing: {partial_text}", end='\r')

    async def on_speak_start(self, event):
        """机器人开始说话时的事件处理 - 根据说话内容生成动作"""
        if not self.shutting_down:
            robot_text = event.get("text", "")
            cprint(f"[Robot] Started speaking: {robot_text}")
            self.commit_user()
            
            # 根据说话内容推断信心等级并执行相应动作
            confidence = self.behavior_generator.infer_confidence_from_text(robot_text)
            _, gesture_description = self.behavior_generator.get_confidence_behavior(confidence)
            cprint(f"[System] Inferred confidence: {confidence}, gesture: {gesture_description}")
            
            # 执行动作
            if self.behavior_generator.furhat:
                await self.behavior_generator.execute_gesture(gesture_description)

    async def on_speak_end(self, event):
        """机器人停止说话时的事件处理"""
        if not self.shutting_down:
            robot_text = event.get("text", "")
            aborted = event.get("aborted", False)
            if aborted:
                cprint(f"[Robot] Speech interrupted: {robot_text}")
            self.commit_robot(robot_text)
            # 清理任务，允许处理下一个输入
            self.orchestrator_task = None

    async def _process_user_input(self, user_text: str):
        """处理用户输入，调用 Orchestrator"""
        try:
            # 传入 furhat 客户端，让 Orchestrator 可以直接发送文本
            orchestrator = Orchestrator(
                user_text, 
                behavior_generator=self.behavior_generator,
                furhat_client=self.furhat
            )
            await orchestrator.run()
            # 处理完成后清理任务
            self.orchestrator_task = None
                
        except asyncio.CancelledError:
            cprint("[System] Request cancelled")
            self.orchestrator_task = None
        except Exception as e:
            cprint(f"\n❌ Error processing user input: {e}")
            import traceback
            traceback.print_exc()
            self.orchestrator_task = None

    async def run(self):
        """运行主对话循环"""
        self.stop_event = asyncio.Event()
        self.setup_signal_handlers()
        cprint("Starting dialogue...")
        cprint("Press Ctrl+C to stop gracefully")
        
        try:
            await self.furhat.connect()
        except Exception as e:
            cprint(f"Failed to connect to Furhat ({self.host}): {e}")
            return

        # 注册事件处理器
        self.furhat.add_handler(Events.response_hear_start, self.on_hear_start)
        self.furhat.add_handler(Events.response_hear_end, self.on_hear_end)
        self.furhat.add_handler(Events.response_hear_partial, self.on_hear_partial)
        self.furhat.add_handler(Events.response_speak_start, self.on_speak_start)
        self.furhat.add_handler(Events.response_speak_end, self.on_speak_end)

        # 注视用户
        await self.furhat.request_attend_user()

        # 开始对话
        await self.furhat.request_speak_text(self.conversation_starter)

        # 开始监听（启用部分识别结果）
        await self.furhat.request_listen_start(
            concat=True,  # 将用户语音连接成单个话语
            partial=True,  # 启用部分识别结果以实时查看识别
            stop_no_speech=False,
            stop_user_end=False,
            stop_robot_start=True,  # 机器人开始说话时停止监听
            resume_robot_end=True,  # 机器人停止说话后恢复监听
            end_speech_timeout=0.5
        )

        # 等待关闭信号
        await self.stop_event.wait()

        # 开始关闭流程
        cprint("Shutting down...")
        await self.shutdown()
        
        # 断开连接
        try:
            await self.furhat.disconnect()
            cprint("Disconnected from Furhat")
        except Exception as e:
            cprint(f"Error disconnecting: {e}")

