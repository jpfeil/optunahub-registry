---
author: Ayush Chaudhary <Ayushkumar.chaudhary2003@gmail.com>
title: Hill Climbing Sampler
description: Hill climbing algorithm for discrete optimization problems
tags: [sampler, hill-climbing, discrete-optimization, local-search]
optuna_versions: [4.0.0]
license: MIT License
---

## Abstract

The hill climbing algorithm is an optimization technique that iteratively improves a
solution by evaluating neighboring solutions in search of a local maximum or minimum.
Starting with an initial guess, the algorithm examines nearby "neighbor" solutions,
moving to a better neighbor if one is found. This process continues until no improvement
can be made locally, at which point the algorithm may restart from a new random position.

This implementation focuses on discrete optimization problems, supporting integer and
categorical parameters only. The sampler fully supports both minimization and
maximization objectives as specified in the Optuna study direction, making it compatible
with all standard Optuna optimization workflows.

## Class or Function Names

- **HillClimbingSampler**

## Installation

No additional dependencies are required beyond Optuna and OptunaHub.

```bash
pip install optuna optunahub
```

## APIs

### HillClimbingSampler

```python
HillClimbingSampler(
    search_space: dict[str, BaseDistribution] | None = None,
    *,
    seed: int | None = None,
    neighbor_size: int = 5,
    max_restarts: int = 10,
)
```

#### Parameters

- **search_space** (dict\[str, BaseDistribution\] | None, optional): A dictionary
  containing the parameter names and their distributions. If None, the search space is
  inferred from the study.
- **seed** (int | None, optional): Seed for the random number generator to ensure
  reproducible results.
- **neighbor_size** (int, default=5): Number of neighboring solutions to generate and
  evaluate in each iteration.
- **max_restarts** (int, default=10): Maximum number of times the algorithm will restart
  from a random position when no improvements are found.

## Supported Distributions

- **IntDistribution**: Integer parameters with specified bounds
- **CategoricalDistribution**: Categorical parameters with discrete choices

## Supported Study Directions

- **Minimization**: `optuna.create_study(direction="minimize")` or
  `optuna.create_study(direction=optuna.study.StudyDirection.MINIMIZE)`
- **Maximization**: `optuna.create_study(direction="maximize")` or
  `optuna.create_study(direction=optuna.study.StudyDirection.MAXIMIZE)`

The algorithm automatically adapts its improvement criteria and best solution tracking
based on the study direction, ensuring optimal performance for both optimization types.

## Limitations

- **Discrete only**: This sampler only supports discrete parameter types (`suggest_int`
  and `suggest_categorical`). Continuous parameters (`suggest_float`) are not supported.
- **Single-objective**: Only single-objective optimization is supported.

## Examples

### Basic Usage with Minimization

```python
import optuna
import optunahub

def objective(trial):
    # Integer parameter
    x = trial.suggest_int("x", -10, 10)
    # Categorical parameter
    algorithm = trial.suggest_categorical("algorithm", ["A", "B", "C"])
    # Simple objective function
    penalty = {"A": 0, "B": 1, "C": 2}[algorithm]
    return x**2 + penalty

# Load the hill climbing sampler
module = optunahub.load_module("samplers/hill_climbing")
sampler = module.HillClimbingSampler(
    neighbor_size=8,    # Generate 8 neighbors per iteration
    max_restarts=5,     # Allow up to 5 restarts
    seed=42             # For reproducible results
)

# Create study for minimization
study = optuna.create_study(sampler=sampler, direction="minimize")
study.optimize(objective, n_trials=100)

print(f"Best value: {study.best_value}")
print(f"Best params: {study.best_params}")
```

### Maximization Example

```python
import optuna
import optunahub

def profit_objective(trial):
    # Resource allocation problem
    workers = trial.suggest_int("workers", 1, 20)
    strategy = trial.suggest_categorical("strategy", ["aggressive", "balanced", "conservative"])

    # Calculate profit (to be maximized)
    base_profit = workers * 100
    strategy_multiplier = {"aggressive": 1.5, "balanced": 1.2, "conservative": 1.0}[strategy]
    risk_penalty = {"aggressive": 50, "balanced": 20, "conservative": 0}[strategy]

    return base_profit * strategy_multiplier - risk_penalty

module = optunahub.load_module("samplers/hill_climbing")
sampler = module.HillClimbingSampler(neighbor_size=6, max_restarts=8, seed=123)

# Create study for maximization
study = optuna.create_study(sampler=sampler, direction="maximize")
study.optimize(profit_objective, n_trials=75)

print(f"Maximum profit: {study.best_value}")
print(f"Optimal allocation: {study.best_params}")
```

