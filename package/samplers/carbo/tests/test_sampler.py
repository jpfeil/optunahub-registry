from __future__ import annotations

from collections.abc import Callable
import multiprocessing
from multiprocessing.managers import DictProxy
import os
from typing import Any
from unittest.mock import patch
import warnings

from _pytest.fixtures import SubRequest
from _pytest.mark.structures import MarkDecorator
import numpy as np
import optuna
from optuna.distributions import BaseDistribution
from optuna.distributions import CategoricalDistribution
from optuna.distributions import FloatDistribution
from optuna.distributions import IntDistribution
from optuna.samplers import BaseSampler
from optuna.samplers._lazy_random_state import LazyRandomState
from optuna.study import Study
from optuna.trial import FrozenTrial
from optuna.trial import Trial
from optuna.trial import TrialState
import optunahub
import pytest


# NOTE(nabenabe): This file content is mostly copied from the Optuna repository.
CARBOSampler = optunahub.load_local_module(
    package="samplers/carbo", registry_root="package/"
).CARBOSampler


def get_carbo_sampler(
    *, n_startup_trials: int = 0, deterministic_objective: bool = False, seed: int | None = None
) -> CARBOSampler:  # type: ignore[valid-type]
    return CARBOSampler(
        n_startup_trials=n_startup_trials,
        seed=seed,
        deterministic_objective=deterministic_objective,
    )


parametrize_sampler = pytest.mark.parametrize(
    "sampler_class",
    [
        lambda: get_carbo_sampler(n_startup_trials=0),
        lambda: get_carbo_sampler(n_startup_trials=0, deterministic_objective=True),
    ],
)
parametrize_relative_sampler = pytest.mark.parametrize(
    "relative_sampler_class",
    [
        lambda: get_carbo_sampler(n_startup_trials=0),
        lambda: get_carbo_sampler(n_startup_trials=0, deterministic_objective=True),
    ],
)

sampler_class_with_seed: dict[str, Callable[[int], BaseSampler]] = {
    "GPSampler": lambda seed: get_carbo_sampler(seed=seed, n_startup_trials=0),
}
param_sampler_with_seed = []
param_sampler_name_with_seed = []
for sampler_name, sampler_class in sampler_class_with_seed.items():
    param_sampler_with_seed.append(pytest.param(sampler_class, id=sampler_name))
    param_sampler_name_with_seed.append(pytest.param(sampler_name))
parametrize_sampler_with_seed = pytest.mark.parametrize("sampler_class", param_sampler_with_seed)
parametrize_sampler_name_with_seed = pytest.mark.parametrize(
    "sampler_name", param_sampler_name_with_seed
)


@pytest.mark.parametrize(
    "sampler_class,expected_has_rng,expected_has_another_sampler",
    [(lambda: get_carbo_sampler(n_startup_trials=0), True, True)],
)
def test_sampler_reseed_rng(
    sampler_class: Callable[[], BaseSampler],
    expected_has_rng: bool,
    expected_has_another_sampler: bool,
) -> None:
    def _extract_attr_name_from_sampler_by_cls(sampler: BaseSampler, cls: Any) -> str | None:
        for name, attr in sampler.__dict__.items():
            if isinstance(attr, cls):
                return name
        return None

    sampler = sampler_class()

    rng_name = _extract_attr_name_from_sampler_by_cls(sampler, LazyRandomState)
    has_rng = rng_name is not None
    assert expected_has_rng == has_rng
    if has_rng:
        rng_name = str(rng_name)
        original_random_state = sampler.__dict__[rng_name].rng.get_state()
        sampler.reseed_rng()
        random_state = sampler.__dict__[rng_name].rng.get_state()
        if not isinstance(sampler, optuna.samplers.CmaEsSampler):
            assert str(original_random_state) != str(random_state)
        else:
            # CmaEsSampler has a RandomState that is not reseed by its reseed_rng method.
            assert str(original_random_state) == str(random_state)

    had_sampler_name = _extract_attr_name_from_sampler_by_cls(sampler, BaseSampler)
    has_another_sampler = had_sampler_name is not None
    assert expected_has_another_sampler == has_another_sampler

    if has_another_sampler:
        had_sampler_name = str(had_sampler_name)
        had_sampler = sampler.__dict__[had_sampler_name]
        had_sampler_rng_name = _extract_attr_name_from_sampler_by_cls(had_sampler, LazyRandomState)
        original_had_sampler_random_state = had_sampler.__dict__[
            had_sampler_rng_name
        ].rng.get_state()
        with patch.object(
            had_sampler,
            "reseed_rng",
            wraps=had_sampler.reseed_rng,
        ) as mock_object:
            sampler.reseed_rng()
            assert mock_object.call_count == 1

        had_sampler = sampler.__dict__[had_sampler_name]
        had_sampler_random_state = had_sampler.__dict__[had_sampler_rng_name].rng.get_state()
        assert str(original_had_sampler_random_state) != str(had_sampler_random_state)


