"""批量处理模块，用于高效处理大量图片。"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Generic

T = TypeVar('T')
R = TypeVar('R')

class BatchProcessor(Generic[T, R]):
    """批量处理器，用于并发处理大量任务"""
    
    def __init__(self, max_workers: int = None):
        """
        初始化批量处理器
        
        Args:
            max_workers: 最大工作线程数，默认为None（由ThreadPoolExecutor自动决定）
        """
        self.max_workers = max_workers
    
    def process_batch(self, 
                      items: List[T], 
                      process_func: Callable[[T, int], R],
                      on_success: Optional[Callable[[int, T, R], None]] = None,
                      on_error: Optional[Callable[[int, T, Exception], None]] = None) -> Dict[int, R]:
        """
        批量处理任务
        
        Args:
            items: 要处理的项目列表
            process_func: 处理函数，接收项目和索引作为参数
            on_success: 成功回调函数，接收索引、项目和结果作为参数
            on_error: 错误回调函数，接收索引、项目和异常作为参数
            
        Returns:
            处理结果字典，键为索引，值为处理结果
        """
        results = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 创建任务
            future_to_index = {
                executor.submit(process_func, item, i): i 
                for i, item in enumerate(items)
            }
            
            # 处理结果
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                item = items[index]
                
                try:
                    result = future.result()
                    results[index] = result
                    
                    if on_success:
                        on_success(index, item, result)
                        
                except Exception as e:
                    if on_error:
                        on_error(index, item, e)
        
        return results
