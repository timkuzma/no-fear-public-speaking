"""Live comparison must refuse unsafe work before opening the production ledger."""
import asyncio
from types import SimpleNamespace

import pytest
from scripts import benchmark_wording


@pytest.mark.parametrize('changes,retries', [
    ({'live': False}, '1'),
    ({}, '2'),
    ({'models': 'one,one'}, '1'),
    ({'models': 'one,two,three'}, '1'),
    ({'max_attempts': 2}, '1'),
    ({'max_attempts': 7}, '1'),
    ({'max_input_chars': 0}, '1'),
    ({'max_output_tokens': 18001}, '1'),
])
def test_unsafe_run_never_opens_ledger(monkeypatch, tmp_path, changes, retries):
    options = SimpleNamespace(live=True, models='one', max_attempts=3,
                              max_input_chars=20000, max_output_tokens=9000,
                              data_dir=tmp_path, output=tmp_path / 'out.json')
    for key, value in changes.items():
        setattr(options, key, value)
    monkeypatch.setenv('LLM_MAX_ATTEMPTS', retries)
    def forbidden(*args):
        pytest.fail('Unsafe configuration reached production ledger')
    monkeypatch.setattr(benchmark_wording, 'ExistingLedger', forbidden)
    with pytest.raises(ValueError):
        asyncio.run(benchmark_wording.run(options))
    assert not options.output.exists()
