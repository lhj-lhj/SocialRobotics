"""行为生成器：将动作描述转换为 Furhat API 调用"""
from typing import Optional, Tuple, Dict, Any
from furhat_realtime_api import AsyncFurhatClient


class BehaviorGenerator:
    """将信心等级和动作描述转换为 Furhat API 调用"""
    
    # 信心等级对应的前缀话术与动作描述
    CONFIDENCE_BEHAVIORS: Dict[str, Tuple[str, str]] = {
        "low": ("I'm not entirely sure, but", "slight head shake"),
        "medium": ("Let me think", "look straight"),
        "high": ("I'm confident that", "nod head"),
    }
    
    def __init__(self, furhat_client: Optional[AsyncFurhatClient] = None):
        self.furhat = furhat_client
    
    def get_confidence_behavior(self, confidence: str) -> Tuple[str, str]:
        """获取信心等级对应的语言前缀和动作描述"""
        if confidence not in self.CONFIDENCE_BEHAVIORS:
            confidence = "medium"  # 默认值
        return self.CONFIDENCE_BEHAVIORS[confidence]
    
    async def execute_gesture(self, gesture_description: str):
        """根据动作描述执行 Furhat 动作"""
        if not self.furhat:
            return
        
        # 将动作描述映射到 Furhat API 调用
        gesture_map = {
            "slight head shake": self._shake_head_slightly,
            "轻微摇头": self._shake_head_slightly,  # 兼容旧描述
            "look straight": self._look_straight,
            "平视凝神": self._look_straight,  # 兼容旧描述
            "nod head": self._nod_head,
            "点头示意": self._nod_head,  # 兼容旧描述
        }
        
        gesture_func = gesture_map.get(gesture_description)
        if gesture_func:
            try:
                await gesture_func()
            except Exception as e:
                print(f"执行动作 {gesture_description} 时出错: {e}")
    
    async def _shake_head_slightly(self):
        """轻微摇头 - 根据 Furhat Realtime API 文档使用 request.gesture.start"""
        if not self.furhat:
            return
        try:
            # Python 客户端可能不需要 monitor 参数
            await self.furhat.request_gesture_start(
                name="ShakeHead", 
                intensity=0.5, 
                duration=0.8
            )
        except (AttributeError, TypeError) as e:
            # 如果方法名或参数不同，尝试其他可能的调用方式
            try:
                await self.furhat.request_gesture(name="ShakeHead")
            except Exception as e2:
                print(f"Error executing head shake: {e2}")
        except Exception as e:
            print(f"Error executing head shake: {e}")
    
    async def _look_straight(self):
        """平视凝神 - 使用 attend_user 或中性姿态"""
        if not self.furhat:
            return
        try:
            # 注视用户作为"平视"的表现
            if hasattr(self.furhat, 'request_attend_user'):
                await self.furhat.request_attend_user()
        except Exception as e:
            print(f"Error executing look straight: {e}")
    
    async def _nod_head(self):
        """点头示意 - 根据 Furhat Realtime API 文档"""
        if not self.furhat:
            return
        try:
            # Python 客户端可能不需要 monitor 参数
            await self.furhat.request_gesture_start(
                name="Nod", 
                intensity=0.7, 
                duration=0.6
            )
        except (AttributeError, TypeError) as e:
            # 如果方法名或参数不同，尝试其他可能的调用方式
            try:
                await self.furhat.request_gesture(name="Nod")
            except Exception as e2:
                print(f"Error executing nod: {e2}")
        except Exception as e:
            print(f"Error executing nod: {e}")
    
    def resolve_confidence(self, hint: Optional[str], word_count: int) -> str:
        """根据提示或词数解析信心等级"""
        if hint and hint.strip().lower() in self.CONFIDENCE_BEHAVIORS:
            return hint.strip().lower()
        return self._estimate_confidence_from_words(word_count)
    
    def infer_confidence_from_text(self, text: str) -> str:
        """根据文本内容推断信心等级"""
        text_lower = text.lower()
        # 根据前缀话术推断信心等级
        if "i'm not entirely sure" in text_lower or "i'm not sure" in text_lower:
            return "low"
        elif "i'm confident" in text_lower or "i'm certain" in text_lower:
            return "high"
        elif "let me think" in text_lower or "i think" in text_lower:
            return "medium"
        # 默认中等信心
        return "medium"
    
    @staticmethod
    def _estimate_confidence_from_words(word_count: int) -> str:
        """根据累计词数粗略估计信心等级"""
        if word_count < 25:
            return "low"
        if word_count < 60:
            return "medium"
        return "high"

