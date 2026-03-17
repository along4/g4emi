Python unit tests for configuration and macro-generation behavior.
Analysis-focused tests live in `test/unit/analysis/` and are split by feature
area.

Run from repository root:

```bash
python -m unittest discover -s test/unit -t . -p "test_*.py"
```

To run only the analysis tests:

```bash
python -m unittest discover -s test/unit/analysis -p "test_*.py"
```

If using pixi:

```bash
pixi run test-python
```
