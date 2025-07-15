from mindtrace.cluster.workers.echo_worker import EchoWorker

if __name__ == "__main__":
    worker = EchoWorker.launch(host="localhost", port=8001, block=True)