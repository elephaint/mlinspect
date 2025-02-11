"""
Tests whether the PipelineExecutor works
"""

from test.testing_helper_utils import run_random_annotation_testing_analyzer, \
    run_row_index_annotation_testing_analyzer, run_multiple_test_analyzers
from example_pipelines import ADULT_SIMPLE_PY


def test_sklearn_backend_random_annotation_propagation():
    """
    Tests whether the sklearn backend works
    """
    with open(ADULT_SIMPLE_PY) as file:
        code = file.read()

        random_annotation_analyzer_result = run_random_annotation_testing_analyzer(code)
        assert len(random_annotation_analyzer_result) == 16


def test_sklearn_backend_row_index_annotation_propagation():
    """
    Tests whether the sklearn backend works
    """
    with open(ADULT_SIMPLE_PY) as file:
        code = file.read()
        lineage_result = run_row_index_annotation_testing_analyzer(code)
        assert len(lineage_result) == 16


def test_sklearn_backend_annotation_propagation_multiple_analyzers():
    """
    Tests whether the sklearn backend works
    """
    with open(ADULT_SIMPLE_PY) as file:
        code = file.read()

        analyzer_results, analyzers = run_multiple_test_analyzers(code)

        for analyzer in analyzers:
            result = analyzer_results[analyzer]
            assert len(result) == 16