## Testing

### Running Tests

To execute the tests for HillClimbingSampler, run the following commands:

```bash
# Run with verbose output to see test details
pytest package/samplers/hill_climbing/tests/ -v

# Run a specific test file
pytest package/samplers/hill_climbing/tests/test_hill_climbing.py -v
```

### Test Coverage

The test suite includes comprehensive coverage of:

- **Initialization testing**: Various parameter configurations and default values
- **Distribution validation**: Ensuring only supported distributions are accepted
- **Minimization optimization**: Basic optimization with minimize direction
- **Maximization optimization**: Basic optimization with maximize direction
- **Direction support verification**: Confirms both minimize and maximize work correctly
- **Error handling**: Proper exceptions for unsupported parameter types

## Algorithm Details

### Initialization

The algorithm starts with a random point in the parameter space using Optuna's RandomSampler.

### Neighbor Generation

For each iteration, the algorithm generates neighboring solutions by:

- **Integer parameters**: Adding or subtracting a small step size (calculated as 1/20th of the parameter range, minimum 1)
- **Categorical parameters**: Randomly selecting a different category from the available choices

### Movement Strategy

The algorithm evaluates all generated neighbors and moves to the best improvement found. The improvement criteria automatically adapts based on the study direction:

- **Minimization** (direction="minimize"): Moves to neighbors with lower objective values
- **Maximization** (direction="maximize"): Moves to neighbors with higher objective values

If no improvement is discovered, the algorithm continues searching or restarts from a new random position.

### Restart Mechanism

When the algorithm gets stuck in a local optimum (no improvements found in recent iterations), it restarts from a new random position up to max_restarts times. The restart logic is direction-aware and properly handles both minimization and maximization scenarios.

## Performance Characteristics

### Strengths

- **Simple and interpretable**: Easy to understand and debug algorithm
- **Direction agnostic**: Full support for both minimization and maximization objectives
- **Good for discrete problems**: Well-suited for combinatorial optimization
- **Local exploitation**: Effective at refining solutions in promising regions
- **Memory efficient**: Low memory footprint compared to population-based algorithms
- **Configurable exploration**: Adjustable neighbor size and restart parameters

### Limitations

- **Local optima**: May get trapped in local optima without sufficient restarts
- **No global view**: Lacks global search capability of more sophisticated algorithms
- **Parameter sensitivity**: Performance depends on neighbor_size and max_restarts settings
- **Discrete only**: Cannot handle continuous parameters (suggest_float)

### When to Use

This sampler is most effective for:

- **Discrete/combinatorial optimization problems** (TSP, knapsack, resource allocation)
- **Problems with relatively small search spaces** where local search is sufficient
- **Both minimization and maximization objectives**
- **Situations where interpretability is important** and you need to understand the search process
- **Baseline comparisons** with more complex algorithms
- **Resource-constrained environments** where simple, efficient algorithms are preferred

## Troubleshooting

### Common Issues

#### ValueError about unsupported distributions:

```python
# ❌ This will raise an error
x = trial.suggest_float("x", 0.0, 1.0)  # FloatDistribution not supported

# ✅ Use discrete alternatives instead
x = trial.suggest_int("x", 0, 100)  # Use integer approximation
# or
x = trial.suggest_categorical("x", [0.1, 0.2, 0.3, 0.4, 0.5])  # Discrete choices
```

#### Poor performance:

- Increase neighbor_size for better local exploration
- Increase max_restarts to escape local optima
- Ensure your objective function has reasonable local structure

#### Getting stuck in local optima:

- Increase max_restarts parameter
- Consider using this sampler as a local refinement step after global search
- Verify that your problem has exploitable local structure

## References

- Russell, S., & Norvig, P. (2020). *Artificial Intelligence: A Modern Approach* (4th ed.). Chapter on Local Search Algorithms.
- Hoos, H. H., & Stützle, T. (2004). *Stochastic Local Search: Foundations and Applications*. Morgan Kaufmann.
- [Optuna Documentation: optuna.study.create_study](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.study.create_study.html)
- [Optuna Documentation: optuna.study.StudyDirection](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.study.StudyDirection.html)
