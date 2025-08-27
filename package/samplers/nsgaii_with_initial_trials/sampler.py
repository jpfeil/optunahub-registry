from __future__ import annotations

from collections.abc import Callable
from collections.abc import Sequence
from typing import TYPE_CHECKING

import optuna
from optuna.samplers import NSGAIISampler
from optuna.samplers._lazy_random_state import LazyRandomState
from optuna.samplers.nsgaii._crossovers._base import BaseCrossover
from optuna.samplers.nsgaii._crossovers._uniform import UniformCrossover
from optuna.study import Study
from optuna.trial import FrozenTrial
from optuna.trial import TrialState

from ._child_generation_strategy import NSGAIIwITChildGenerationStrategy
from ._mutations._base import BaseMutation
from ._mutations._uniform import UniformMutation


if TYPE_CHECKING:
    from optuna.study import Study


class NSGAIIwITSampler(NSGAIISampler):
    def __init__(
        self,
        *,
        population_size: int = 50,
        mutation: BaseMutation | None = None,
        mutation_prob: float | None = None,
        crossover: BaseCrossover | None = None,
        crossover_prob: float = 0.9,
        swapping_prob: float = 0.5,
        seed: int | None = None,
        constraints_func: Callable[[FrozenTrial], Sequence[float]] | None = None,
        elite_population_selection_strategy: (
            Callable[[Study, list[FrozenTrial]], list[FrozenTrial]] | None
        ) = None,
        after_trial_strategy: (
            Callable[[Study, FrozenTrial, TrialState, Sequence[float] | None], None] | None
        ) = None,
    ) -> None:
        if crossover is None:
            crossover = UniformCrossover(swapping_prob)

        if mutation is None:
            mutation = UniformMutation()

        child_generation_strategy_w_mutation = NSGAIIwITChildGenerationStrategy(
            mutation=mutation,
            mutation_prob=mutation_prob,
            crossover=crossover,
            crossover_prob=crossover_prob,
            swapping_prob=swapping_prob,
            constraints_func=constraints_func,
            rng=LazyRandomState(seed),
        )

        super().__init__(
            population_size=population_size,
            mutation_prob=mutation_prob,
            crossover=crossover,
            crossover_prob=crossover_prob,
            swapping_prob=swapping_prob,
            seed=seed,
            constraints_func=constraints_func,
            elite_population_selection_strategy=elite_population_selection_strategy,
            child_generation_strategy=child_generation_strategy_w_mutation,
            after_trial_strategy=after_trial_strategy,
        )

    def get_trial_generation(self, study: optuna.Study, trial: FrozenTrial) -> int:
        generation = trial.system_attrs.get(self._get_generation_key(), None)
        if generation is not None:
            return generation

        trials = study._get_trials(deepcopy=False, states=[TrialState.COMPLETE], use_cache=True)

        max_generation, max_generation_count = 0, 0

        for t in reversed(trials):
            generation = t.system_attrs.get(self._get_generation_key(), -1)

            if generation < max_generation:
                continue
            elif generation > max_generation:
                max_generation = generation
                max_generation_count = 1
            else:
                max_generation_count += 1

        assert self._population_size is not None, "Population size must be set."

        # Modified below section :
        # If there are already more trials than the population before sampling the 0th generation, set the generation to 1.
        if len(trials) > self._population_size and max_generation < 1:
            generation = 1
        # ---
        elif max_generation_count < self._population_size:
            generation = max_generation
        else:
            generation = max_generation + 1
        study._storage.set_trial_system_attr(
            trial._trial_id, self._get_generation_key(), generation
        )
        return generation

    def get_population(self, study: optuna.Study, generation: int) -> list[FrozenTrial]:
        # Modified below section :
        # In order to take all trials into consideration, return all results when generation=0.
        if generation == 0:
            return [
                trial
                for trial in study._get_trials(
                    deepcopy=False, states=[TrialState.COMPLETE], use_cache=True
                )
            ]
        # ---
        else:
            return [
                trial
                for trial in study._get_trials(
                    deepcopy=False, states=[TrialState.COMPLETE], use_cache=True
                )
                if trial.system_attrs.get(self._get_generation_key(), None) == generation
            ]
