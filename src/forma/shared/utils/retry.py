"""重试装饰器模块，用于处理外部服务调用的短暂失败。"""

import functools
import time
from typing import Any, Callable, Optional, Type, Union, List, Tuple

def retry(
    max_tries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    指数退避重试装饰器
    
    Args:
        max_tries: 最大尝试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟时间的增长因子
        exceptions: 需要捕获并重试的异常类型
        on_retry: 重试前调用的回调函数，接收异常和尝试次数作为参数
        
    Returns:
        装饰后的函数
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            mtries, mdelay = max_tries, delay
            last_exception = None
            
            for i in range(mtries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if i == mtries - 1:
                        raise
                    
                    if on_retry:
                        on_retry(e, i + 1)
                    
                    time.sleep(mdelay)
                    mdelay *= backoff
            
            # 这里不应该到达，但为了类型检查添加
            raise last_exception
        return wrapper
    return decorator


def retry_async(
    max_tries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    异步函数的指数退避重试装饰器
    
    Args:
        max_tries: 最大尝试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟时间的增长因子
        exceptions: 需要捕获并重试的异常类型
        on_retry: 重试前调用的回调函数，接收异常和尝试次数作为参数
        
    Returns:
        装饰后的异步函数
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            import asyncio
            
            mtries, mdelay = max_tries, delay
            last_exception = None
            
            for i in range(mtries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if i == mtries - 1:
                        raise
                    
                    if on_retry:
                        on_retry(e, i + 1)
                    
                    await asyncio.sleep(mdelay)
                    mdelay *= backoff
            
            # 这里不应该到达，但为了类型检查添加
            raise last_exception
        return wrapper
    return decorator
