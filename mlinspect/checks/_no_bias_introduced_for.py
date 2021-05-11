"""
The NoBiasIntroducedFor check
"""
from __future__ import annotations

import dataclasses
from typing import Iterable, OrderedDict
import collections
from matplotlib import pyplot
from numpy import nanmax
from pandas import DataFrame

from mlinspect.checks._check import Check, CheckStatus, CheckResult
from mlinspect.inspections._histogram_for_columns import HistogramForColumns
from mlinspect.inspections._inspection import Inspection
from mlinspect.instrumentation._dag_node import OperatorType, DagNode
from mlinspect.inspections._inspection_result import InspectionResult


@dataclasses.dataclass(eq=True, frozen=True)
class BiasDistributionChange:
    """
    Did the histogram change too much for one given operation?
    """
    dag_node: DagNode
    acceptable_change: bool
    min_relative_ratio_change: float
    acceptable_probability_difference: bool
    max_probability_difference: float
    before_and_after_df: DataFrame


@dataclasses.dataclass
class NoBiasIntroducedForResult(CheckResult):
    """
    Did the histogram change too much for some operations?
    """
    bias_distribution_change: OrderedDict[DagNode, OrderedDict[str, BiasDistributionChange]]


class NoBiasIntroducedFor(Check):
    """
    Does the user pipeline introduce bias because of operators like joins and selects?
    """

    # pylint: disable=unnecessary-pass, too-few-public-methods

    def __init__(self, sensitive_columns, min_allowed_relative_ratio_change=-0.3,
                 max_allowed_probability_difference=2.0):
        self.sensitive_columns = sensitive_columns
        self.min_allowed_relative_ratio_change = min_allowed_relative_ratio_change
        self.max_allowed_probability_difference = max_allowed_probability_difference

    @property
    def check_id(self):
        """The id of the Check"""
        return tuple(self.sensitive_columns), self.min_allowed_relative_ratio_change, \
            self.max_allowed_probability_difference

    @property
    def required_inspections(self) -> Iterable[Inspection]:
        """The inspections required for the check"""
        return [HistogramForColumns(self.sensitive_columns)]

    def evaluate(self, inspection_result: InspectionResult) -> CheckResult:
        """Evaluate the check"""
        dag = inspection_result.dag
        histograms = inspection_result.inspection_to_annotations[HistogramForColumns(self.sensitive_columns)]
        relevant_nodes = [node for node in dag.nodes if node.operator_type in {OperatorType.JOIN,
                                                                               OperatorType.SELECTION} or
                          (node.module == ('sklearn.impute._base', 'SimpleImputer', 'Pipeline') and
                           node.columns[0] in self.sensitive_columns)]
        check_status = CheckStatus.SUCCESS
        bias_distribution_change = collections.OrderedDict()
        issue_list = []
        for node in relevant_nodes:
            parents = list(dag.predecessors(node))
            column_results = collections.OrderedDict()
            for column in self.sensitive_columns:
                column_result = self.get_histograms_for_node_and_column(column, histograms, node, parents)
                column_results[column] = column_result
                if not column_result.acceptable_change:
                    issue = "A {} causes a min_relative_ratio_change of '{}' by {}, a value below the " \
                            "configured minimum threshold {}!" \
                        .format(node.operator_type.value, column, column_result.min_relative_ratio_change,
                                self.min_allowed_relative_ratio_change)
                    issue_list.append(issue)
                    check_status = CheckStatus.FAILURE
                elif not column_result.acceptable_probability_difference:
                    issue = "A {} causes a max_probability_difference of '{}' by {}, a value above the " \
                            "configured maximum threshold {}!" \
                        .format(node.operator_type.value, column, column_result.max_probability_difference,
                                self.max_allowed_probability_difference)
                    issue_list.append(issue)
                    check_status = CheckStatus.FAILURE

            bias_distribution_change[node] = column_results
        if issue_list:
            description = " ".join(issue_list)
        else:
            description = None
        return NoBiasIntroducedForResult(self, check_status, description, bias_distribution_change)

    def get_histograms_for_node_and_column(self, column, histograms, node, parents):
        """
        Compute histograms for a dag node like a join and a concrete sensitive column like race
        """
        # pylint: disable=too-many-locals, too-many-arguments
        after_map = histograms[node][column]
        after_df = DataFrame(after_map.items(), columns=["sensitive_column_value", "count_after"])

        before_map = {}
        for parent in parents:
            parent_histogram = histograms[parent][column]
            before_map = {**before_map, **parent_histogram}
        before_df = DataFrame(before_map.items(), columns=["sensitive_column_value", "count_before"])

        joined_df = before_df.merge(after_df, on="sensitive_column_value", how="outer")
        joined_df = joined_df.sort_values(by=['sensitive_column_value']).reset_index(drop=True)
        joined_df["count_before"] = joined_df["count_before"].fillna(0)
        joined_df["count_after"] = joined_df["count_after"].fillna(0)

        # TODO: What information is useful/what is confusing?
        # joined_df["absolute_change"] = joined_df["count_after"] - joined_df["count_before"]
        # joined_df["relative_change"] = joined_df["absolute_change"] / joined_df["count_before"]
        joined_df["ratio_before"] = joined_df["count_before"] / joined_df["count_before"].sum()
        joined_df["ratio_after"] = joined_df["count_after"] / joined_df["count_after"].sum()
        # joined_df["absolute_ratio_change"] = joined_df["ratio_after"] - joined_df["ratio_before"]
        absolute_ratio_change = joined_df["ratio_after"] - joined_df["ratio_before"]
        joined_df["relative_ratio_change"] = absolute_ratio_change / joined_df["ratio_before"]

        # Dropping nan values (e.g., missing value imputation) is a distribution change we consider okay
        not_nan = joined_df["sensitive_column_value"].notnull()
        min_relative_ratio_change = joined_df[not_nan]["relative_ratio_change"].min()
        all_changes_acceptable = min_relative_ratio_change >= self.min_allowed_relative_ratio_change

        # Probability of removal
        joined_df["removed_records"] = joined_df["count_before"] - joined_df["count_after"]
        joined_df["removal_probability"] = joined_df["removed_records"] / joined_df["count_before"]
        # There might be classes where no records are being removed.
        # We should probably find a more principled method to do this at some point
        non_zero_probabilities = joined_df["removal_probability"] > 0.0
        removal_probability_min = joined_df[non_zero_probabilities]["removal_probability"].min()
        joined_df["normalized_removal_probability"] = joined_df["removal_probability"] / removal_probability_min
        joined_df.loc[joined_df['removed_records'] < 0, 'removal_probability'] = 0
        joined_df.loc[joined_df['removed_records'] < 0, 'normalized_removal_probability'] = 0

        not_nan = joined_df["normalized_removal_probability"].notnull()
        max_probability_difference = nanmax([joined_df[not_nan]["normalized_removal_probability"].max(), 0.])
        acceptable_probability_difference = max_probability_difference <= self.max_allowed_probability_difference

        return BiasDistributionChange(node, all_changes_acceptable, min_relative_ratio_change,
                                      acceptable_probability_difference, max_probability_difference, joined_df)

    @staticmethod
    def plot_distribution_change_histograms(distribution_change: BiasDistributionChange, filename=None,
                                            save_to_file=False):
        """
        Plot before and after histograms visualising a DistributionChange
        """
        pyplot.subplot(1, 2, 1)
        keys = distribution_change.before_and_after_df["sensitive_column_value"]
        keys = [str(key) for key in keys]  # Necessary because of null values
        before_values = distribution_change.before_and_after_df["count_before"]
        after_values = distribution_change.before_and_after_df["count_after"]

        pyplot.bar(keys, before_values)
        pyplot.gca().set_title("before")
        pyplot.xticks(
            rotation=45,
            horizontalalignment='right',
        )

        pyplot.subplot(1, 2, 2)

        pyplot.bar(keys, after_values)
        pyplot.gca().set_title("after")
        pyplot.xticks(
            rotation=45,
            horizontalalignment='right',
        )

        fig = pyplot.gcf()
        fig.set_size_inches(12, 4)

        if save_to_file:
            fig.savefig(filename + '.svg', bbox_inches='tight')
            fig.savefig(filename + '.png', bbox_inches='tight', dpi=800)

        pyplot.show()
        pyplot.close()

    @staticmethod
    def plot_removal_probability_histograms(distribution_change: BiasDistributionChange, filename=None,
                                            save_to_file=False):
        """
        Plot before and after histograms visualising a DistributionChange
        """
        pyplot.subplot(1, 1, 1)
        keys = distribution_change.before_and_after_df["sensitive_column_value"]
        keys = [str(key) for key in keys]  # Necessary because of null values
        removal_probabilities = distribution_change.before_and_after_df["normalized_removal_probability"]

        pyplot.bar(keys, removal_probabilities)
        pyplot.gca().set_title("normed removal probability per member of sensitive group")
        pyplot.xticks(
            rotation=45,
            horizontalalignment='right',
        )

        fig = pyplot.gcf()
        fig.set_size_inches(6, 4)

        if save_to_file:
            fig.savefig(filename + '.svg', bbox_inches='tight')
            fig.savefig(filename + '.png', bbox_inches='tight', dpi=800)

        pyplot.show()
        pyplot.close()

    @staticmethod
    def get_distribution_changes_overview_as_df(no_bias_check_result: NoBiasIntroducedForResult) -> DataFrame:
        """
        Get a pandas DataFrame with an overview of all DistributionChanges
        """
        # pylint: disable=too-many-locals
        operator_types = []
        code_references = []
        modules = []
        code_snippets = []
        descriptions = []
        assert isinstance(no_bias_check_result.check, NoBiasIntroducedFor)
        sensitive_column_names = []
        for name in no_bias_check_result.check.sensitive_columns:
            total_change_column_name = "'{}' distribution change below the configured minimum test threshold"\
                .format(name)
            sensitive_column_names.append(total_change_column_name)
            removal_probability_column_name = "'{}' probability difference above the configured maximum test threshold"\
                .format(name)
            sensitive_column_names.append(removal_probability_column_name)

        sensitive_columns = []
        for _ in range(len(sensitive_column_names)):
            sensitive_columns.append([])
        for dag_node, distribution_change in no_bias_check_result.bias_distribution_change.items():
            operator_types.append(dag_node.operator_type)
            code_references.append(dag_node.code_reference)
            modules.append(dag_node.module)
            code_snippets.append(dag_node.source_code)
            descriptions.append(dag_node.description)
            for index, change_info in enumerate(distribution_change.values()):
                sensitive_columns[2*index].append(not change_info.acceptable_change)
                sensitive_columns[2*index+1].append(not change_info.acceptable_probability_difference)
        return DataFrame(zip(operator_types, descriptions, code_references, code_snippets, modules, *sensitive_columns),
                         columns=[
                             "operator_type",
                             "description",
                             "code_reference",
                             "source_code",
                             "module",
                             *sensitive_column_names])
