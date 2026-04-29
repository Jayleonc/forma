"""Document Conversion Feature Package."""

def run_conversion(*args, **kwargs):
    from .workflow import run_conversion as _run_conversion
    return _run_conversion(*args, **kwargs)


def convert_path(*args, **kwargs):
    from .workflow import convert_path as _convert_path
    return _convert_path(*args, **kwargs)


__all__ = ["convert_path", "run_conversion"]