def parametrize_suggest_method(name: str) -> MarkDecorator:
    return pytest.mark.parametrize(
        f"suggest_method_{name}",
        [
            lambda t: t.suggest_float(name, 0, 10),
            lambda t: t.suggest_float(name, 1e-7, 10, log=True),
        ],
    )


@parametrize_sampler
@pytest.mark.parametrize(
    "distribution",
    [
        FloatDistribution(-1.0, 1.0),
        FloatDistribution(0.0, 1.0),
        FloatDistribution(-1.0, 0.0),
        FloatDistribution(1e-7, 1.0, log=True),
        FloatDistribution(-10, 10, step=0.1),
        FloatDistribution(-10.2, 10.2, step=0.1),
    ],
)
def test_float(
    sampler_class: Callable[[], BaseSampler],
    distribution: FloatDistribution,
) -> None:
    study = optuna.study.create_study(sampler=sampler_class())
    points = np.array(
        [
            study.sampler.sample_independent(study, _create_new_trial(study), "x", distribution)
            for _ in range(100)
        ]
    )
    assert np.all(points >= distribution.low)
    assert np.all(points <= distribution.high)
    assert not isinstance(
        study.sampler.sample_independent(study, _create_new_trial(study), "x", distribution),
        np.floating,
    )

    if distribution.step is not None:
        # Check all points are multiples of distribution.step.
        points -= distribution.low
        points /= distribution.step
        round_points = np.round(points)
        np.testing.assert_almost_equal(round_points, points)


@parametrize_relative_sampler
@pytest.mark.parametrize(
    "x_distribution",
    [FloatDistribution(-1.0, 1.0), FloatDistribution(1e-7, 1.0, log=True)],
)
@pytest.mark.parametrize(
    "y_distribution",
    [FloatDistribution(-1.0, 1.0), FloatDistribution(1e-7, 1.0, log=True)],
)
def test_sample_relative_numerical(
    relative_sampler_class: Callable[[], BaseSampler],
    x_distribution: BaseDistribution,
    y_distribution: BaseDistribution,
) -> None:
    search_space: dict[str, BaseDistribution] = dict(x=x_distribution, y=y_distribution)
    study = optuna.study.create_study(sampler=relative_sampler_class())
    trial = study.ask(search_space)
    study.tell(trial, sum(trial.params.values()))

    def sample() -> list[int | float]:
        params = study.sampler.sample_relative(study, _create_new_trial(study), search_space)
        return [params[name] for name in search_space]

    points = np.array([sample() for _ in range(10)])
    for i, distribution in enumerate(search_space.values()):
        assert isinstance(
            distribution,
            (
                FloatDistribution,
                IntDistribution,
            ),
        )
        assert np.all(points[:, i] >= distribution.low)
        assert np.all(points[:, i] <= distribution.high)
    for param_value, distribution in zip(sample(), search_space.values()):
        assert not isinstance(param_value, np.floating)
        assert not isinstance(param_value, np.integer)
        if isinstance(distribution, IntDistribution):
            assert isinstance(param_value, int)
        else:
            assert isinstance(param_value, float)


