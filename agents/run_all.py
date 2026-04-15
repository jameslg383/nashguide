"""Run all background agents in a single process using threads."""
import logging
import threading
import time

from agents import planner_agent, delivery_agent, marketing_agent, updater_agent

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("run_all")


def _thread(name, fn):
    t = threading.Thread(target=fn, name=name, daemon=True)
    t.start()
    return t


def main():
    log.info("Starting NashGuide agent swarm…")
    threads = [
        _thread("planner", planner_agent.run),
        _thread("delivery", delivery_agent.run),
        _thread("marketing", marketing_agent.run),
        _thread("updater", updater_agent.run),
    ]
    while True:
        time.sleep(60)
        for t in threads:
            if not t.is_alive():
                log.error("Agent thread died: %s", t.name)


if __name__ == "__main__":
    main()
