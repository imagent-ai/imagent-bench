# Benchmark CI

Benchmark orchestration should live with the benchmark or with external
automation, not inside the agent implementation repository. A standard offline
gate looks like this:

1. Check out the benchmark repo on a fixed ref.
2. Check out the base agent revision.
3. Check out the candidate agent revision.
4. Install `imagent-bench`.
5. Run the base agent and candidate agent against the same benchmark config.
6. Compare the two result files with `imagent_bench.compare`.

The critical invariant is that the candidate agent must not be able to modify
the benchmark code, task suite, or thresholds in the same pull request that is
being judged.

For untrusted pull requests, use the deterministic offline configs and avoid
repository secrets. For trusted same-repository branches, a separate live API
workflow can be enabled with protected secrets.

Store promoted baselines under `baselines/` in the benchmark repository or in a
separate benchmark-operations repository. Agent repositories do not need to
vendor benchmark workflows or baseline history.
