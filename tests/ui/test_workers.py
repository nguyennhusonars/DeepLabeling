import threading
import time

from deeplabeling.ui.workers import Jobs


def run(qtbot, jobs, fn, **slots):
    job = jobs.start(fn, **slots)
    with qtbot.waitSignal(job.signals.finished, timeout=5000):
        pass
    return job


def test_a_result_arrives_on_the_gui_thread(qtbot):
    jobs, got = Jobs(1), []
    run(qtbot, jobs, lambda emit, cancelled: threading.get_ident(),
        done=lambda worker: got.append((worker, threading.get_ident())))
    qtbot.waitUntil(lambda: bool(got))
    worker, receiver = got[0]
    assert worker != receiver == threading.get_ident()


def test_batches_arrive_in_order_before_the_result(qtbot):
    jobs, got = Jobs(1), []

    def fn(emit, cancelled):
        for i in range(5):
            emit(i)
        return "end"

    run(qtbot, jobs, fn, batch=got.append, done=got.append)
    qtbot.waitUntil(lambda: len(got) == 6)
    assert got == [0, 1, 2, 3, 4, "end"]


def test_a_job_that_raises_reports_and_does_not_finish_with_a_result(qtbot):
    jobs, done, failed = Jobs(1), [], []

    def fn(emit, cancelled):
        raise OSError("disk gone")

    run(qtbot, jobs, fn, done=done.append, failed=failed.append)
    qtbot.waitUntil(lambda: bool(failed))
    assert done == [] and failed == ["OSError: disk gone"]


def test_a_cancelled_job_reports_nothing_and_is_released(qtbot):
    jobs, done = Jobs(1), []
    started = threading.Event()

    def fn(emit, cancelled):
        started.set()
        while not cancelled():
            time.sleep(0.001)
        return "too late"

    job = jobs.start(fn, done=done.append)
    started.wait(5)
    with qtbot.waitSignal(job.signals.finished, timeout=5000):
        jobs.cancel_all()
    qtbot.wait(20)
    assert done == [] and jobs._live == set()
