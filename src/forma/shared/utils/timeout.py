"""超时机制模块，用于避免长时间阻塞。"""

import asyncio
import functools
import signal
from typing import Any, Callable, Optional, Type, TypeVar, cast

T = TypeVar('T')

class TimeoutError(Exception):
    """超时异常"""
    pass

def timeout(seconds: int):
    """
    同步函数超时装饰器，使用signal实现
    
    Args:
        seconds: 超时时间（秒）
        
    Returns:
        装饰后的函数
    
    Raises:
        TimeoutError: 如果函数执行超时
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            def handler(signum: int, frame: Any) -> None:
                raise TimeoutError(f"Function {func.__name__} timed out after {seconds} seconds")
            
            # 设置信号处理器
            original_handler = signal.getsignal(signal.SIGALRM)
            signal.signal(signal.SIGALRM, handler)
            
            # 设置闹钟
            signal.alarm(seconds)
            try:
                result = func(*args, **kwargs)
            finally:
                # 取消闹钟并恢复原始信号处理器
                signal.alarm(0)
                signal.signal(signal.SIGALRM, original_handler)
            
            return result
        return wrapper
    return decorator


async def async_timeout(seconds: int, coro: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """
    异步函数超时包装器
    
    Args:
        seconds: 超时时间（秒）
        coro: 异步协程函数
        args: 位置参数
        kwargs: 关键字参数
        
    Returns:
        协程函数的结果
        
    Raises:
        asyncio.TimeoutError: 如果协程执行超时
    """
    try:
        async with asyncio.timeout(seconds):
            return await coro(*args, **kwargs)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Function {coro.__name__} timed out after {seconds} seconds")
