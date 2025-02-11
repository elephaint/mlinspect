"""
The Interface for the different instrumentation backends
"""
import abc

import networkx


class Backend(metaclass=abc.ABCMeta):
    """
    The Interface for the different instrumentation backends
    """

    def __init__(self):
        self.code_reference_to_module = {}
        self.code_reference_to_description = {}
        self.code_reference_to_code = {}
        self.dag_node_identifier_to_columns = {}
        self.dag_node_identifier_to_inspection_output = {}
        self.inspections = []

    @abc.abstractmethod
    def is_responsible_for_call(self, function_info, function_prefix, value=None):
        """Checks whether the backend is responsible for the current method call"""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def operator_map(self):
        """The list of known operator mappings"""
        raise NotImplementedError

    @abc.abstractmethod
    def process_wir(self, wir: networkx.DiGraph) -> networkx.DiGraph:
        """Preprocess the WIR if necessary before extracting the DAG"""
        raise NotImplementedError

    @abc.abstractmethod
    def process_dag(self, dag: networkx.DiGraph) -> networkx.DiGraph:
        """Postprocess the DAG if necessary"""
        raise NotImplementedError

    @abc.abstractmethod
    def before_call_used_value(self, function_info, subscript, call_code, value_code, value_value,
                               code_reference):
        """The value or module a function may be called on"""
        # pylint: disable=too-many-arguments, unused-argument
        raise NotImplementedError

    @abc.abstractmethod
    def before_call_used_args(self, function_info, subscript, call_code, args_code, code_reference, store,
                              args_values):
        """The arguments a function may be called with"""
        # pylint: disable=too-many-arguments, unused-argument
        raise NotImplementedError

    @abc.abstractmethod
    def before_call_used_kwargs(self, function_info, subscript, call_code, kwargs_code, code_reference, kwargs_values):
        """The keyword arguments a function may be called with"""
        # pylint: disable=too-many-arguments, unused-argument
        raise NotImplementedError

    @abc.abstractmethod
    def after_call_used(self, function_info, subscript, call_code, return_value, code_reference):
        """The return value of some function"""
        # pylint: disable=too-many-arguments, unused-argument
        raise NotImplementedError