@parametrize_sampler
def test_conditional_sample_independent(sampler_class: Callable[[], BaseSampler]) -> None:
    # This test case reproduces the error reported in #2734.
    # See https://github.com/optuna/optuna/pull/2734#issuecomment-857649769.

    study = optuna.study.create_study(sampler=sampler_class())
    categorical_distribution = CategoricalDistribution(choices=["x", "y"])
    dependent_distribution = CategoricalDistribution(choices=["a", "b"])

    study.add_trial(
        optuna.create_trial(
            params={"category": "x", "x": "a"},
            distributions={"category": categorical_distribution, "x": dependent_distribution},
            value=0.1,
        )
    )

    study.add_trial(
        optuna.create_trial(
            params={"category": "y", "y": "b"},
            distributions={"category": categorical_distribution, "y": dependent_distribution},
            value=0.1,
        )
    )

    _trial = _create_new_trial(study)
    category = study.sampler.sample_independent(
        study, _trial, "category", categorical_distribution
    )
    assert category in ["x", "y"]
    value = study.sampler.sample_independent(study, _trial, category, dependent_distribution)
    assert value in ["a", "b"]


def _create_new_trial(study: Study) -> FrozenTrial:
    trial_id = study._storage.create_new_trial(study._study_id)
    return study._storage.get_trial(trial_id)


class FixedSampler(BaseSampler):
    def __init__(
        self,
        relative_search_space: dict[str, BaseDistribution],
        relative_params: dict[str, Any],
        unknown_param_value: Any,
    ) -> None:
        self.relative_search_space = relative_search_space
        self.relative_params = relative_params
        self.unknown_param_value = unknown_param_value

    def infer_relative_search_space(
        self, study: Study, trial: FrozenTrial
    ) -> dict[str, BaseDistribution]:
        return self.relative_search_space

    def sample_relative(
        self, study: Study, trial: FrozenTrial, search_space: dict[str, BaseDistribution]
    ) -> dict[str, Any]:
        return self.relative_params

    def sample_independent(
        self,
        study: Study,
        trial: FrozenTrial,
        param_name: str,
        param_distribution: BaseDistribution,
    ) -> Any:
        return self.unknown_param_value


def test_sample_relative() -> None:
    relative_search_space: dict[str, BaseDistribution] = {
        "a": FloatDistribution(low=0, high=5),
    }
    relative_params = {
        "a": 3.2,
    }
    unknown_param_value = 30

    sampler = FixedSampler(relative_search_space, relative_params, unknown_param_value)
    study = optuna.study.create_study(sampler=sampler)

    def objective(trial: Trial) -> float:
        # Predefined parameters are sampled by `sample_relative()` method.
        assert trial.suggest_float("a", 0, 5) == 3.2

        # Other parameters are sampled by `sample_independent()` method.
        assert trial.suggest_float("d", 1, 100, log=True) == unknown_param_value
        assert trial.suggest_float("e", 20, 40) == unknown_param_value

        return 0.0

    study.optimize(objective, n_trials=10, catch=())
    for trial in study.trials:
        assert trial.params == {"a": 3.2, "d": 30, "e": 30}


@parametrize_sampler
def test_nan_objective_value(sampler_class: Callable[[], BaseSampler]) -> None:
    study = optuna.create_study(sampler=sampler_class())

    def objective(trial: Trial, base_value: float) -> float:
        return trial.suggest_float("x", 0.1, 0.2) + base_value

    # Non NaN objective values.
    for i in range(10, 1, -1):
        study.optimize(lambda t: objective(t, i), n_trials=1, catch=())
    assert int(study.best_value) == 2

    # NaN objective values.
    study.optimize(lambda t: objective(t, float("nan")), n_trials=1, catch=())
    assert int(study.best_value) == 2

    # Non NaN objective value.
    study.optimize(lambda t: objective(t, 1), n_trials=1, catch=())
    assert int(study.best_value) == 1


@parametrize_sampler
def test_sample_single_distribution(sampler_class: Callable[[], BaseSampler]) -> None:
    relative_search_space = {
        "a": CategoricalDistribution([1]),
        "b": IntDistribution(low=1, high=1),
        "c": IntDistribution(low=1, high=1, log=True),
        "d": FloatDistribution(low=1.0, high=1.0),
        "e": FloatDistribution(low=1.0, high=1.0, log=True),
        "f": FloatDistribution(low=1.0, high=1.0, step=1.0),
    }

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", optuna.exceptions.ExperimentalWarning)
        sampler = sampler_class()
    study = optuna.study.create_study(sampler=sampler)

    # We need to test the construction of the model, so we should set `n_trials >= 2`.
    for _ in range(2):
        trial = study.ask(fixed_distributions=relative_search_space)
        study.tell(trial, 1.0)
        for param_name in relative_search_space.keys():
            assert trial.params[param_name] == 1


