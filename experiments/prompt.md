Call claude opus 5.5 (thinking high) using my claude code cli for each of the hard tasks from Large Lemma Miners.
with the following prompt template:

```
Use @accelerate-sva-proofs/SKILL.md to accelerate the proof of the assert in <Task name> from Large
Lemma Miners, you can use any engine in jasper and only jasper; to connect to jasper use "ssh vlsi".

Have a 900 second time limit for each engine run, record the total cpu and agent time.
```

- !!! Don't read or let the subagents read, the runs of any other agent or
any benchmark results !!!
- If several tasks are the same but with different sizes of the same module,
merge them into a single experiment with a sweep over the required
parameters.
- Monitor Claude's /status and if the 5 hour usage limit reaches 90% stop the agent and resume it when the limit resets; do this loop until all your subagents finish.
