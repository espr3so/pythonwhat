import re
import os
import inspect
from collections import defaultdict
from functools import wraps

from pythonwhat.local import StubProcess, run_exercise, ChDir, WorkerProcess
from contextlib import contextmanager
from protowhat.Test import TestFail as TF
from pythonwhat.test_exercise import test_exercise
from pythonwhat.sct_syntax import Chain
import pytest
import tempfile


test_data = defaultdict(list)


def capture_test_data(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        result = f(*args, **kwargs)

        data = kwargs.copy()
        del data["student_process"]
        del data["solution_process"]
        data["result"] = result

        context = "other"
        stack = inspect.stack()
        for frame in stack:
            _, filename = os.path.split(frame.filename)
            if filename and filename.startswith("test_"):
                context = filename
                break
        test_data[context].append(data.copy())

        return result

    return wrapper


test_exercise = capture_test_data(test_exercise)


@contextmanager
def in_temp_dir():
    with tempfile.TemporaryDirectory() as d:
        with ChDir(d):
            yield d


def run(data, run_code=True):

    pec = data.get("DC_PEC", "")
    stu_code = data.get("DC_CODE", "")
    sol_code = data.get("DC_SOLUTION", "")
    sct = data.get("DC_SCT", "")
    force_diagnose = data.get("DC_FORCE_DIAGNOSE", False)

    with in_temp_dir():
        if run_code:
            sol_process, stu_process, raw_stu_output, error = run_exercise(
                pec, sol_code, stu_code
            )
        else:
            raw_stu_output = ""
            stu_process = StubProcess()  # WorkerProcess()
            sol_process = StubProcess()  # WorkerProcess()
            error = None

        res = test_exercise(
            sct=sct,
            student_code=stu_code,
            solution_code=sol_code,
            pre_exercise_code=pec,
            student_process=stu_process,
            solution_process=sol_process,
            raw_student_output=raw_stu_output,
            ex_type="NormalExercise",
            force_diagnose=force_diagnose,
            error=error,
        )

    return res


def get_sct_payload(output):
    sct_output = [out for out in output if out["type"] == "sct"]
    if len(sct_output) > 0:
        return sct_output[0]["payload"]
    else:
        print(output)
        return None


def passes(st):
    assert isinstance(st, Chain)


@contextmanager
def verify_sct(correct):
    if correct:
        yield
    else:
        with pytest.raises(TF):
            yield


def test_lines(test, sct_payload, ls, le, cs, ce):
    test.assertEqual(sct_payload["line_start"], ls)
    test.assertEqual(sct_payload["line_end"], le)
    test.assertEqual(sct_payload["column_start"], cs)
    test.assertEqual(sct_payload["column_end"], ce)


def test_absent_lines(test, sct_payload):
    test.assertFalse("line_start" in sct_payload)
    test.assertFalse("line_end" in sct_payload)
    test.assertFalse("column_start" in sct_payload)
    test.assertFalse("column_end" in sct_payload)


def with_line_info(output, ls, le, cs, ce):
    assert output["line_start"] == ls
    assert output["line_end"] == le
    assert output["column_start"] == cs
    assert output["column_end"] == ce


def no_line_info(output):
    assert "line_start" not in output
    assert "line_end" not in output
    assert "column_start" not in output
    assert "column_end" not in output


def remove_lambdas(sct_str, count=0, with_args=False):
    if with_args:
        return re.sub("lambda.*?:", "", sct_str, count=count)
    else:
        return re.sub("lambda:", "", sct_str, count=count)


def replace_test_if(sct):
    return re.sub(r"test_if_else\(", "test_if_exp(", sct)


@contextmanager
def set_v2_only_env(new):
    key = "PYTHONWHAT_V2_ONLY"
    old = os.environ.get(key)
    try:
        os.environ[key] = new
        yield
    finally:
        if old is None:
            del os.environ[key]
        else:
            os.environ[key] = old