@parametrize_sampler
@parametrize_suggest_method("x")
def test_single_parameter_objective(
    sampler_class: Callable[[], BaseSampler], suggest_method_x: Callable[[Trial], float]
) -> None:
    def objective(trial: Trial) -> float:
        return suggest_method_x(trial)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", optuna.exceptions.ExperimentalWarning)
        sampler = sampler_class()

    study = optuna.study.create_study(sampler=sampler)
    study.optimize(objective, n_trials=10)

    assert len(study.trials) == 10
    assert all(t.state == TrialState.COMPLETE for t in study.trials)


@parametrize_sampler
def test_conditional_parameter_objective(sampler_class: Callable[[], BaseSampler]) -> None:
    def objective(trial: Trial) -> float:
        if trial.number % 2 == 0:
            return trial.suggest_float("y", 0, 1)
        return trial.suggest_float("z", 0, 1)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", optuna.exceptions.ExperimentalWarning)
        sampler = sampler_class()

    study = optuna.study.create_study(sampler=sampler)
    study.optimize(objective, n_trials=10)

    assert len(study.trials) == 10
    assert all(t.state == TrialState.COMPLETE for t in study.trials)


@parametrize_sampler
@parametrize_suggest_method("x")
@parametrize_suggest_method("y")
def test_combination_of_different_distributions_objective(
    sampler_class: Callable[[], BaseSampler],
    suggest_method_x: Callable[[Trial], float],
    suggest_method_y: Callable[[Trial], float],
) -> None:
    def objective(trial: Trial) -> float:
        return suggest_method_x(trial) + suggest_method_y(trial)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", optuna.exceptions.ExperimentalWarning)
        sampler = sampler_class()

    study = optuna.study.create_study(sampler=sampler)
    study.optimize(objective, n_trials=3)

    assert len(study.trials) == 3
    assert all(t.state == TrialState.COMPLETE for t in study.trials)


@parametrize_sampler
@pytest.mark.parametrize(
    "second_low,second_high",
    [
        (0, 5),  # Narrow range.
        (0, 20),  # Expand range.
        (20, 30),  # Set non-overlapping range.
    ],
)
def test_dynamic_range_objective(
    sampler_class: Callable[[], BaseSampler], second_low: int, second_high: int
) -> None:
    def objective(trial: Trial, low: int, high: int) -> float:
        v = trial.suggest_float("x", low, high)
        v += trial.suggest_float("y", low, high)
        return v

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", optuna.exceptions.ExperimentalWarning)
        sampler = sampler_class()

    study = optuna.study.create_study(sampler=sampler)
    study.optimize(lambda t: objective(t, 0, 10), n_trials=10)
    study.optimize(lambda t: objective(t, second_low, second_high), n_trials=10)

    assert len(study.trials) == 20
    assert all(t.state == TrialState.COMPLETE for t in study.trials)


# We add tests for constant objective functions to ensure the reproducibility of sorting.
@parametrize_sampler_with_seed
@pytest.mark.slow
@pytest.mark.parametrize("objective_func", [lambda *args: sum(args), lambda *args: 0.0])
def test_reproducible(sampler_class: Callable[[int], BaseSampler], objective_func: Any) -> None:
    def objective(trial: Trial) -> float:
        a = trial.suggest_float("a", 1, 9)
        b = trial.suggest_float("b", 1, 9, log=True)
        return objective_func(a, b)

    study = optuna.create_study(sampler=sampler_class(1))
    study.optimize(objective, n_trials=15)

    study_same_seed = optuna.create_study(sampler=sampler_class(1))
    study_same_seed.optimize(objective, n_trials=15)
    for i in range(15):
        assert study.trials[i].params == study_same_seed.trials[i].params

    study_different_seed = optuna.create_study(sampler=sampler_class(2))
    study_different_seed.optimize(objective, n_trials=15)
    assert any(
        [study.trials[i].params != study_different_seed.trials[i].params for i in range(15)]
    )


