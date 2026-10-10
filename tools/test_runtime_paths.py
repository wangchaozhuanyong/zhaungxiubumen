"""Writable project-owned test output, separate from frozen candidate source."""
import os
from pathlib import Path


def root():
    value = os.environ.get('FLASHCAST_TEST_RUNTIME')
    source = Path(__file__).resolve().parents[1]
    if value:
        path = Path(value)
        if not path.is_absolute(): raise ValueError('absolute project-owned test runtime required')
    elif source.name == 'candidate':
        path = source.parent / 'test-runtime'
    else:
        raise ValueError('Set FLASHCAST_TEST_RUNTIME to a writable directory inside this project')
    scope = source.parent if source.name == 'candidate' else source
    if path.is_symlink() or scope.resolve() not in path.resolve().parents:
        raise ValueError('test runtime must remain inside its source delivery or project')
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink(): raise ValueError('test runtime cannot be a symlink')
    return path
