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
    assert done == [] and not jobs._live


def test_finished_jobs_and_what_they_captured_are_freed(qtbot):
    """A job's closures can hold a whole workspace; once it finishes, nothing may keep them."""
    import gc
    import weakref

    class Big:
        pass

    jobs, refs = Jobs(2), []
    for _ in range(20):
        big = Big()
        refs.append(weakref.ref(big))
        handle = jobs.start(lambda emit, cancelled, b=big: None, done=lambda result, b=big: None)
    del big, handle
    jobs.wait(5000)
    qtbot.waitUntil(lambda: not jobs._live, timeout=5000)
    gc.collect()
    assert [r for r in refs if r() is not None] == []