@pytest.mark.slow
@parametrize_sampler_with_seed
def test_reseed_rng_change_sampling(sampler_class: Callable[[int], BaseSampler]) -> None:
    def objective(trial: Trial) -> float:
        a = trial.suggest_float("a", 1, 9)
        b = trial.suggest_float("b", 1, 9, log=True)
        return a + b

    sampler = sampler_class(1)
    study = optuna.create_study(sampler=sampler)
    study.optimize(objective, n_trials=15)

    sampler_different_seed = sampler_class(1)
    sampler_different_seed.reseed_rng()
    study_different_seed = optuna.create_study(sampler=sampler_different_seed)
    study_different_seed.optimize(objective, n_trials=15)
    assert any(
        [study.trials[i].params != study_different_seed.trials[i].params for i in range(15)]
    )


# This function is used only in test_reproducible_in_other_process, but declared at top-level
# because local function cannot be pickled, which occurs within multiprocessing.
def run_optimize(
    k: int,
    sampler_name: str,
    sequence_dict: DictProxy,
    hash_dict: DictProxy,
) -> None:
    def objective(trial: Trial) -> float:
        a = trial.suggest_float("a", 1, 9)
        b = trial.suggest_float("b", 1, 9, log=True)
        return a + b

    hash_dict[k] = hash("nondeterministic hash")
    sampler = sampler_class_with_seed[sampler_name](1)
    study = optuna.create_study(sampler=sampler)
    study.optimize(objective, n_trials=15)
    sequence_dict[k] = list(study.trials[-1].params.values())


@pytest.fixture
def unset_seed_in_test(request: SubRequest) -> None:
    # Unset the hashseed at beginning and restore it at end regardless of an exception in the test.
    # See https://docs.pytest.org/en/stable/how-to/fixtures.html#adding-finalizers-directly
    # for details.

    hash_seed = os.getenv("PYTHONHASHSEED")
    if hash_seed is not None:
        del os.environ["PYTHONHASHSEED"]

    def restore_seed() -> None:
        if hash_seed is not None:
            os.environ["PYTHONHASHSEED"] = hash_seed

    request.addfinalizer(restore_seed)


@pytest.mark.slow
@parametrize_sampler_name_with_seed
def test_reproducible_in_other_process(sampler_name: str, unset_seed_in_test: None) -> None:
    # This test should be tested without `PYTHONHASHSEED`. However, some tool such as tox
    # set the environmental variable "PYTHONHASHSEED" by default.
    # To do so, this test calls a finalizer: `unset_seed_in_test`.

    # Multiprocessing supports three way to start a process.
    # We use `spawn` option to create a child process as a fresh python process.
    # For more detail, see https://github.com/optuna/optuna/pull/3187#issuecomment-997673037.
    multiprocessing.set_start_method("spawn", force=True)
    manager = multiprocessing.Manager()
    sequence_dict: DictProxy = manager.dict()
    hash_dict: DictProxy = manager.dict()
    for i in range(3):
        p = multiprocessing.Process(
            target=run_optimize, args=(i, sampler_name, sequence_dict, hash_dict)
        )
        p.start()
        p.join()

    # Hashes are expected to be different because string hashing is nondeterministic per process.
    assert not (hash_dict[0] == hash_dict[1] == hash_dict[2])
    # But the sequences are expected to be the same.
    assert sequence_dict[0] == sequence_dict[1] == sequence_dict[2]


@pytest.mark.parametrize("n_jobs", [1, 2])
@parametrize_relative_sampler
def test_trial_relative_params(
    n_jobs: int, relative_sampler_class: Callable[[], BaseSampler]
) -> None:
    # TODO(nabenabe): Consider moving this test to study.
    sampler = relative_sampler_class()
    study = optuna.study.create_study(sampler=sampler)

    def objective(trial: Trial) -> float:
        assert trial._relative_params is None

        trial.suggest_float("x", -10, 10)
        trial.suggest_float("y", -10, 10)
        assert trial._relative_params is not None
        return -1

    study.optimize(objective, n_trials=10, n_jobs=n_jobs)
