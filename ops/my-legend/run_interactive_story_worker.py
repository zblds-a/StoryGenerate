"""Opt-in worker. Run --migrate once; no model requests occur during migration."""
import argparse
import threading
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--migrate', action='store_true')
    args = parser.parse_args()
    from my_legend_production.production.cli import services
    from my_legend_production.production.interactive import workers
    repository, artifacts = services()
    service, story, background = workers(repository, artifacts)
    if args.migrate:
        repository.migrate()
        service.store.migrate()
        print('Interactive session schema ready; no model calls made.')
        return
    stop = threading.Event()
    def run(worker):
        while not stop.is_set():
            if not worker.run_once():
                stop.wait(1)
    threads = [threading.Thread(target=run, args=(background,), daemon=True) for _ in range(2)]
    for thread in threads:
        thread.start()
    try:
        run(story)
    except KeyboardInterrupt:
        stop.set()
    finally:
        for thread in threads:
            thread.join(timeout=5)


if __name__ == '__main__':
    main()
