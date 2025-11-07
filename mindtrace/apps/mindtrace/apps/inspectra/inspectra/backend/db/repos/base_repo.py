import inspect as _inspect
from contextlib import asynccontextmanager
from functools import wraps


class BaseRepo:
    @staticmethod
    def with_db(fn):
        if not _inspect.iscoroutinefunction(fn):
            raise TypeError("@with_db can only decorate async functions")

        @wraps(fn)
        async def _wrap(*args, **kwargs):
            # circular import avoid
            from inspectra.backend.db.init import ensure_db_init

            await ensure_db_init()
            return await fn(*args, **kwargs)

        return _wrap

    @classmethod
    @asynccontextmanager
    async def ready(cls):
        """Use this if you want to do multiple ops with a single ensure."""
        from inspectra.backend.db.init import ensure_db_init

        await ensure_db_init()
        yield


class AutoInitRepo(BaseRepo):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name, attr in list(cls.__dict__.items()):
            if name.startswith("_"):
                continue
            fn = None

            if isinstance(attr, staticmethod):
                fn = attr.__func__
                is_static = True
                is_class = False
            elif isinstance(attr, classmethod):
                fn = attr.__func__
                is_static = False
                is_class = True
            else:
                fn = attr
                is_static = False
                is_class = False

            if _inspect.iscoroutinefunction(fn):
                wrapped = cls.with_db(fn)
                if is_static:
                    wrapped = staticmethod(wrapped)
                elif is_class:
                    wrapped = classmethod(wrapped)
                setattr(cls, name, wrapped)
