"""Runs the seeded fault-injection simulator (apps/core/simulation.py) in CI.

A failure prints the seed and the command that reproduces it locally:
    uv run python manage.py simulate --seed <seed>
"""

import os

import pytest

from apps.core.simulation import Simulation

# A fixed seed keeps CI deterministic; SIMULATION_SEEDS="1,2,3" runs others locally.
SEEDS = [int(s) for s in os.environ.get("SIMULATION_SEEDS", "20261011").split(",")]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("seed", SEEDS)
def test_simulation_upholds_every_invariant(seed):
    report = Simulation(seed, operations=int(os.environ.get("SIMULATION_OPS", "600"))).run()
    assert report.invariant_checks > 0
    assert report.incidents_opened > 0
    assert sum(report.faults.values()) > 0, "no faults were injected"
