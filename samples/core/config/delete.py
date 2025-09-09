from mindtrace.core import Mindtrace


class Delete(Mindtrace):
    def __init__(self):
        super().__init__()
        print(self.config.MINDTRACE_DEFAULT_HOST_URLS)

    @classmethod
    def get_default_host_urls(cls):
        return cls.config['MINDTRACE_DEFAULT_HOST_URLS']['SERVICE']

if __name__ == "__main__":
    # delete = Delete()
    print(Delete.get_default_host_urls())